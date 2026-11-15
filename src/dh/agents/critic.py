"""Critic (layer 4): a Strands agent on Amazon Bedrock, the sceptic between the Portfolio and the Explainer.

It reads the strategies the Guardian passed, decides what looks doubtful, INVESTIGATES with deterministic tools before
objecting, and returns at most 3 objections, each citing the tool calls behind it, with one fix from a fixed menu
(merge two lines, trim a line, shift growth to defensive, or just disclose). "The LLM argues, code enforces" (#2):

    1. backed?   every number in an objection must appear in a tool result it cites (else dropped)
    2. allowed?  the fix can only keep or lower risk with assets already held (`portfolio.apply_action`)
    3. once      the Portfolio applies at most one fix per strategy, every number is recomputed (`portfolio.revise`)
    4. Guardian  re-checks the revised strategy; if it fails or breaks the loss limit, the original stays

Shown in the trace only (decision #30). Modes, like the Explainer (#23):
- `bedrock`: committed demo cache → local cache → Strands agent (BEDROCK_CRITIC_MODEL_ID, else the Explainer's
  default model). Cached by a hash of the facts, so a replay shows the same tool calls.
- `mock` (default, tests, offline): a deterministic critic that makes the same kind of tool calls and objections.
"""

from __future__ import annotations

from ..data import period_label

import functools
import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone

from ..data import ROOT
from ..metrics import look_through as _look_through
from . import guardian, market
from .rules import CORR_WARN, DEFENSIVE

PROMPT_VERSION = "critic-v1"
DEMO_CACHE = ROOT / "cache" / "critic"      # committed: the demo replays offline
LOCAL_CACHE = ROOT / ".cache" / "critic"    # gitignored
MAX_CALLS = 6
MAX_OBJECTIONS = 3

GUIDE = """1. Same bet twice? Two holdings whose returns move together (correlation >= 0.85) add little diversification.
2. Hidden concentration? A company or a sector close to its cap once the ETFs are looked through.
3. 2022 again? A historical drop or the 2022 sell-off close to the client's own loss limit.
4. Does it fit the goal? Little chance of reaching the target, or a conflict between goal and loss limit.
5. Does it fit the person? Their job sector, horizon, a request they made that we only partly met.
6. Are the strategies really different? Nearly the same weights or the same worst drop."""

SYSTEM_PROMPT = f"""You are the Critic in an investment-analysis SIMULATION (no real money, no advice). You receive
FACTS as JSON: a fictional client, their limits, and up to three strategies that already passed deterministic rules.
Your job is to be the sceptic a careful advisor would be, using this guide:
{GUIDE}

Work like this:
- Decide what looks doubtful, then CHECK it with the tools before objecting. At most {MAX_CALLS} tool calls in total.
- Every tool result has a call_id (t1, t2, ...). An objection must cite the call_ids that back it.
- Quote numbers ONLY as they appear in the tool results you cite (you may write 0.912 as 0.91 or 0.132 as 13.2%).
  An objection with a number no cited result contains is discarded by code.
- At most {MAX_OBJECTIONS} objections, the ones that matter most for THIS client. None is a valid answer.
- Each objection proposes one fix from this menu (code applies it, then re-checks every rule):
  {{"type": "merge", "a": TICKER, "b": TICKER}}   keep the larger of two holdings of the same kind
  {{"type": "trim", "ticker": TICKER, "to": WEIGHT}}  lower one growth holding (fraction, e.g. 0.05), excess to the core ETF
  {{"type": "shift", "pct": FRACTION}}            move up to 0.20 of the portfolio from growth to defensive
  {{"type": "disclose"}}                          no change: the client should simply know
  Fixes may only keep or lower risk. Never propose a new asset.
- No return forecasts, no "buy" or "sell".

Answer with JSON only, no prose around it:
{{"objections": [{{"strategy": "<key>", "claim": "<= 2 sentences", "evidence": ["t1"], "action": {{...}}}}]}}
"""


# ---- facts: what the Critic starts from ----------------------------------------------------------------

def facts(strategies: list[dict], limits: dict, profile: dict) -> dict:
    caps = limits.get("company_caps") or {}
    held = sorted({t for s in strategies for t in s["weights"]})
    return {
        "client": {k: profile.get(k) for k in ("name", "age", "horizon_years", "objective", "capital", "max_loss_pct",
                                               "interests", "exclusions", "requested_positions", "job_sector")},
        "limits": {"risk_level": limits.get("risk_level"), "loss_limit": limits.get("loss_limit"),
                   "defensive_floor": limits.get("min_defensive"), "crypto_cap": limits.get("max_crypto"),
                   "company_caps": {t: caps[t] for t in held if t in caps}},
        "strategies": [{
            "key": s["key"], "name": s["name"], "weights": s["weights"], "split": s["split"],
            "stats": {k: (s.get("stats") or {}).get(k) for k in ("max_drawdown", "stress_2022", "return_2022",
                                                                  "worst_12m", "ann_vol", "prob_loss")},
            "warnings": [c["check"] for c in s.get("checks", []) if c["status"] == "warn"],
        } for s in strategies],
    }


def facts_hash(f: dict, model_id: str = "") -> str:
    return hashlib.sha256(json.dumps([PROMPT_VERSION, model_id, f], sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---- tools: deterministic, recorded, capped ------------------------------------------------------------

class Recorder:
    """Numbers every tool call (t1, t2, ...), keeps args and results for the validator and the trace, enforces the
    call budget. Errors are returned as {"error"}, never raised, so the agent can read them."""

    def __init__(self, budget: int = MAX_CALLS):
        self.calls: list[dict] = []
        self.budget = budget

    def call(self, fn, name: str, kwargs: dict) -> dict:
        if len(self.calls) >= self.budget:
            return {"error": f"tool budget ({self.budget}) reached: answer now"}
        try:
            out = fn(**kwargs)
        except Exception as e:  # noqa: BLE001 — the agent reads the error and moves on
            out = {"error": f"{type(e).__name__}: {e}"[:300]}
        cid = f"t{len(self.calls) + 1}"
        self.calls.append({"call_id": cid, "tool": name, "args": kwargs, "result": out})
        return {"call_id": cid, **out} if isinstance(out, dict) else {"call_id": cid, "result": out}

    def wrap(self, fn):
        """The tool as the model sees it: only JSON parameters. Internal ones (e.g. `rets: pd.DataFrame`, kept for
        tests) are hidden: Strands builds a JSON schema from every parameter, and one DataFrame made the whole
        toolset fail on Bedrock (PydanticSchemaGenerationError), so the Critic and the Analyst fell back offline."""
        import inspect
        sig = inspect.signature(fn)
        keep = [p for p in sig.parameters.values() if p.name not in INTERNAL_PARAMS]

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            bound = inspect.Signature(keep).bind(*args, **kwargs)
            return self.call(fn, fn.__name__, dict(bound.arguments))
        del wrapper.__wrapped__  # inspect / Strands must read the reduced signature, not the original one
        wrapper.__signature__ = inspect.Signature(keep, return_annotation=sig.return_annotation)
        wrapper.__annotations__ = {k: v for k, v in getattr(fn, "__annotations__", {}).items()
                                   if k not in INTERNAL_PARAMS}
        return wrapper


INTERNAL_PARAMS = {"rets", "holdings"}  # never shown to the model: data objects, not JSON


def make_tools(strategies: list[dict], limits: dict, holdings: dict) -> list:
    """Joud's market tools (#15) + views on what the pipeline computed + risk contributions (#40)."""
    by_key = {s["key"]: s for s in strategies}

    def look_through(weights: dict[str, float]) -> dict:
        """Real exposure to each company once the ETFs are opened (issuer holdings files).

        Args:
            weights: {ticker: weight}, e.g. a strategy's weights.

        Returns:
            the 10 largest exposures (fractions) and each company's cap for this client.
        """
        eff = _look_through(weights, holdings)
        caps = limits.get("company_caps") or {}
        top = sorted(eff.items(), key=lambda kv: -kv[1])[:10]
        return market._round({"exposures": [{"name": k, "weight": v, "cap": caps.get(k)} for k, v in top],
                              "holdings_data": sorted(t for t in weights if t in holdings)})

    def strategy_checks(strategy: str) -> dict:
        """The rule checks already run on one strategy (C-F checks and Guardian G1-G17), with values and limits.

        Args:
            strategy: the strategy key from FACTS, e.g. "growth".

        Returns:
            checks: [{check, value, limit, status (pass/warn/fail), reason}].
        """
        s = by_key.get(strategy)
        if s is None:
            return {"error": f"unknown strategy {strategy!r}; keys: {sorted(by_key)}"}
        cs = [{k: c.get(k) for k in ("check", "value", "limit", "status", "reason")} for c in s.get("checks", [])]
        gs = [{"check": c["rule"], "status": c["status"], "reason": c["detail"]}
              for c in (s.get("guardian") or {}).get("checks", [])]
        return market._round({"strategy": strategy, "checks": cs + gs})

    def limit_reason(name: str) -> dict:
        """Why one of the client's limits has its value (the Profiler's written reasons).

        Args:
            name: loss_limit, defensive_floor, crypto, risk_level, or a ticker for its company cap.

        Returns:
            the value and the reasons that mention it.
        """
        keys = {"loss_limit": ("loss_limit", "loss limit"), "defensive_floor": ("min_defensive", "defensive floor"),
                "crypto": ("max_crypto", "crypto"), "risk_level": ("risk_level", "risk level")}
        if name in keys:
            k, word = keys[name]
            val = limits.get(k)
        else:
            word, val = "one company", (limits.get("company_caps") or {}).get(name)
            if val is None:
                return {"error": f"no limit named {name!r}"}
        return market._round({"name": name, "value": val,
                              "reasons": [r for r in limits.get("reasons", []) if word in r.lower()]})

    def risk_contributions(weights: dict[str, float]) -> dict:
        """Where the swings come from: each holding's share of the portfolio's risk vs its share of the money.
        Uses only volatilities and correlations of 2021-2026 daily returns, no average return (no forecast).

        Args:
            weights: {ticker: weight}, e.g. a strategy's weights.

        Returns:
            holdings sorted by risk share: [{ticker, weight, risk_share, ratio (risk_share / weight)}], ann_vol.
            A ratio of 2 means the holding brings twice as much risk as money.
        """
        from ..metrics import risk_contributions as _rc
        rets = market._tool_rets()
        err = market._check_weights(weights, rets)
        if err:
            return err
        tot = sum(weights.values())
        rc = _rc(rets, weights)
        rows = [{"ticker": t, "weight": weights[t] / tot, "risk_share": v,
                 "ratio": v / (weights[t] / tot) if weights[t] else None} for t, v in rc["shares"].items()]
        return market._round({"holdings": sorted(rows, key=lambda r: -r["risk_share"]), "ann_vol": rc["ann_vol"]})

    return list(market.AGENT_TOOLS) + [look_through, strategy_checks, limit_reason, risk_contributions]


@contextmanager
def _tool_returns(rets):
    """Market tools read market._TOOL_RETS; point them at the pipeline's returns (tests pass synthetic ones)."""
    old = market._TOOL_RETS
    if rets is not None:
        market._TOOL_RETS = rets
    try:
        yield
    finally:
        market._TOOL_RETS = old


# ---- code enforces: validation ---------------------------------------------------------------------------

_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?%?")


def _claim_numbers(text: str) -> list[str]:
    out = []
    for m in _NUM.findall(text or ""):
        v = float(m.rstrip("%"))
        if not m.endswith("%") and (v.is_integer() and (abs(v) <= 10 or 1900 <= v <= 2100)):
            continue  # small counts ("2 holdings", "3 strategies") and years are not data
        out.append(m)
    return out


def _result_numbers(x) -> list[float]:
    if isinstance(x, bool):
        return []
    if isinstance(x, (int, float)):
        return [float(x)]
    if isinstance(x, str):
        return [float(m.rstrip("%")) / (100 if m.endswith("%") else 1) for m in _NUM.findall(x)]
    if isinstance(x, dict):
        return [n for v in x.values() for n in _result_numbers(v)]
    if isinstance(x, (list, tuple)):
        return [n for v in x for n in _result_numbers(v)]
    return []


def _backed(token: str, pool: list[float]) -> bool:
    pct = token.endswith("%")
    s = token.rstrip("%")
    v = abs(float(s))
    tol = 0.5 * 10 ** -(len(s.split(".")[1]) if "." in s else 0) + 1e-9
    for r in pool:
        for c in ((abs(r) * 100, abs(r)) if pct else (abs(r), abs(r) * 100)):
            if abs(c - v) <= tol:
                return True
    return False


def validate(raw: list[dict], calls: list[dict], strategies: list[dict]) -> list[dict]:
    """Each objection gets a status: `valid` or `dropped: <why>`. At most MAX_OBJECTIONS are kept."""
    by_id = {c["call_id"]: c for c in calls}
    keys = {s["key"] for s in strategies}
    out = []
    for i, o in enumerate(raw if isinstance(raw, list) else []):
        o = dict(o) if isinstance(o, dict) else {"claim": str(o)}
        o.setdefault("action", {"type": "disclose"})
        o["id"] = f"K{i + 1}"
        if len([x for x in out if x["status"] == "valid"]) >= MAX_OBJECTIONS:
            o["status"] = f"dropped: more than {MAX_OBJECTIONS} objections"
        elif o.get("strategy") not in keys:
            o["status"] = f"dropped: unknown strategy {o.get('strategy')!r}"
        elif not o.get("evidence") or any(e not in by_id for e in o["evidence"]):
            o["status"] = "dropped: cites no tool call it made"
        else:
            pool = [n for e in o["evidence"] for n in _result_numbers(by_id[e]["result"])]
            missing = [t for t in _claim_numbers(o.get("claim", "")) if not _backed(t, pool)]
            o["status"] = f"dropped: unbacked number(s) {', '.join(missing)}" if missing else "valid"
        if not isinstance(o.get("action"), dict) or o["action"].get("type") not in ("merge", "trim", "shift", "disclose"):
            o["action"] = {"type": "disclose"}
        out.append(o)
    return out


# ---- the two critics: deterministic (mock) and the Strands agent ----------------------------------------

def _mock(strategies: list[dict], limits: dict, rec: Recorder, tools: dict) -> list[dict]:
    """Same method as the agent, fixed choices: check the most growth-heavy strategy's two largest growth lines for
    the same bet (→ merge), then read each strategy's warnings (→ disclose). It never shifts: every strategy sits at
    its computed ceiling by design (#17), so "close to the limit" is expected; trading that off is the agent's call."""
    out = []
    top = max(strategies, key=lambda s: s["split"]["growth"])
    growth = sorted((t for t in top["weights"] if t not in DEFENSIVE), key=lambda t: -top["weights"][t])[:2]
    if len(growth) == 2:
        r = rec.call(tools["correlation_between"], "correlation_between", {"tickers": growth})
        p = (r.get("pairs") or [{}])[0]
        if p.get("correlation", 0) >= CORR_WARN:
            out.append({"strategy": top["key"], "evidence": [r["call_id"]],
                        "claim": f"{p['a']} and {p['b']} moved almost together in {period_label()} (correlation "
                                 f"{p['correlation']:.2f}): holding both is largely the same bet.",
                        "action": {"type": "merge", "a": p["a"], "b": p["b"]}})
    for s in strategies:
        r = rec.call(tools["strategy_checks"], "strategy_checks", {"strategy": s["key"]})
        for c in r.get("checks", []):
            if c["status"] != "warn" or not c.get("reason") or c["check"].startswith("G"):
                continue
            out.append({"strategy": s["key"], "evidence": [r["call_id"]],
                        "claim": c["reason"][:1].upper() + c["reason"][1:].rstrip(".") + ".", "action": {"type": "disclose"}})
    out.sort(key=lambda o: o["action"]["type"] == "disclose")  # objections with a fix first
    return out[:MAX_OBJECTIONS]


def model_id() -> str:
    from .explainer import DEFAULT_MODEL_ID
    return os.getenv("BEDROCK_CRITIC_MODEL_ID") or os.getenv("BEDROCK_MODEL_ID") or DEFAULT_MODEL_ID


def _parse(text: str) -> list[dict]:
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in the answer")
    return json.loads(text[a:b + 1]).get("objections", [])


def _run_agent(f: dict, rec: Recorder, tools: list) -> list[dict]:
    """Strands agent on Bedrock with the recorded tools. Imported lazily: tests and mock mode don't need strands."""
    from strands import Agent, tool
    from strands.models import BedrockModel

    model = BedrockModel(model_id=model_id(), region_name=os.getenv("AWS_REGION", "us-east-1"), max_tokens=8000)
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[tool(rec.wrap(t)) for t in tools],
                  callback_handler=None)
    return _parse(str(agent("FACTS:\n" + json.dumps(f, ensure_ascii=False, default=str))))


# ---- entry points ------------------------------------------------------------------------------------------

def _cache_paths(h: str):
    return DEMO_CACHE / f"{h}.json", LOCAL_CACHE / f"{h}.json"


def review(strategies: list[dict], limits: dict, profile: dict, provider: str | None = None, rets=None,
           holdings=None) -> dict:
    """{objections, tool_calls, source, model, note, facts_hash}. Never raises on agent failure (→ mock critic)."""
    provider = (provider or os.getenv("LLM_PROVIDER", "mock")).lower()
    if holdings is None:
        from ..holdings import holdings as load_holdings
        holdings = load_holdings()
    f = facts(strategies, limits, profile)
    mid = model_id()
    h = facts_hash(f, mid)
    tools = make_tools(strategies, limits, holdings)
    raw = calls = None
    src, note, model = "mock", "mock mode", ""
    for p in _cache_paths(h):
        if p.exists():
            c = json.loads(p.read_text())
            raw, calls, src, note, model = c["objections"], c["tool_calls"], f"cache ({p.parent.name})", "", c["model"]
            break
    with _tool_returns(rets):
        if raw is None and provider == "bedrock":
            rec = Recorder()
            try:
                raw = _run_agent(f, rec, tools)
                calls, src, note, model = rec.calls, "bedrock", "", mid
                LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
                _cache_paths(h)[1].write_text(json.dumps(
                    {"model": mid, "prompt_version": PROMPT_VERSION, "objections": raw, "tool_calls": calls,
                     "created": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                    ensure_ascii=False, indent=1, default=str))
            except Exception as e:  # noqa: BLE001 — any AWS/Strands/parse error → mock critic, said in the trace
                raw, note = None, f"agent unavailable ({type(e).__name__}: {e})"[:300]
        if raw is None:
            rec = Recorder()
            raw = _mock(strategies, limits, rec, {t.__name__: t for t in tools})
            calls = rec.calls
    return {"objections": validate(raw, calls, strategies), "tool_calls": calls, "source": src, "model": model,
            "note": note, "facts_hash": h}


def save_demo(c: dict) -> str:
    """Copy a Bedrock review into the committed demo cache (the demo replays it offline)."""
    if c["source"] != "bedrock" and not c["source"].startswith("cache"):
        raise ValueError(f"nothing to save: the review came from the mock critic ({c['note']})")
    DEMO_CACHE.mkdir(parents=True, exist_ok=True)
    p = DEMO_CACHE / f"{c['facts_hash']}.json"
    raw = [{k: v for k, v in o.items() if k not in ("id", "status")} for o in c["objections"]]
    p.write_text(json.dumps({"model": c["model"], "prompt_version": PROMPT_VERSION, "objections": raw,
                             "tool_calls": c["tool_calls"],
                             "created": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                            ensure_ascii=False, indent=1, default=str))
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def _short(call: dict) -> str:
    r, a = call["result"], call["args"]
    arg = ", ".join(a["tickers"]) if "tickers" in a else a.get("strategy") or a.get("name") or (
        f"{len(a['weights'])} holdings" if "weights" in a else "")
    if isinstance(r, dict) and "error" in r:
        res = "error: " + r["error"][:60]
    elif call["tool"] == "correlation_between" and r.get("pairs"):
        res = ", ".join(f"{p['a']}/{p['b']} {p['correlation']:.2f}" for p in r["pairs"][:2])
    elif call["tool"] == "strategy_checks":
        res = f"{sum(c['status'] == 'warn' for c in r.get('checks', []))} warning(s)"
    elif call["tool"] in ("portfolio_stats", "stress_test"):
        k = "max_drawdown" if "max_drawdown" in r else "deepest_drop"
        res = f"{k} {r.get(k, 0):.1%}"
    elif call["tool"] == "look_through" and r.get("exposures"):
        e = next((x for x in r["exposures"] if x.get("cap")), r["exposures"][0])
        res = f"{e['name']} {e['weight']:.1%}" + (f" vs cap {e['cap']:.1%}" if e.get("cap") else "")
    elif call["tool"] == "risk_contributions" and r.get("holdings"):
        h = r["holdings"][0]
        res = f"{h['ticker']} {h['weight']:.1%} of the money, {h['risk_share']:.1%} of the risk"
    else:
        res = json.dumps(r, default=str)[:60]
    return f"{call['call_id']} {call['tool']}({arg}) → {res}"


def add_to_trace(res: dict, profile: dict, provider: str | None = None, rets=None, holdings=None) -> dict:
    """Run the Critic on a pipeline result, apply at most one fix per strategy (Portfolio), re-check (Guardian), and
    append the hand-offs to res['trace']. Revised strategies replace the originals in res['strategies']."""
    from . import portfolio
    from .trace import describe_checks

    strategies = res.get("strategies") or []
    if not strategies:
        return {}
    if holdings is None:
        from ..holdings import holdings as load_holdings
        holdings = load_holdings()
    limits = res["limits"]
    c = review(strategies, limits, profile, provider, rets=rets, holdings=holdings)
    revised, cons, later = set(), {}, []
    for o in c["objections"]:
        if o["status"] != "valid":
            continue
        k, act = o["strategy"], o["action"]
        idx = next(i for i, s in enumerate(strategies) if s["key"] == k)
        if act["type"] == "disclose" or k in revised:
            o["status"] = "disclosed" + (" (one fix per strategy already applied)" if k in revised else "")
        else:
            with _tool_returns(rets):
                new, how = portfolio.revise(strategies[idx], act, profile, limits, rets=rets, holdings=holdings)
            if new is None:
                o["status"] = f"disclosed (fix not applied: {how})"
            else:
                g = guardian.check_strategy(new, limits, profile, holdings)
                v = guardian.verdict(g)
                dd, lim = abs(new["stats"]["max_drawdown"]), limits["loss_limit"]
                if v == "fail" or dd > lim + 1e-9:
                    why = ", ".join(f"{x['rule']} {x['detail']}" for x in g if x["status"] == "fail") or \
                        f"worst drop {dd:.1%} > loss limit {lim:.0%}"
                    o["status"] = f"kept, justified: the fix would break {why}"
                else:
                    new["guardian"] = dict(verdict=v, checks=g)
                    strategies[idx] = new
                    revised.add(k)
                    o["status"] = f"revised: {how}"
                    later.append(("Portfolio", "Guardian",
                                  f"'{new['name']}' recomputed on the Critic's objection {o['id']} ({how}): "
                                  f"{new['split']['growth']:.0%} growth, worst drop {new['stats']['max_drawdown']:.1%} "
                                  f"vs loss limit {lim:.0%}", dict(output=new)))
                    later.append(("Guardian", "Explainer", f"'{new['name']}' (revised): "
                                  + describe_checks("Portfolio", g, v), dict(checks=g)))
        if not o["status"].startswith("revised"):
            cons.setdefault(k, []).append(o["claim"])
    for s in strategies:
        s["cons"] = list(s.get("cons") or []) + cons.get(s["key"], [])
    calls = "; ".join(_short(x) for x in c["tool_calls"]) or "no tool call"
    n = sum(o["status"] != "valid" and not o["status"].startswith("dropped") for o in c["objections"])
    src = c["source"] + (f"; {c['note']}" if c["note"] and c["note"] != "mock mode" else "")
    marks = [{"rule": o["id"], "status": "pass" if o["status"].startswith("revised") else "warn",
              "text": f"{o['strategy']}: {o.get('claim', '')}", "detail": o["status"]} for o in c["objections"]]
    res["trace"].step("Critic", "Portfolio", f"{len(c['tool_calls'])} tool call(s): {calls}. {n} objection(s) "
                             f"kept ({src}).", output=c, checks=marks)
    for agent, to, summary, kw in later:
        res["trace"].step(agent, to, summary, **kw)
    res["critic"] = c
    return c
