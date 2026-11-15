"""Portfolio (layer 3): DETERMINISTIC code, not an AI agent.

Up to 3 strategies, each defined by WHAT IT HOLDS (a growth basket and a defensive basket). Its stocks/bonds split is
COMPUTED from the client and the data (decision #17), never looked up in a table:

    ceiling  = scanning growth shares up from 0% (5% steps), the last one before the first whose SIMULATED drawdown over
               the client's horizon breaks the loss limit with a probability above rules.LOSS_ALPHA (10%): stationary
               bootstrap of the data window's days, central assumption (cash + 3% on growth). Also ≤ 1 − defensive
               floor (horizon rule, money needed within 3 years, never 100% growth). Audit A1, decisions R1-R2.
               The observed worst drop of the window is still computed and SHOWN, never used as a guarantee.
    range    = the same rule on 3-year sub-windows (R2): how much the ceiling depends on the window.
    goal     = dh.risk.goals status under named assumptions (zero premium / central / replay), if a target is set; a
               minimum share only under the central assumption and never above the ceiling (audit A2, R3-R4).
    result   = each strategy at its ceiling; levels 2-3 share level 1's defensive basket and must be safer on worst
               drop and chance of loss, else they are dropped (inverted) or flagged (mixed) (audit A3, R5).

    from dh.agents.profiler import derive_limits
    from dh.agents import portfolio
    strategies = portfolio.propose(profile, derive_limits(profile))     # contract §2

Every number comes from `market.strategy_stats` / `market.goal_outlook` (Joud's lane): nothing is recomputed here.
Plan items kept from Joud's skeleton (`notes/branches/lane-portfolio.md`): P2 baskets, P3 short-term-heavy defensive
basket, P5 single names net of ETF holdings, P7 stats, P9 rounding, P10 drop + say why.
"""

from __future__ import annotations

from typing import TypedDict

import pandas as pd

from .. import data, metrics
from ..data import period_label
from ..holdings import holdings as load_holdings
from ..risk import goals as rg
from ..risk import levels as rl
from ..risk import loss_model as lm
from ..risk import sync
from . import checks as ck
from . import diversification as dv
from . import market
from .rules import (BEGINNER_MAX_KNOWLEDGE, CENTRAL_PREMIUM, CRYPTO, DEFENSIVE, DIVIDEND_PAYERS, EQUITY_ETFS, EXCLUSIONS,
                    GOAL_LOW_PROB, GOAL_MIN_PROB, LOSS_ALPHA, MAX_COUNTRY_EQUITY, SENSITIVITY_STEP_YEARS,
                    SENSITIVITY_YEARS, STOCKS)

MAX_STRATEGIES = 3
STEP = 0.05                   # growth-share grid for the split search
ROUND_TO = 0.005              # P9: weights in 0.5% steps
N_SEARCH, N_FINAL = 500, 2000  # goal scenarios while searching the minimum share / for the final strategy
N_LOSS, N_LOSS_FINAL, N_RANGE = 1000, 2000, 1000  # loss-model scenarios: ceiling scan / final check (G7) / range
MIN_HORIZON_YEARS = 0.25       # the loss model needs a horizon: money needed "now" is simulated over 3 months

# ---- A. strategies = what they hold (team choices, see notes/system-design.md block A) ------------
STRATEGY_DEFS = {
    "core": dict(
        name="Broad core",
        growth={"XIU.TO": 0.50, "SPY": 0.50},
        defensive={"ZST.TO": 0.50, "XBB.TO": 0.50},
        why="broad Canadian and U.S. stock ETFs, short and aggregate bonds"),
    "income": dict(
        name="Income / dividends",
        growth={"XIU.TO": 0.35, "RY.TO": 0.15, "TD.TO": 0.10, "FTS.TO": 0.10, "ENB.TO": 0.10, "JNJ": 0.10, "PG": 0.10},
        # single names = rules.DIVIDEND_PAYERS (checked by a test)
        defensive={"XBB.TO": 0.40, "AGG": 0.30, "ZST.TO": 0.30},
        why="dividend-paying established companies plus the TSX 60, aggregate bonds"),
    "growth": dict(
        name="Growth tilt",
        growth={"QQQ": 0.40, "SPY": 0.25, "NVDA": 0.10, "MSFT": 0.10, "GOOGL": 0.05, "BTC-USD": 0.07, "ETH-USD": 0.03},
        defensive={"ZST.TO": 0.50, "GLD": 0.50},
        why="U.S. growth/tech ETFs and a few large tech names (+ crypto only if asked, allowed and it earns its place), "
            "short bonds and gold"),
}
GROWTH_INTERESTS = {"ai", "tech", "crypto"}
SHORT_HEAVY = {"ZST.TO": 0.60, "XBB.TO": 0.20, "GLD": 0.20}   # P3: loss limit ≤ 10% (decision #13)
ESG_SWAP = {"SPY": "ESGV"}

# ---- research mode (branch produit_cadusa): only with harness.toml [data] extra set, so the demo is unchanged ----
# Each change is triggered by the client's profile or by an existing check (C2), never by a persona's name.
RESEARCH_ESG_SWAP = {"XIU.TO": "XESG.TO"}         # replace, never add: daily correlation ~0.96 with XIU (C6 ≥ 0.95)
SHORT_HORIZON_YEARS = 5                           # horizon ≤ 5 y: short-term bonds instead of aggregate (rate risk)
SHORT_HORIZON_SWAP = {"XBB.TO": "XSB.TO"}
INTERNATIONAL = {"XEF.TO": 0.75, "XEC.TO": 0.25}  # developed ex-North America / emerging, when C2 would warn
PAYER_MAX_PAYOUT = 0.80                           # income names: dividends ≤ 80% of the last 3 years' earnings


def research_mode() -> bool:
    """True when an extra product catalogue is configured (harness.toml [data] extra)."""
    return bool(data.load_config().extra)


def _covered_payers(g: dict) -> tuple[dict, list[str]]:
    """Income names keep their place only if their dividend is ≤ PAYER_MAX_PAYOUT of 3 years' earnings."""
    from .. import fundamentals
    notes, out = [], dict(g)
    for t in sorted(set(g) & DIVIDEND_PAYERS):
        try:
            cov = fundamentals.coverage(t)
        except SystemExit:
            return g, ["dividend coverage not checked (run `make data-fundamentals`)"]
        p = cov.get("payout_ratio_3y")
        if "error" in cov or p is None or p > PAYER_MAX_PAYOUT:
            out.pop(t)
            why = cov.get("error") or (f"dividends {p:.0%} of its last 3 years' earnings" if p is not None
                                       else "no earnings over its last 3 years")
            notes.append(f"{t} left out of the income names: {why} (income names stay ≤ {PAYER_MAX_PAYOUT:.0%})")
    return out, notes


def _add_international(g: dict) -> tuple[dict, list[str]]:
    """If one country would be above MAX_COUNTRY_EQUITY of the equities (C2 ⚠), move the smallest 5%-step share of
    the basket to INTERNATIONAL that brings it back to the limit."""
    eq = {t: v for t, v in g.items() if t in STOCKS or t in EQUITY_ETFS}
    if not eq or set(INTERNATIONAL) <= set(g):
        return g, []
    where = market.exposures(list(eq))

    def top(basket: dict) -> tuple[str, float]:
        e = {t: v for t, v in basket.items() if t in STOCKS or t in EQUITY_ETFS}
        by: dict[str, float] = {}
        for t, v in e.items():
            c = where.get(t) or market.exposures([t])[t]
            by[c] = by.get(c, 0.0) + v / sum(e.values())
        return max(by.items(), key=lambda kv: kv[1])

    country, share = top(g)
    if share <= MAX_COUNTRY_EQUITY + 1e-9:
        return g, []
    for k in range(1, 11):
        x = round(k * STEP, 2)
        new = {t: v * (1 - x) for t, v in g.items()}
        for t, v in INTERNATIONAL.items():
            new[t] = new.get(t, 0.0) + x * v
        c2, s2 = top(new)
        if s2 <= MAX_COUNTRY_EQUITY + 1e-9:
            return new, [f"{country} was {share:.0%} of the equities (C2 limit {MAX_COUNTRY_EQUITY:.0%}): "
                         f"{x:.0%} of the stock part moved to developed ex-North America and emerging markets "
                         f"({', '.join(INTERNATIONAL)})"]
    return g, [f"{country} {share:.0%} of the equities: international ETFs could not bring it under the C2 limit"]


class Strategy(TypedDict, total=False):
    key: str
    name: str
    risk_level: int
    weights: dict[str, float]
    split: dict[str, float]          # {"growth", "defensive"}
    split_range: dict                # {"floor", "ceiling", "liquidity_floor", "conflict", "conflict_message"}
    split_curve: list[dict]          # [{"growth", "max_drawdown", "stress_2022", "return_2022", "ann_vol"}]
    stats: dict
    outlook: dict | None
    diversification: dict
    baskets: dict                    # {"growth": {ticker: w}, "defensive": {...}} the split was computed from
    flavour: str                     # core · income · growth: which baskets (STRATEGY_DEFS key); `key` is unique
    level: dict                      # {"rank" 1-3, "label", "delta", "target_growth"} (decision #32)
    checks: list[dict]               # C-F checks (checks.py, decision #20): {check, value, limit, status, reason, source}
    adjustments: list[str]
    pros: list[str]
    cons: list[str]
    risk: dict                       # simulated loss test on the FINAL weights (G7/D2), R1
    stamps: dict                     # dh.risk.sync: which weights/data each section was computed on (A6)


# ---- helpers ---------------------------------------------------------------------------------------

def _norm(b: dict[str, float]) -> dict[str, float]:
    b = {t: w for t, w in b.items() if w > 0}
    s = sum(b.values())
    return {t: w / s for t, w in b.items()} if s > 0 else {}


def _wants_esg(profile: dict) -> bool:
    return "esg" in (profile.get("interests") or []) or "fossil_fuels" in (profile.get("exclusions") or [])


def asked_crypto(profile: dict) -> bool:
    """The client asked for crypto: listed it as an interest or requested a crypto position."""
    req = profile.get("requested_positions") or {}
    return "crypto" in (profile.get("interests") or []) or any(t in CRYPTO and w > 0 for t, w in req.items())


def crypto_decision(g: dict, dfn: dict, profile: dict, limits: dict, rets: pd.DataFrame,
                    holdings: dict) -> tuple[bool, str]:
    """Crypto stays in a growth basket only if all three hold (never added by default):
    1. asked    the client listed crypto as an interest or requested a crypto position;
    2. allowed  the Profiler gave a crypto cap > 0 (not a beginner, not excluded);
    3. model    with crypto, the computed growth ceiling (largest stock share inside the client's own loss limit,
                data window) is at least as high as without it: crypto must not cost the client stock room.
    Returns (keep, reason for the trace)."""
    if not any(t in CRYPTO for t in g):
        return False, ""
    if not asked_crypto(profile):
        return False, "crypto left out: you didn't ask for it"
    if limits.get("max_crypto", 0) <= 0 or not CRYPTO & set(limits.get("allowed_assets") or []):
        return False, "crypto left out: not allowed for this profile"
    no_goal = {**profile, "target_amount": None}  # only the ceilings are compared: skip the goal search
    without = _norm({t: w for t, w in g.items() if t not in CRYPTO})
    c_with = split_search(g, dfn, no_goal, limits, rets, holdings, with_range=False)["ceiling"]
    c_without = split_search(without, dfn, no_goal, limits, rets, holdings, with_range=False)["ceiling"]
    if c_with + 1e-9 < c_without:
        return False, (f"crypto left out: with it your loss limit {limits['loss_limit']:.0%} allows only {c_with:.0%} "
                       f"in growth assets, without it {c_without:.0%} (loss test, {period_label(rets)} data)")
    return True, (f"crypto kept (≤ {limits['max_crypto']:.1%}): you asked for it, your profile allows it, and the growth "
                  f"ceiling stays {c_with:.0%} with it vs {c_without:.0%} without ({period_label(rets)} data)")


def offered(profile: dict, limits: dict) -> list[tuple[str, str]]:
    """Which strategies to build, each with the reason (or why one is skipped)."""
    beginner = limits["knowledge_score"] <= BEGINNER_MAX_KNOWLEDGE
    out = [("core", "always offered: broad and simple")]
    if beginner:
        out.append(("-income", f"knowledge {limits['knowledge_score']} ≤ {BEGINNER_MAX_KNOWLEDGE}: broad ETFs only"))
    else:
        out.append(("income", "single names allowed (knowledge ≥ 3)"))
    wants = GROWTH_INTERESTS & set(profile.get("interests") or [])
    if asked_crypto(profile):
        wants.add("crypto")
    if wants and limits["risk_level"] >= 3 and not beginner:
        out.append(("growth", f"interest in {', '.join(sorted(wants))} and risk level {limits['risk_level']} ≥ 3"))
    else:
        out.append(("-growth", "needs an interest in ai/tech/crypto, risk level ≥ 3 and knowledge ≥ 3"))
    return out


def baskets(key: str, profile: dict, limits: dict) -> tuple[dict, dict, list[str]]:
    """Growth and defensive baskets for one strategy, restricted to the client's allowed assets."""
    d = STRATEGY_DEFS[key]
    notes = []
    g = dict(d["growth"])
    if _wants_esg(profile):
        for a, b in ESG_SWAP.items():
            if a in g:
                g[b] = g.pop(a)
                notes.append(f"{a} replaced by the ESG-screened {b} (ESG preference)")
    research = research_mode()
    if research:
        if _wants_esg(profile):
            for a, b in RESEARCH_ESG_SWAP.items():
                if a in g:
                    g[b] = g.pop(a)
                    notes.append(f"{a} replaced by the ESG-screened {b} (ESG preference)")
        g, more = _covered_payers(g)
        notes += more
    allowed = set(limits["allowed_assets"])
    dropped = sorted(t for t in g if t not in allowed)
    if dropped:
        why = {}
        for t in dropped:
            kw = next((k for k in (profile.get("exclusions") or []) if t in EXCLUSIONS.get(k, {k})), None)
            why.setdefault(f"you excluded {kw.replace('_', ' ')}" if kw else
                           "crypto isn't proposed at this knowledge level" if t in CRYPTO else
                           "not allowed for this profile", []).append(t)
        notes += [f"left out: {', '.join(ts)} ({w})" for w, ts in why.items()]
    g = _norm({t: w for t, w in g.items() if t in allowed})
    if research and set(INTERNATIONAL) <= allowed:
        g, more = _add_international(g)
        notes += more
    dfn = SHORT_HEAVY if limits["loss_limit"] <= 0.10 else d["defensive"]
    if dfn is SHORT_HEAVY:
        notes.append(f"loss limit {limits['loss_limit']:.0%} ≤ 10%: short-term-heavy defensive basket (ZST 60%)")
    horizon = profile.get("horizon_years")
    if research and isinstance(horizon, (int, float)) and horizon <= SHORT_HORIZON_YEARS:
        for a, b in SHORT_HORIZON_SWAP.items():
            if a in dfn and b in allowed:
                dfn = {(b if t == a else t): v for t, v in dfn.items()}
                notes.append(f"{a} replaced by {b} (horizon {horizon:g} years ≤ {SHORT_HORIZON_YEARS}: "
                             "short-term bonds carry less interest-rate risk)")
    dfn = _norm({t: w for t, w in dfn.items() if t in allowed})
    return g, dfn, notes


def round_weights(w: dict[str, float], step: float = ROUND_TO) -> dict[str, float]:
    """P9: round to `step`, drop zeros, put the rounding gap on the largest line so the sum is exactly 1."""
    r = {t: round(v / step) * step for t, v in w.items()}
    r = {t: v for t, v in r.items() if v > 1e-12}
    gap = 1.0 - sum(r.values())
    top = max(r, key=r.get)
    r[top] += gap
    return {t: round(v, 6) for t, v in sorted(r.items(), key=lambda kv: -kv[1])}


def build(g: dict, dfn: dict, share: float, limits: dict, holdings: dict,
          enforce_floor: bool = True) -> tuple[dict[str, float], list[str]]:
    """Weights for one growth share: combine, cap crypto, size single names net of ETF holdings (P5), round, and
    keep the defensive floor after rounding. Returns weights and what was adjusted (for the trace)."""
    notes = []
    w = {t: share * v for t, v in g.items()}
    for t, v in dfn.items():
        w[t] = w.get(t, 0.0) + (1 - share) * v
    etfs = [t for t in g if t in EQUITY_ETFS] or [t for t in g if t not in STOCKS | CRYPTO]

    def move(excess: float, src: str):
        w[src] -= excess
        targets = {t: w[t] for t in etfs if t != src} or {t: w[t] for t in dfn}
        tot = sum(targets.values())
        for t, v in targets.items():
            w[t] += excess * v / tot

    cr = sum(v for t, v in w.items() if t in CRYPTO)
    if cr > limits["max_crypto"] + 1e-12:
        scale = limits["max_crypto"] / cr if cr else 0
        for t in [t for t in w if t in CRYPTO]:
            move(w[t] * (1 - scale), t)
        notes.append(f"crypto capped at {limits['max_crypto']:.0%}")
    caps = limits.get("company_caps") or {}
    cap_of = lambda t: caps.get(t, limits["max_single"])  # noqa: E731  — each company's own cap (#24)
    for _ in range(3):  # P5: a company's direct weight + what the ETFs hold ≤ its cap
        eff = metrics.look_through(w, holdings)
        over = {t: eff[t] - cap_of(t) for t in w if t in STOCKS and eff.get(t, 0) > cap_of(t) + 1e-9}
        if not over:
            break
        for t, ex in over.items():
            via_etf = eff[t] - w[t]
            move(min(ex, w[t]), t)
            notes.append(f"{t} trimmed to its {cap_of(t):.1%} cap" + (
                f", counting the {via_etf:.1%} already held through ETFs" if via_etf > 1e-4 else ""))
    w = round_weights({t: v for t, v in w.items() if v > 1e-9})
    floor = limits["min_defensive"]
    dt = max(dfn, key=dfn.get)
    # Rounding to 0.5% (and the gap put on the largest line) can push a capped line just over its cap (e.g. crypto
    # 6.0% vs a 5.8% cap), and the Guardian would then drop the whole strategy: step capped lines down to fit.
    sink = max((t for t in w if t in etfs), key=w.get, default=dt)
    for _ in range(400):
        eff = metrics.look_through(w, holdings)
        over = [t for t in w if t in STOCKS and t != sink and eff.get(t, 0) > cap_of(t) + 1e-9]
        if sum(v for t, v in w.items() if t in CRYPTO) > limits["max_crypto"] + 1e-9:
            over.append(max((t for t in w if t in CRYPTO), key=w.get))
        if not over:
            break
        for t in over:
            d = min(ROUND_TO, w[t])
            w[t] = round(w[t] - d, 6)
            w[sink] = round(w.get(sink, 0.0) + d, 6)
        w = {t: v for t, v in w.items() if v > 1e-9}
    while enforce_floor and sum(v for t, v in w.items() if t in DEFENSIVE) < floor - 1e-9:  # rounding vs G6
        gt = max((t for t in w if t not in DEFENSIVE), key=w.get)
        w[gt] = round(w[gt] - ROUND_TO, 6)
        w[dt] = round(w.get(dt, 0.0) + ROUND_TO, 6)
    return {t: v for t, v in w.items() if v > 1e-9}, sorted(set(notes))


# ---- B. the split, computed (decision #17) ----------------------------------------------------------

def cash_daily(rets: pd.DataFrame, index: pd.Index) -> float:
    """Average daily return of cash (ZST.TO) on these days: the same cash `market.goal_outlook` uses. 0 if absent."""
    if "ZST.TO" not in rets:
        return 0.0
    z = rets["ZST.TO"].reindex(index).dropna()
    return float(z.mean()) if len(z) else 0.0


def loss_model(cash: float, n: int = N_LOSS, seed: int = 0) -> lm.StationaryBootstrapLoss:
    """The loss model of decision R1: block bootstrap over the client's horizon, central assumption."""
    return lm.StationaryBootstrapLoss(n_scenarios=n, seed=seed, assumption=rg.central(), cash_daily=cash)


def horizon_of(profile: dict) -> float:
    return max(float(profile.get("horizon_years") or 0.0), MIN_HORIZON_YEARS)


def split_search(g: dict, dfn: dict, profile: dict, limits: dict, rets: pd.DataFrame,
                 holdings: dict, with_range: bool = True) -> dict:
    """Ceiling (simulated loss test, R1), its range over sub-windows (R2), goal status (R3-R4), and the observed curve."""
    max_share = round(1 - limits["min_defensive"], 4)
    grid = [round(i * STEP, 4) for i in range(int(round(1 / STEP)) + 1)]
    built: dict[float, tuple] = {}

    def at(s: float) -> tuple[dict, list, pd.Series]:
        if s not in built:
            w, notes = build(g, dfn, s, limits, holdings, enforce_floor=s <= max_share + 1e-9)
            built[s] = (w, notes, metrics.portfolio_returns(rets[list(w)], w))
        return built[s]

    def port_at(s: float) -> pd.Series:
        return at(s)[2]

    def growth_at(s: float) -> float:
        return sum(v for t, v in at(s)[0].items() if t not in DEFENSIVE)
    cash = cash_daily(rets, port_at(0.0).index)
    horizon, limit = horizon_of(profile), limits["loss_limit"]
    dec = lm.equity_ceiling(port_at, grid, limit, horizon, LOSS_ALPHA, loss_model(cash), max_share, growth_at)
    sim = {r["share"]: r for r in dec.table}

    curve = []
    for s in grid:
        st = market.strategy_stats(at(s)[0], rets=rets)
        q = sim.get(s)
        curve.append({"growth": s, "max_drawdown": st["max_drawdown"], "stress_2022": st["stress_2022"],
                      "return_2022": st["return_2022"], "ann_vol": st["ann_vol"],
                      "exceedance": q["exceedance"] if q else None,
                      "sim_drop": q["alpha_drawdown"] if q else None})
    if dec.share is None:  # even 0% growth breaks the loss test: take the safest point and say so (G7 will block)
        ceiling = 0.0
        w, notes, _ = at(0.0)
        best = (w, market.strategy_stats(w, rets=rets),
                notes + [(f"even 0% growth: {dec.table[0]['exceedance']:.0%} chance of a drop deeper than "
                          f"{limit:.0%} over {horizon:g} years (more than {LOSS_ALPHA:.0%})")])
    else:
        ceiling = dec.share
        w, notes, _ = at(ceiling)
        best = (w, market.strategy_stats(w, rets=rets), notes)

    rng = None
    if with_range:
        wc = lm.window_ceilings(port_at, grid, limit, horizon, LOSS_ALPHA, lambda: loss_model(cash, N_RANGE),
                                SENSITIVITY_YEARS, SENSITIVITY_STEP_YEARS, max_share, growth_at)
        vals = [v for v in [*wc["by_window"].values(), dec.share] if v is not None]   # the full window counts too
        rng = {"by_window": {f"{a} to {b}": v for (a, b), v in wc["by_window"].items()},
               "full_window": dec.share, "range": (min(vals), max(vals)) if vals else None,
               "unstable": bool(vals) and max(vals) - min(vals) > 2 * STEP + 1e-9}

    goal = goal_assessment(port_at, growth_at, grid, ceiling, cash, profile)
    set_by, set_by_text, data_ceiling = what_set_the_split(dec, ceiling, max_share, limits, rets, horizon)
    conflict = goal is not None and goal["status"] in (rg.GoalStatus.ONLY_FAVOURABLE.value,
                                                       rg.GoalStatus.LOW_PROBABILITY.value,
                                                       rg.GoalStatus.IMPOSSIBLE.value)
    msg = goal_message(goal, ceiling, set_by_text, rets) if conflict else None
    return {"curve": curve, "ceiling": ceiling, "floor": goal["min_share"] if goal else None, "best": best,
            "conflict": conflict, "conflict_message": msg, "liquidity_floor": limits.get("liquidity_floor", 0.0),
            "max_share": max_share, "set_by": set_by, "set_by_text": set_by_text, "data_ceiling": data_ceiling,
            "exceedance": sim[ceiling]["exceedance"] if ceiling in sim else None, "alpha": LOSS_ALPHA,
            "horizon_years": horizon, "range": rng, "goal": goal}


def goal_assessment(port_at, growth_at, grid: list[float], ceiling: float, cash: float, profile: dict) -> dict | None:
    """dh.risk.goals on this strategy's baskets: curves under zero premium (0% only), central and replay, up to the
    ceiling; the status and, when it applies, the smallest share that reaches the goal. None without a target."""
    target, capital = profile.get("target_amount"), profile.get("capital")
    if not (target and capital):
        return None
    shares = [s for s in grid if s <= ceiling + 1e-9]
    kw = {"cash_daily": cash, "capital": capital, "horizon_years": horizon_of(profile), "target": target,
          "monthly_contribution": profile.get("monthly_contribution") or 0.0, "n_scenarios": N_SEARCH,
          "growth_of": growth_at}
    central = rg.central()
    curves = {rg.ZERO_PREMIUM.name: rg.probability_curve(port_at, [0.0], rg.ZERO_PREMIUM, **kw),
              central.name: rg.probability_curve(port_at, shares, central, **kw),
              rg.FAVOURABLE.name: rg.probability_curve(port_at, shares, rg.FAVOURABLE, **kw)}
    a = rg.classify(curves, {c: x for c, x in ((rg.ZERO_PREMIUM.name, rg.ZERO_PREMIUM), (central.name, central),
                                              (rg.FAVOURABLE.name, rg.FAVOURABLE))},
                    ceiling, GOAL_MIN_PROB, GOAL_LOW_PROB)
    return rg.explanation_facts(a)


def goal_message(goal: dict, ceiling: float, set_by_text: str, rets: pd.DataFrame) -> str:
    """Plain words for a goal that does not fit (never "more than 100%": the ceiling is the most we propose)."""
    best = goal["best_probability_by_assumption"]
    c, f = best.get("central") or 0.0, best.get("favourable") or 0.0
    lab = period_label(rets)
    opts = "Options: a longer horizon, a lower target, larger contributions, or accepting a larger loss (your choice)."
    if goal["status"] == rg.GoalStatus.ONLY_FAVOURABLE.value:
        return (f"Within your limits (at most {ceiling:.0%} in growth assets, set by {set_by_text}), your goal is "
                f"reached with at least a {GOAL_MIN_PROB:.0%} chance only if {lab} returns repeat ({f:.0%}); with our "
                f"central assumption ({CENTRAL_PREMIUM:.0%} a year more than cash on growth assets) the best chance is "
                f"{c:.0%}. {opts}")
    if goal["status"] == rg.GoalStatus.LOW_PROBABILITY.value:
        return (f"Within your limits (at most {ceiling:.0%} in growth assets, set by {set_by_text}), the best chance of "
                f"reaching your goal is {c:.0%} with our central assumption, below {GOAL_MIN_PROB:.0%}. {opts}")
    return (f"Within your limits (at most {ceiling:.0%} in growth assets, set by {set_by_text}), your goal is out of "
            f"reach: at most {max(c, f):.0%} chance, even if {lab} returns repeat. {opts}")


def what_set_the_split(dec: lm.CeilingDecision, ceiling: float, max_share: float, limits: dict,
                       rets: pd.DataFrame, horizon: float) -> tuple[str, str, float | None]:
    """Which constraint decided the growth share (decision #33): the client's loss test (simulated, R1), or a rule
    (horizon, withdrawals, safety net, a lower risk level). Also the share the loss test ALONE would allow."""
    data_ceiling = dec.loss_only
    if data_ceiling is None or (data_ceiling + 1e-9 < max_share and abs(ceiling - data_ceiling) < 1e-9):
        return "worst_drop", (f"the loss test (at most a {LOSS_ALPHA:.0%} chance of a drop deeper than your "
                              f"{limits['loss_limit']:.0%} limit over {horizon:g} years, in simulations built from "
                              f"{period_label(rets)} days)"), data_ceiling
    src = limits.get("min_defensive_source", "safety")
    text = limits.get("min_defensive_why") or "the defensive floor"
    return src, text, data_ceiling


# ---- assemble ----------------------------------------------------------------------------------------

def fix_diversification(w: dict[str, float], rep: dict, limits: dict, rets: pd.DataFrame,
                        holdings: dict, profile: dict | None = None) -> tuple[dict[str, float], list[str]]:
    """On a C6 ✘ (two holdings correlated >= 0.95) keep the larger one; on a C3 ✘ (a sector above 40%) move the
    excess from that sector's single stocks to the broad core ETF. Undone if the result fails the loss test (simulated,
    R1; observed worst drop when no profile is given)."""
    new, notes = dict(w), []
    for p in rep.get("redundant_pairs", []):
        a, b = p["a"], p["b"]
        if a in new and b in new:
            keep, drop = (a, b) if new[a] >= new[b] else (b, a)
            new[keep] += new.pop(drop)
            notes.append(f"C6: {drop} merged into {keep} (correlation {p['correlation']:.3f}, same bet twice)")
    ls = rep.get("largest_sector", {})
    if ls.get("weight", 0) > dv.MAX_SECTOR + 1e-9:
        sec = dv._universe_col("sector")
        names = [t for t in new if t in STOCKS and sec.get(t) == ls["name"]]
        core = next((t for t in ("XIU.TO", "ESGV", "SPY") if t in new), None)
        held = sum(new[t] for t in names)
        if names and core and held > 0:
            cut = min(held, ls["weight"] - dv.MAX_SECTOR)
            for t in names:
                new[t] -= cut * new[t] / held
            new[core] += cut
            notes.append(f"C3: {ls['name']} cut by {cut:.1%} (single stocks → {core}) to stay ≤ {dv.MAX_SECTOR:.0%}")
    if not notes:
        return w, []
    new = round_weights({t: v for t, v in new.items() if v > 1e-9})
    lim = limits.get("loss_limit", limits["max_drawdown"])
    if profile is not None:
        breaks = final_risk(new, profile, limits, rets, n=N_LOSS)["exceedance"] > LOSS_ALPHA + 1e-9
    else:
        breaks = abs(market.strategy_stats(new, rets=rets)["max_drawdown"]) > lim + 1e-9
    if breaks:
        return w, [n + " — undone: it would break the loss limit" for n in notes]
    return new, notes


def final_risk(w: dict[str, float], profile: dict, limits: dict, rets: pd.DataFrame, n: int | None = None,
               seed: int = 1) -> dict:
    """The loss test on the FINAL weights (after rounding, caps, diversification fixes, Critic): a fresh simulation
    (other seed, more paths) of the weights actually proposed, not of the grid point the ceiling was read from.
    G7 / D2 read it. `tolerance` = 2 standard errors of the estimated probability at alpha (sampling noise)."""
    n = N_LOSS_FINAL if n is None else n
    port = metrics.portfolio_returns(rets[list(w)], w)
    cash = cash_daily(rets, port.index)
    growth = sum(v for t, v in w.items() if t not in DEFENSIVE)
    horizon, limit = horizon_of(profile), limits.get("loss_limit", limits["max_drawdown"])
    d = loss_model(cash, n, seed).distribution(port, horizon, growth_share=growth)
    return {"exceedance": d.exceedance(limit), "alpha": LOSS_ALPHA,
            "tolerance": round(2 * (LOSS_ALPHA * (1 - LOSS_ALPHA) / n) ** 0.5, 4), "loss_limit": limit,
            "drop_1_in_10": d.quantile(LOSS_ALPHA), "drop_1_in_20": d.quantile(0.05), "horizon_years": horizon,
            "n_scenarios": n, "premium": CENTRAL_PREMIUM, "growth_share": growth, "evidence": "simulated",
            "method": (f"stationary block bootstrap of {period_label(rets)} daily returns over {horizon:g} years, "
                       f"average = cash + {CENTRAL_PREMIUM:.0%} a year on the growth part")}


def assemble(key: str, why: str, g: dict, dfn: dict, notes: list[str], profile: dict, limits: dict,
             rets: pd.DataFrame, holdings: dict, with_range: bool = True) -> Strategy:
    """The whole calculation for one strategy from its baskets: split search (ceiling, range, goal), build, the
    diversification fixes, then EVERY number on the final weights (stats, outlook, loss test, diversification, checks),
    each section stamped with those weights (dh.risk.sync, audit A6). Used by `propose`, `levels` and `revise`."""
    sr = split_search(g, dfn, profile, limits, rets, holdings, with_range)
    w, _, build_notes = sr["best"]
    rep = dv.report(w, rets=rets, holdings=holdings)
    w2, fixes = fix_diversification(w, rep, limits, rets, holdings, profile)
    if w2 is not w:
        w = w2
        rep = dv.report(w, rets=rets, holdings=holdings)
    build_notes = build_notes + fixes
    # From here on, every section describes `w` (the final weights): computed once, then stamped.
    stats = dict(market.strategy_stats(w, rets=rets))
    outlook = None
    if profile.get("capital"):
        outlook = market.goal_outlook(w, capital=profile["capital"], horizon_years=profile["horizon_years"],
                                      monthly_contribution=profile.get("monthly_contribution") or 0.0,
                                      target_amount=profile.get("target_amount"), n_scenarios=N_FINAL, rets=rets)
        stats["prob_loss"] = outlook["risk_only"]["prob_loss"]
    risk = {**final_risk(w, profile, limits, rets), "ceiling_range": sr["range"]}
    growth = round(sum(v for t, v in w.items() if t not in DEFENSIVE), 4)
    rng = (sr["range"] or {}).get("range")
    s = Strategy(
        key=key, flavour=key, name=STRATEGY_DEFS[key]["name"], risk_level=limits["risk_level"], weights=w,
        split={"growth": growth, "defensive": round(1 - growth, 4)},
        split_range={k: sr[k] for k in ("floor", "ceiling", "liquidity_floor", "conflict", "conflict_message",
                                        "set_by", "set_by_text", "data_ceiling", "exceedance", "alpha",
                                        "horizon_years", "range", "goal")},
        split_curve=sr["curve"], stats=market._round(stats), outlook=market._round(outlook) if outlook else None,
        diversification={**rep, "checks": dv.check(rep)}, risk=market._round(risk),
        adjustments=[f"offered: {why}", f"holds: {STRATEGY_DEFS[key]['why']}",
                     f"split {growth:.0%} growth, set by {sr['set_by_text']}"
                     + (f"; the loss test alone would allow {sr['data_ceiling']:.0%}"
                        if sr["set_by"] != "worst_drop" and sr["data_ceiling"] is not None else "")
                     + (f"; on 3-year sub-windows the loss test gives {rng[0]:.0%} to {rng[1]:.0%}" if rng else "")]
        + notes + build_notes,
        baskets={"growth": g, "defensive": dfn}, pros=[], cons=[])
    s = sync.stamp(s, ("stats", "outlook", "diversification", "risk"), rets, "portfolio.assemble")
    s["checks"] = ck.run(s, profile, limits, rets=rets, holdings=holdings)
    return sync.stamp(s, "checks", rets, "checks.run")


def propose(profile: dict, limits: dict, rets: pd.DataFrame | None = None, holdings=None) -> list[Strategy]:
    """Up to MAX_STRATEGIES strategies at different risk levels (#32), most growth first. [] if limits["missing"]."""
    if limits.get("missing"):
        return []
    rets = data.returns() if rets is None else rets
    holdings = load_holdings() if holdings is None else holdings
    flavours = []
    for key, why in offered(profile, limits):
        if key.startswith("-"):
            continue
        g, dfn, notes = baskets(key, profile, limits)
        if not g or not dfn:
            continue
        if any(t in CRYPTO for t in g):
            keep, why_c = crypto_decision(g, dfn, profile, limits, rets, holdings)
            if not keep:
                g = _norm({t: w for t, w in g.items() if t not in CRYPTO})
            if why_c:
                notes.append(why_c)
        flavours.append((key, why, g, dfn, notes))
    return levels(flavours, profile, limits, rets, holdings)


# ---- the 3 strategies are 3 RISK LEVELS (decision #32) ------------------------------------------------
# Level 1 = the growth share the client's limits allow (the ceiling), levels 2 and 3 = 10 and 20 points less in
# stocks. Named by what they hold, not "more prudent": less in stocks did NOT always mean smaller past drops (Robert:
# 5% stocks in XBB/AGG fell -9.5% in 2021-2026, 15% stocks with ZST -8.6%), so a risk word would be a promise the
# data can break. The measured drops sit next to each name. Each level is a full recalculation (assemble) with a higher defensive floor, never a hand edit, and it can
# only be safer than level 1. The client's preferred flavour (growth tilt if offered, else broad core) takes level 1,
# the others the next levels. Levels closer than MIN_LEVEL_GAP to one already kept, or below MIN_LEVEL_GROWTH, are
# dropped: Robert (15% ceiling) gets 2 strategies, not 3 near-copies.
LEVELS = [(1, "most growth your limits allow", 0.0), (2, "less in stocks", 0.10), (3, "least in stocks", 0.20)]
MIN_LEVEL_GAP = 0.05
MIN_LEVEL_GROWTH = 0.05
FLAVOUR_ORDER = ("growth", "core", "income")


def level_limits(limits: dict, level: dict | None) -> dict:
    """The client's limits with the level's higher defensive floor (level 1 = the client's own limits)."""
    if not level or level.get("rank", 1) == 1:
        return limits
    floor = round(max(limits["min_defensive"], 1 - level["target_growth"]), 4)
    why = (f"option {level['rank']} of 3 ({level['label']}): {level['target_growth']:.0%} growth, "
           f"{level['delta'] * 100:.0f} points below the top strategy, a choice offered to the client, not a limit")
    return {**limits, "min_defensive": floor, "min_defensive_source": "level", "min_defensive_why": why}


def levels(flavours: list, profile: dict, limits: dict, rets: pd.DataFrame, holdings: dict) -> list[Strategy]:
    """Levels 2-3 use level 1's DEFENSIVE basket (only the growth basket and the share change, decision R5), then the
    ladder is checked on measured risk (worst drop, chance of loss: dh.risk.levels): a level that is not safer than
    the one above is dropped (inverted) or kept with the disagreement stated (mixed). Audit A3."""
    if not flavours:
        return []
    order = sorted(flavours, key=lambda f: FLAVOUR_ORDER.index(f[0]))
    top = assemble(*order[0], profile, limits, rets, holdings)
    ref = top["split"]["growth"]
    top_dfn = top["baskets"]["defensive"]
    out: list[Strategy] = []
    used: dict[str, int] = {}
    for i, (rank, label, delta) in enumerate(LEVELS):
        f = order[i] if i < len(order) else next((x for x in order if x[0] == "core"), order[-1])
        target = round(ref - delta, 4)
        if rank > 1 and target < MIN_LEVEL_GROWTH - 1e-9:
            break
        lvl = {"rank": rank, "label": label, "delta": delta, "target_growth": target}
        key, why, g, _, notes = f
        lv_notes = [] if rank == 1 else [(f"level {rank} of 3 ({label}): growth capped at {target:.0%}, "
                                          f"{delta * 100:.0f} points below the top strategy's {ref:.0%}, same "
                                          "defensive basket")]
        s = top if rank == 1 else assemble(key, why, g, top_dfn, notes + lv_notes, profile,
                                           level_limits(limits, lvl), rets, holdings, with_range=False)
        if any(abs(s["split"]["growth"] - o["split"]["growth"]) < MIN_LEVEL_GAP - 1e-9 for o in out):
            continue  # not a different risk level: skip it
        if out:
            prev = out[-1]
            issues = rl.check_labels([(prev["name"], rl.risk_vector(prev)), (label, rl.risk_vector(s))])
            codes = {x.code for x in issues}
            if "C-inverted" in codes:
                out[0]["adjustments"] = out[0]["adjustments"] + [(
                    f"level {rank} ({STRATEGY_DEFS[key]['name']}) left out: it is not safer than '{prev['name']}' "
                    "on worst drop and chance of loss")]
                continue
            if "C-mixed" in codes:
                per = next(x for x in issues if x.code == "C-mixed").evidence["per_dimension"]
                lvl = {**lvl, "contradiction": per}
                s = {**s, "adjustments": s["adjustments"] + [
                    "risk measures disagree with the level above: "
                    + ", ".join(f"{d} {v}" for d, v in per.items() if v) + " (shown as an alternative)"]}
        used[key] = used.get(key, 0) + 1
        s = {**s, "key": key if used[key] == 1 else f"{key}-{rank}", "flavour": key, "level": lvl,
             "name": f"{STRATEGY_DEFS[key]['name']}: {label}"}
        out.append(s)
    return out[:MAX_STRATEGIES]


def describe(strategies: list[Strategy], limits: dict) -> str:
    """Portfolio → Guardian hand-off line for the trace (numbers only from the strategies and limits)."""
    if not strategies:
        return "no strategy: profile incomplete or nothing allowed."
    parts = []
    for s in strategies:
        r = s["split_range"]
        rk = s.get("risk") or {}
        part = (f"'{s['name']}' {s['split']['growth']:.0%}/{s['split']['defensive']:.0%} "
                f"(set by {r.get('set_by', '?')}; observed worst drop {s['stats']['max_drawdown']:.1%}"
                + (f", simulated chance of a drop deeper than {limits['loss_limit']:.0%} over "
                   f"{rk['horizon_years']:g} years {rk['exceedance']:.0%} (allowed {rk['alpha']:.0%})"
                   if "exceedance" in rk else f" vs loss limit {limits['loss_limit']:.0%}"))
        if (r.get("goal") or {}).get("status"):
            part += f"; goal: {r['goal']['status'].replace('_', ' ')}"
        if r["floor"] is not None:
            part += f", minimum growth for the goal {r['floor']:.0%}"
        part += ")"
        parts.append(part)
    s = f"{len(strategies)} strateg{'y' if len(strategies) == 1 else 'ies'}: " + "; ".join(parts) + "."
    conflict = next((x["split_range"]["conflict_message"] for x in strategies if x["split_range"]["conflict"]), None)
    if conflict:
        s += " Conflict: " + conflict
    return s



# ---- one revision round, asked by the Critic (decision #30) -----------------------------------------------
# A fix never edits weights by hand: it TIGHTENS one input of the calculation, then `assemble` reruns all of it
# (split search, build, diversification fixes, stats, outlook, checks). Inputs can only get stricter, and only
# assets already in the strategy are used, so a fix can't raise risk. The Guardian re-checks against the client's
# original limits (the pipeline's job).

ACTIONS = ("merge", "trim", "shift", "disclose")
MAX_SHIFT = 0.20


def tighten(s: Strategy, action: dict, limits: dict) -> tuple[dict, dict, dict, str] | tuple[None, None, None, str]:
    """(growth basket, defensive basket, limits, what changed) for one Critic fix, or (None, None, None, why not).
    merge(a, b): the smaller of two holdings of the same basket goes into the larger;
    trim(ticker, to): that company's cap becomes `to` (lower than now), the build moves the excess to the ETFs;
    shift(pct): the defensive floor rises by pct (the split search then finds a lower ceiling)."""
    kind = (action or {}).get("type")
    b = s.get("baskets") or {}
    g, dfn, lim = dict(b.get("growth") or {}), dict(b.get("defensive") or {}), dict(limits)
    if not g or not dfn:
        return None, None, None, "strategy has no baskets to recompute from"
    if kind == "merge":
        a, c = action.get("a"), action.get("b")
        basket = g if a in g and c in g else dfn if a in dfn and c in dfn else None
        if basket is None or a == c:
            return None, None, None, f"merge needs two different holdings of the same basket (got {a}, {c})"
        keep, drop = (a, c) if basket[a] >= basket[c] else (c, a)
        basket[keep] += basket.pop(drop)
        return g, dfn, lim, f"{drop} merged into {keep}, whole calculation rerun"
    if kind == "trim":
        t, to = action.get("ticker"), action.get("to")
        caps = dict(lim.get("company_caps") or {})
        now = s["weights"].get(t, 0.0)
        if t not in g or t not in STOCKS or not isinstance(to, (int, float)) or not 0 <= to < now:
            return None, None, None, f"trim needs a single company of the growth basket and a lower weight (got {t} → {to})"
        caps[t] = min(caps.get(t, lim["max_single"]), to)
        lim["company_caps"] = caps
        return g, dfn, lim, f"{t} capped at {to:.1%} (was {now:.1%}), whole calculation rerun"
    if kind == "shift":
        pct = action.get("pct")
        if not isinstance(pct, (int, float)) or not 0 < pct <= MAX_SHIFT:
            return None, None, None, f"shift needs 0 < pct ≤ {MAX_SHIFT:.0%} (got {pct})"
        floor = round(max(lim["min_defensive"], s["split"]["defensive"] + pct), 4)
        if floor >= 1:
            return None, None, None, "nothing left to shift"
        lim["min_defensive"] = floor
        return g, dfn, lim, f"defensive floor raised to {floor:.0%} (+{pct:.0%}), whole calculation rerun"
    return None, None, None, f"no change to apply ({kind or 'disclose'})"


def revise(s: Strategy, action: dict, profile: dict, limits: dict, rets: pd.DataFrame | None = None,
           holdings=None) -> tuple[Strategy | None, str]:
    """The strategy recomputed from scratch with one Critic fix, or (None, why). Same calculation as `propose`."""
    rets = data.returns() if rets is None else rets
    holdings = load_holdings() if holdings is None else holdings
    g, dfn, lim, note = tighten(s, action, level_limits(limits, s.get("level")))
    if g is None:
        return None, note
    why = next((a[len("offered: "):] for a in s.get("adjustments", []) if a.startswith("offered: ")), "")
    kept = [a for a in s.get("adjustments", [])[2:] if a.startswith(("left out", "crypto", "loss limit", "SPY replaced",
                                                                   "level "))]
    new = assemble(s.get("flavour", s["key"]), why, g, dfn, kept + [f"Critic: {note}"], profile, lim, rets, holdings,
                   with_range=(s.get("level") or {}).get("rank", 1) == 1)
    if new["weights"] == s["weights"]:
        return None, "the recalculation gives the same weights"
    new.update({k: s[k] for k in ("key", "name", "level") if k in s})
    new["cons"] = list(s.get("cons") or [])
    return new, note
