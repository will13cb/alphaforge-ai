"""Explainer (layer 5): a Strands agent on Amazon Bedrock (Claude Opus 5.5) that writes the client text.

In:  the strategies (contract §2), the client's limits with their written reasons, the profile.
Out: plain-language text, checked by the Guardian against G11 (disclaimer), G12 (every % traced to a computed
     number) and G13 (every refused request explained). "The LLM argues, code enforces" (#2): if the agent's text
     fails a check, the deterministic template below is used instead and the trace says why.

The agent gets ONE tool, `check_text`, which runs those same Guardian rules on its draft, so it can fix its own text
before answering (capped by the prompt; the Guardian re-checks the final text anyway).

Modes (LLM_PROVIDER, like dh.llm):
- `bedrock`: committed demo cache → local cache → Strands agent (model id from BEDROCK_EXPLAINER_MODEL_ID, else
  BEDROCK_MODEL_ID; copy it from the Bedrock console in us-east-1). Answers are cached by a hash of the facts.
- `mock` (default, tests, offline demo): committed demo cache if the facts match, else the deterministic template.

Demo cache: `python -m dh explain <persona> --save-demo` (with Bedrock) writes cache/explainer/<hash>.json, committed,
so the demo replays the real Opus text without AWS (the account closes Monday).
Rule 5 exception (decision #23): Strands calls Bedrock itself, not through dh.llm.ask; caching is done here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone

from ..data import ROOT
from ..data import DEFAULT_LABEL, period, period_label, proxies_used
from ..personas import DISCLAIMER
from . import guardian

PROMPT_VERSION = "explainer-v5"  # v4: {nK} ids for every number (strict G12); v5: data window from the data (#31),
#                                  risk levels and what sets each split (#32, #33)
DEMO_CACHE = ROOT / "cache" / "explainer"      # committed: demo replays offline
LOCAL_CACHE = ROOT / ".cache" / "explainer"    # gitignored
MAX_CHECKS = 3
# Verified on the event account (CONTEXT.md, make bedrock-check): the default, so the committed demo cache replays
# without a .env (judges, teammates, Friday without AWS). Override with BEDROCK_EXPLAINER_MODEL_ID.
from ..llm import DEFAULT_MODEL_ID  # noqa: E402  (one default for every agent, dh.llm)

SYSTEM_PROMPT = f"""You write the explanation a fictional investor reads at the end of an investment-analysis
simulation. You are given FACTS as JSON: the client's profile, their limits with the reasons behind each, and up to
three strategies already computed and approved by deterministic rules.

Write for this client, in plain English, at most 350 words, with five short sections:
1. What we looked at (data and period). 2. What we found about you (limits and why). 3. Your request (if any).
4. The strategies, compared (their risk level, split and what set it, worst historical drop, the sell-offs listed
in FACTS.stress_windows, chance of a loss). 5. Limits of this analysis and
what would change the answer.
If FACTS has existing_portfolio, add after section 3 a section "The portfolio you already have": what we measured,
its worst drop and the limits it breaks, what we see, every stand-in (held fund measured with another fund, and why)
and every holding left out for lack of data, then the rebuilt version and its largest changes (a simulation).

Hard rules:
- NEVER write a number yourself: no digits at all, and no spelled-out amounts ("eight percent"). Every number in
  FACTS (percentages, dollars, ages, years, dates, levels) has been replaced by an id like {{n7}}; their values are
  listed in NUMBERS so you can compare them. In your text, write the id exactly (e.g. "its worst drop was {{n7}}") and
  the system fills in the value. Any digit you type yourself is rejected. Never compute, estimate or invent a number.
  Don't number your sections; use bold headings.
- Every request in FACTS.requests_not_included must be named with its reason, in a respectful, factual tone: the
  client asked for something reasonable-sounding, so never write "refused", "rejected", "denied" or "not allowed".
  Say what the data shows (its worst drop and what that weight alone would have cost), how that compares with the
  limit the client gave, and how much would fit. The client can still decide; we only show what fits their limits.
- The caps are computed for this client and each asset (FACTS.limits.how_caps_work), not fixed rules: say so
  briefly when you mention one.
- Past numbers describe FACTS.period only; never present them as predictions or promises.
- When FACTS says a split was set by a rule (e.g. the horizon rule), say it is a rule, not something the data showed.
- Do not tell the client to buy or sell; this is a simulation, not advice.
- End with this sentence, verbatim: "{DISCLAIMER}"
- Before answering, call check_text on your full draft. Fix every problem it lists and check again, at most
  {MAX_CHECKS} calls in total. Then answer with the final text only, no preamble.
"""


# ---- facts: the only thing the Explainer may quote ----------------------------------------------------

def _pct(x) -> str | None:
    return None if x is None else f"{100 * x:.1f}%"


def refused(limits: dict) -> list[dict]:
    """Requests not included, with the numbers behind each (Profiler's request_checks, decision #24)."""
    out = []
    for r in limits.get("request_checks") or []:
        out.append({"ticker": r["ticker"], "asked": _pct(r.get("asked")), "worst_drop": _pct(r.get("worst_drop")), "measured_on": r.get("window"),
                    "that_weight_alone_would_have_cost": _pct(r.get("loss_at_asked")),
                    "fits_up_to": _pct(r.get("fits_up_to")), "reason": r["reason"]})
    if not out:  # older limits without request_checks: parse the flags
        for f in limits.get("flags", []):
            m = re.match(r"request (\S+?):? (\S+%)?:? ?(.*)", f)
            if f.startswith("request ") and m:
                out.append({"ticker": m.group(1).rstrip(":"), "asked": m.group(2), "reason": m.group(3)})
    return out


def _caps_shown(strategies: list[dict], limits: dict, profile: dict) -> dict:
    """Caps of the companies held or requested (all caps would be noise)."""
    caps = limits.get("company_caps") or {}
    held = {t for s in strategies for t in s["weights"]} | set(profile.get("requested_positions") or {})
    return {t: _pct(caps[t]) for t in sorted(held) if t in caps}


def _dividend_facts(weights: dict) -> dict:
    """Research mode (decision #41): the dividends of the single companies held, judged on 3 years of earnings.
    {} by default, so the demo's facts (and their cache hash) are unchanged. Numbers become ids for strict G12."""
    from ..data import load_config
    if not load_config().extra:
        return {}
    from .. import fundamentals
    held = fundamentals.held_dividends(weights)
    if not held:
        return {}
    return {"dividends": [{"ticker": h["ticker"], "status": h["status"],
                           "share_of_3y_earnings_paid": _pct(h["payout_3y"]), "reason": h["reason"]} for h in held],
            "dividends_rule": f"a dividend is covered when it is at most {1 / fundamentals.COVERAGE_THIN:.0%} of the "
                              f"last {fundamentals.YEARS} years' earnings (team rule, not a regulation)"}


def _money(x) -> str | None:
    return f"{x:,.0f} $" if isinstance(x, (int, float)) else None


def _existing_facts(r: dict | None) -> dict | None:
    """The client's current portfolio, reviewed (branch portefeuille_existant). None → no key in the facts, so the
    hash (and the demo caches) of a run without an existing portfolio is unchanged."""
    if not r or not r.get("current"):
        return None
    c, t = r["current"], r.get("target") or {}
    side = lambda v: {"worst_drop": _pct(v.get("max_drawdown")), "worst_drop_cad": _money(v.get("drawdown_cad")),
                      "return_2022": _pct(v.get("return_2022")), "volatility": _pct(v.get("ann_vol")),
                      "growth": _pct(v.get("growth")), "limits_broken": [f["id"] for f in v.get("fails", [])]}
    return {
        "measured_cad": _money(r.get("assessed_cad")), "entered_cad": _money(r.get("total_cad")),
        "today": side(c), "rebuilt_as": t.get("name"), "rebuilt": side(t) if t else None,
        "what_we_see": r.get("critique", [])[:8],
        "stand_ins": [{"held": s["ticker"], "measured_with": s["measured_with"], "why": s["closeness"],
                       "currency_hedge_simulated": s["hedged"],
                       **({"hedge_effect_worst_drop": {k: _pct(v) for k, v in s["hedge_effect"]["max_drawdown"].items()}}
                          if s.get("hedge_effect") else {}),
                       **({"checked_against_real_fund": {
                           "window": s["checked_against_real"]["window"],
                           "real_worst_drop": _pct(s["checked_against_real"]["real_worst_drop"]),
                           "stand_in_worst_drop": _pct(s["checked_against_real"]["stand_in_worst_drop"])}}
                          if s.get("checked_against_real") else {})} for s in r.get("stand_ins") or []],
        "stand_in_limits": r.get("limits_of_stand_ins"),
        "no_data_left_out": r.get("not_assessable") or [],
        "fees_a_year": ({"today": _money(r["fees"]["today"]["total_cad"]),
                         "today_share": _pct(r["fees"]["today"]["weighted_mer"]),
                         "rebuilt": _money((r["fees"].get("rebuilt") or {}).get("total_cad")),
                         "unknown_for": r["fees"]["today"]["unknown"], "source": r["fees"]["today"]["source"]}
                        if r.get("fees") else None),
        "look_through_not_opened": (r.get("look_through") or {}).get("not_opened", []),
        "largest_changes": [{"holding": m["ticker"], "held_as": m.get("held") or None, "today": _money(m["now_cad"]),
                             "rebuilt": _money(m["target_cad"]), "change": _money(m["change_cad"]),
                             "action": m["action"]} for m in (r.get("moves") or [])[:5]],
    }


def facts(strategies: list[dict], limits: dict, profile: dict) -> dict:
    """Everything the Explainer may say, numbers pre-formatted as the text should show them."""
    p, label = period(), period_label()
    strats = []
    for s in strategies:
        st, r = s.get("stats", {}), s.get("split_range", {})
        o = (s.get("outlook") or {}).get("risk_only") or {}
        top = sorted(s["weights"].items(), key=lambda kv: -kv[1])[:6]
        strats.append({
            "name": s["name"],
            "risk_level_choice": (s.get("level") or {}).get("label"),
            "growth": _pct(s["split"]["growth"]), "defensive": _pct(s["split"]["defensive"]),
            "split_set_by": r.get("set_by_text"),
            "worst_drop_test_alone_would_allow": (_pct(r.get("data_ceiling")) if r.get("set_by") not in (None, "worst_drop")
                                                  else None),
            "ceiling": _pct(r.get("ceiling")), "goal_floor": _pct(r.get("floor")),
            "conflict_message": r.get("conflict_message"),
            "worst_drop": _pct(st.get("max_drawdown")), "return_2022": _pct(st.get("return_2022")),
            "stress_2022": _pct(st.get("stress_2022")), "volatility": _pct(st.get("ann_vol")),
            **{k: _pct(st[k]) for k in ("stress_2008", "stress_2020") if st.get(k) is not None},
            "chance_of_loss_risk_only": _pct(st.get("prob_loss")),
            "chance_of_target_risk_only": _pct(o.get("prob_target")),
            # decision R1: the loss rule is simulated over the client's horizon; the worst drop above is OBSERVED
            "chance_of_drop_beyond_loss_limit_simulated": _pct((s.get("risk") or {}).get("exceedance")),
            "allowed_chance_of_drop_beyond_loss_limit": _pct((s.get("risk") or {}).get("alpha")),
            "one_in_ten_drop_over_horizon_simulated": _pct((s.get("risk") or {}).get("drop_1_in_10")),
            "goal_status": ((r.get("goal") or {}).get("status") or "").replace("_", " ") or None,
            "chance_of_target_central": _pct(((s.get("outlook") or {}).get("central") or {}).get("prob_target")),
            "top_holdings": {t: _pct(w) for t, w in top},
            "why": [a for a in s.get("adjustments", []) if not a.startswith("offered")][:4],
            **_dividend_facts(s["weights"]),
        })
    out = {
        "client": {"name": profile.get("name"), "age": profile.get("age"), "horizon_years": profile.get("horizon_years"),
                   "objective": profile.get("objective"),
                   "capital_cad": f"{profile['capital']:,.0f} $" if profile.get("capital") else None,
                   "max_loss_accepted": f"{profile['max_loss_pct']:.0f}%" if profile.get("max_loss_pct") else None,
                   "requested": {t: _pct(w) for t, w in (profile.get("requested_positions") or {}).items()}},
        "limits": {"risk_level": limits.get("risk_level"), "risk_name": limits.get("risk_name"),
                   "loss_limit": _pct(limits.get("loss_limit", limits.get("max_drawdown"))),
                   "loss_limit_cad": f"{limits['loss_limit_cad']:,} $" if limits.get("loss_limit_cad") else None,
                   "defensive_floor": _pct(limits.get("min_defensive")),
                   "company_caps": _caps_shown(strategies, limits, profile),
                   "how_caps_work": f"computed for this client and each asset: one company's own worst {label} drop "
                                    "may cost at most a quarter of the loss limit, and no company above a fifth of "
                                    "what the client can hold in stocks",
                   "crypto_cap": _pct(limits.get("max_crypto")),
                   "knowledge_score": limits.get("knowledge_score"), "reasons": limits.get("reasons", [])},
        "requests_not_included": refused(limits),
        "strategies": strats,
        "period": label.replace("-", "–"), "stress_year": "2022",
        "stress_windows": ["2022 (Jan-Oct)"] + [w for w, k in (("2008-2009", "stress_2008"), ("2020 (Feb-Mar)", "stress_2020"))
                                               if any(k in (s.get("stats") or {}) for s in strategies)],
        "data": (f"Daily prices {p[0]} to {p[1]} " if p else "Daily prices ")
                + ("(Yahoo Finance via the organizers' starter pack), " if label == DEFAULT_LABEL else
                   "(Yahoo Finance via the organizers' build script, longer window), ")
                + "Bank of Canada USD/CAD; all returns in CAD." + (" Stand-ins before an asset's first price: "
                + "; ".join(proxies_used()) + "." if proxies_used() else ""),
        "disclaimer": DISCLAIMER,
    }
    ex = _existing_facts(limits.get("existing_review"))
    if ex:
        out["existing_portfolio"] = ex
    return out


def facts_hash(f: dict, model_id: str = "") -> str:
    return hashlib.sha256(json.dumps([PROMPT_VERSION, model_id, f], sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---- the Guardian checks, on all strategies at once ----------------------------------------------------

def _combined(strategies: list[dict]) -> dict:
    """One pseudo-strategy holding every number the text may quote (G12 matches each % against these)."""
    w, st = {}, {}
    for s in strategies:
        k = s.get("key", s["name"])
        w.update({f"{k}|{t}": v for t, v in s["weights"].items()})
        for name, v in (s.get("stats") or {}).items():
            if isinstance(v, (int, float)):
                st[f"{k}|{name}"] = v
        st[f"{k}|growth"], st[f"{k}|defensive"] = s["split"]["growth"], s["split"]["defensive"]
        r = s.get("split_range") or {}
        for name in ("ceiling", "floor"):
            if r.get(name) is not None:
                st[f"{k}|{name}"] = r[name]
        o = (s.get("outlook") or {}).get("risk_only") or {}
        if o.get("prob_target") is not None:
            st[f"{k}|prob_target"] = o["prob_target"]
    return {"weights": w, "stats": st}


# Any % or $ amount, however written ("-8.6%", "−8.6 %", "60,000 $", "$60,000").
NUM = re.compile(r"[-−]?\d[\d,]*(?:\.\d+)?\s?(?:%|per\s?cents?\b|pct\b|percentage points?\b)"
                 r"|\d[\d,]*(?:\.\d+)?\s?(?:\$|dollars?\b|CAD\b|USD\b|k\s?\$)"
                 r"|(?:\$|CAD\s|USD\s)\s?\d[\d,]*(?:\.\d+)?", re.I)
PLACEHOLDER = re.compile(r"\{(n\d+)\}")
# Every number the agent could need, as one token: dates and periods first, then %/$ amounts, then plain numbers.
ANY_NUM = re.compile(r"\d{4}-\d{2}-\d{2}|\d{4}[-–]\d{4}|" + NUM.pattern + r"|[-−]?\d[\d,]*(?:\.\d+)?", re.I)
WORD_PCT = re.compile(r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|"
                      r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|half|quarter)\b[\w\s-]{0,25}?"
                      r"\b(?:per\s?cent|percentage|dollars?)\b", re.I)


def _norm(tok: str) -> str:
    """Canonical form of a number token, so "−8.6 %", "-8.6 percent" and "-8.6%" compare equal, and "60,000 $",
    "$60,000", "60,000 dollars" and "CAD 60,000" too (only the writing is normalised, never the value)."""
    t = tok.lower().replace("−", "-").replace(",", "")
    num = re.search(r"-?\d+(?:\.\d+)?", t).group(0)
    return num + ("%" if re.search(r"%|per\s?cent|pct|percentage", t) else "$")


def placeholders(f: dict) -> tuple[dict, dict[str, str]]:
    """Facts with every % / $ value replaced by an id {nK}, and the table {nK: value} (same value → same id)."""
    table, ids = {}, {}

    def sub(m):
        v = m.group(0)
        if v not in ids:
            ids[v] = f"n{len(ids) + 1}"
            table[ids[v]] = v
        return "{" + ids[v] + "}"

    def walk(o):
        if isinstance(o, bool) or o is None:
            return o
        if isinstance(o, (int, float)):
            return walk(f"{o:g}")
        if isinstance(o, str):
            return ANY_NUM.sub(sub, o)
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return o

    return walk(f), table


def render(raw: str, table: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: table.get(m.group(1), m.group(0)), raw)


def strict_problems(raw: str, table: dict[str, str]) -> list[str]:
    """The agent's draft (with ids): any digit it typed itself, a spelled-out amount, or an id that doesn't exist is a
    problem. Only the disclaimer is exempt (copied verbatim, no digits)."""
    rest = PLACEHOLDER.sub("", raw)
    typed = re.findall(r"\S*\d\S*", rest) + [m.group(0) for m in WORD_PCT.finditer(rest)]
    unknown = sorted({m for m in PLACEHOLDER.findall(raw) if m not in table})
    out = []
    if typed:
        out.append("typed numbers instead of ids: " + ", ".join(typed[:6]))
    if unknown:
        out.append("ids not in NUMBERS: " + ", ".join(unknown[:6]))
    return out


def check(text: str, strategies: list[dict], limits: dict, profile: dict, f: dict | None = None) -> list[dict]:
    """G11–G13 on the whole client text. G12 is EXACT: every % / $ in the text must be one of the values written in
    the facts the Explainer was given (no tolerance), so a made-up number can't pass by being close to a real one."""
    f = facts(strategies, limits, profile) if f is None else f
    allowed = {_norm(v) for v in placeholders(f)[1].values()}
    out = guardian.check_explanation(text, _combined(strategies), limits, profile)
    bad = [t for t in NUM.findall(text) if _norm(t) not in allowed]
    for c in out:
        if c["rule"] == "G12":
            c.update(status="pass" if not bad else "fail",
                     detail="every number is one of the computed facts, exactly" if not bad else
                     "not in the computed facts: " + ", ".join(bad[:6]))
    return out


# ---- deterministic template (mock mode, and the fallback when the agent's text fails a check) ----------

def template(f: dict) -> str:
    c, lim = f["client"], f["limits"]
    out = [f"**{c['name'] or 'Client'}, here is what this simulation found.**", "",
           f"**What we looked at.** {f['data']}", "",
           f"**What we found about you.** Your loss limit is {lim['loss_limit']}"
           + (f" ({lim['loss_limit_cad']})" if lim.get("loss_limit_cad") else "")
           + f": risk level {lim['risk_level']} ({lim['risk_name']}). At least {lim['defensive_floor']} stays in "
             f"defensive assets and crypto is capped at {lim['crypto_cap']}. Caps on one company are {lim['how_caps_work']}."]
    if f["requests_not_included"]:
        out += ["", "**Your request.**"]
        for r in f["requests_not_included"]:
            out.append(f"You asked for {r['asked'] or ''} in {r['ticker']}. {r['reason'][:1].upper()}{r['reason'][1:]}. "
                       f"The strategies below stay within that; the choice remains yours.".replace("for  in", "for"))
    ex = f.get("existing_portfolio")
    if ex:
        out += _template_existing(ex)
    out += ["", "**The strategies.** Up to three options, from the most growth your limits allow to the least in "
                "stocks; less in stocks is not always a smaller past drop, so compare the drops. The choice is yours."]
    for s in f["strategies"]:
        line = f"- **{s['name']}**: {s['growth']} growth, {s['defensive']} defensive"
        if s.get("split_set_by"):
            line += f", set by {s['split_set_by']}"
            if s.get("worst_drop_test_alone_would_allow"):
                line += f" (the loss test alone would allow {s['worst_drop_test_alone_would_allow']})"
        line += f". Worst historical drop {s['worst_drop']} (your limit {lim['loss_limit']})"
        for k, lab in (("stress_2008", "in 2008-2009"), ("stress_2020", "in the 2020 crash")):
            if s.get(k):
                line += f"; {lab} it returned {s[k]}"
        if s["return_2022"]:
            line += f"; in {f['stress_year']} it returned {s['return_2022']}"
        if s["chance_of_loss_risk_only"]:
            line += f"; chance of ending below what you put in, without assuming past returns repeat: " \
                    f"{s['chance_of_loss_risk_only']}"
        out.append(line + ".")
        if s.get("dividends"):
            out.append("  Dividends of the companies held: " + "; ".join(
                f"{d['ticker']} {d['status']}" + (f" ({d['share_of_3y_earnings_paid']} of 3 years' earnings)"
                                                  if d.get("share_of_3y_earnings_paid") else "")
                for d in s["dividends"]) + f". Rule: {s['dividends_rule']}.")
        if s["conflict_message"]:
            out.append(f"  {s['conflict_message']}")
    out += ["", f"**Limits of this analysis.** These numbers describe {f['period']} only; they are not predictions. "
                "A longer horizon, a different loss limit or new money needed soon would change the answer.",
            "", f["disclaimer"]]
    return "\n".join(out)


def _template_existing(ex: dict) -> list[str]:
    t, r = ex["today"], ex.get("rebuilt")
    out = ["", "**The portfolio you already have.** We measured " + ex["measured_cad"]
           + (f" of the {ex['entered_cad']} you entered" if ex["entered_cad"] != ex["measured_cad"] else "")
           + f". Its worst historical drop was {t['worst_drop']}"
           + (f" (about {t['worst_drop_cad']})" if t.get("worst_drop_cad") else "")
           + (f"; limits it breaks: {', '.join(t['limits_broken'])}." if t["limits_broken"] else
              "; it stays within your limits.")]
    out += [f"- {line}" for line in ex["what_we_see"]]
    for s in ex["stand_ins"]:
        line = (f"- {s['held']} is not in our data: it is measured with {s['measured_with']} ({s['why']})"
                + (", with its currency hedge simulated" if s["currency_hedge_simulated"] else ""))
        h = s.get("hedge_effect_worst_drop")
        if h:
            line += f"; worst drop {h['hedged']} hedged vs {h['unhedged']} without the hedge"
        v = s.get("checked_against_real_fund")
        if v:
            line += (f". Checked against {s['held']}'s own prices ({v['window']}): its real worst drop was "
                     f"{v['real_worst_drop']}, the stand-in's {v['stand_in_worst_drop']}")
        out.append(line + ".")
    if ex["stand_ins"]:
        out.append(f"  Limits of these stand-ins: {ex['stand_in_limits']}.")
    if ex["no_data_left_out"]:
        out.append(f"- No data for {', '.join(ex['no_data_left_out'])}: left out of these numbers.")
    fy = ex.get("fees_a_year")
    if fy and fy.get("today"):
        out.append(f"- Fund fees: about {fy['today']} a year ({fy['today_share']} of what we measured)"
                   + (f"; rebuilt, about {fy['rebuilt']}" if fy.get("rebuilt") else "") + f" (source: {fy['source']}).")
    if r:
        out.append(f"Rebuilt as **{ex['rebuilt_as']}** with the same money, its worst drop would have been "
                   f"{r['worst_drop']}" + (f" (about {r['worst_drop_cad']})" if r.get("worst_drop_cad") else "")
                   + (". " if not r["limits_broken"] else f", still breaking {', '.join(r['limits_broken'])}. ")
                   + "Largest changes, as a simulation: " + "; ".join(
                       f"{m['holding']}{' (held as ' + ', '.join(m['held_as']) + ')' if m.get('held_as') else ''} "
                       f"{m['today']} → {m['rebuilt']}" for m in ex["largest_changes"]) + ".")
    return out


# ---- Strands agent on Bedrock ---------------------------------------------------------------------------

def model_id() -> str:
    return os.getenv("BEDROCK_EXPLAINER_MODEL_ID") or os.getenv("BEDROCK_MODEL_ID") or DEFAULT_MODEL_ID


def _run_agent(f: dict, strategies: list[dict], limits: dict, profile: dict) -> tuple[str, int]:
    """Returns (raw text with {nK} ids, number of check_text calls). Strands imported lazily (tests don't need it)."""
    from strands import Agent, tool
    from strands.models import BedrockModel

    calls = {"n": 0}
    tf, table = placeholders(f)

    @tool
    def check_text(text: str) -> dict:
        """Run the Guardian's G11-G13 checks on a draft: disclaimer present, every % traced, refusals explained.
        Returns the failing checks (empty list = all good)."""
        calls["n"] += 1
        if calls["n"] > MAX_CHECKS:
            return {"error": f"check limit ({MAX_CHECKS}) reached: answer now"}
        problems = strict_problems(text, table)
        bad = [c for c in check(render(text, table), strategies, limits, profile, f) if c["status"] == "fail"]
        return {"failing": [{"rule": "G12", "detail": p} for p in problems]
                           + [{"rule": c["rule"], "detail": c["detail"]} for c in bad]}

    model = BedrockModel(model_id=model_id(), region_name=os.getenv("AWS_REGION", "us-east-1"), max_tokens=16000)
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[check_text], callback_handler=None)
    res = agent("FACTS:\n" + json.dumps(tf, ensure_ascii=False, indent=1)
                + "\n\nNUMBERS (write the id, never the value):\n" + json.dumps(table, ensure_ascii=False, indent=1))
    return str(res).strip(), calls["n"]


# ---- entry point -----------------------------------------------------------------------------------------

def _cache_paths(h: str):
    return DEMO_CACHE / f"{h}.json", LOCAL_CACHE / f"{h}.json"


def explain(strategies: list[dict], limits: dict, profile: dict, provider: str | None = None) -> dict:
    """{text, raw, source, model, checks, verdict, check_calls, facts_hash, note}. Never raises on agent failure:
    falls back to the template and says why. The agent writes ids ({nK}); code fills in the values (strict G12)."""
    provider = (provider or os.getenv("LLM_PROVIDER", "mock")).lower()
    f = facts(strategies, limits, profile)
    _, table = placeholders(f)
    mid = model_id()
    h = facts_hash(f, mid)
    result = None
    for p in _cache_paths(h):  # committed demo cache first, then local cache
        if p.exists():
            c = json.loads(p.read_text())
            result = dict(raw=c.get("raw", c["text"]), source=f"cache ({p.parent.name})", model=c["model"],
                          check_calls=c.get("check_calls", 0), note="")
            break
    if result is None and provider == "bedrock":
        try:
            raw, n = _run_agent(f, strategies, limits, profile)
            result = dict(raw=raw, source="bedrock", model=mid, check_calls=n, note="")
            LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
            _cache_paths(h)[1].write_text(json.dumps(
                {"model": mid, "prompt_version": PROMPT_VERSION, "raw": raw, "text": render(raw, table),
                 "check_calls": n, "created": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                ensure_ascii=False, indent=1))
        except Exception as e:  # noqa: BLE001 — any AWS/Strands error → template, reported in the trace
            result = dict(raw=None, source="template", model="", check_calls=0,
                          note=f"agent unavailable ({type(e).__name__}: {e})"[:300])
    if result is None:
        result = dict(raw=None, source="template", model="", check_calls=0, note="mock mode")

    problems = strict_problems(result["raw"], table) if result["raw"] is not None else []
    text = render(result["raw"], table) if result["raw"] is not None else template(f)
    checks = check(text, strategies, limits, profile, f)
    if result["source"] != "template" and (problems or guardian.verdict(checks) == "fail"):  # code enforces
        bad = problems + [f"{c['rule']} ({c['detail']})" for c in checks if c["status"] == "fail"]
        result = dict(raw=None, source="template", model="", check_calls=result["check_calls"],
                      note=f"agent text failed: {'; '.join(bad)[:250]}; replaced by the template")
        text = template(f)
        checks = check(text, strategies, limits, profile, f)
    return {**result, "text": text, "checks": checks, "verdict": guardian.verdict(checks), "facts_hash": h}


def save_demo(e: dict) -> str:
    """Copy a Bedrock answer into the committed demo cache (so the demo replays it offline)."""
    if e["source"] == "template":
        raise ValueError(f"nothing to save: the text came from the template ({e['note']})")
    DEMO_CACHE.mkdir(parents=True, exist_ok=True)
    p = DEMO_CACHE / f"{e['facts_hash']}.json"
    p.write_text(json.dumps({"model": e["model"], "prompt_version": PROMPT_VERSION, "raw": e["raw"], "text": e["text"],
                             "check_calls": e["check_calls"],
                             "created": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                            ensure_ascii=False, indent=1))
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def add_to_trace(res: dict, profile: dict, provider: str | None = None) -> dict:
    """Run the Explainer on a pipeline result and append its two hand-offs to res['trace'] (no pipeline.py change)."""
    from .trace import describe_checks

    if res.get("fixed_income_scenario"):
        from ..fixed_income import explanation as fixed_explanation
        text = fixed_explanation(res["fixed_income_scenario"])
        e = dict(text=text, source="fixed_rate", model="", check_calls=0, checks=[], verdict="warn",
                 facts_hash="", note="Sourced fixed-income lookup and deterministic cash-flow illustration; purchase quote required.")
        res["trace"].step("Fixed-income explainer", "Client", e["note"], output=text)
        res["explanation"] = e
        return e
    e = explain(res.get("strategies", []), res["limits"], profile, provider)
    src = e["source"] + (f", {e['check_calls']} self-check(s)" if e["check_calls"] else "")
    res["trace"].step("Explainer", "Guardian", f"client text ({len(e['text'])} characters, {src})"
                      + (f"; {e['note']}" if e["note"] else ""), output=e["text"])
    res["trace"].step("Guardian", "Client" if e["verdict"] != "fail" else "Explainer",
                      describe_checks("Explainer", e["checks"], e["verdict"]), checks=e["checks"])
    res["explanation"] = e
    return e
