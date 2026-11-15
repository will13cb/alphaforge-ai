"""Layer 3, blocks G (request handling) and H (pros and cons). DETERMINISTIC, no LLM (branch portfolio/requests).

G — `compare`: the client's request (e.g. Robert's 25% in TSLA) is put on top of our proposal ("as asked"), and next
    to it the version that fits (each requested asset capped at what the Profiler says fits, decision #24). Both get
    the same C-F checks (`checks.py`) and the Guardian, so the side by side shows the real weight (through ETFs), the
    worst drop in % and in $, and every check that fails. The client decides; nothing is "refused" in the wording.
H — `pros_cons`: pros and cons written from templates filled ONLY with numbers already in `stats` and `checks`
    (never by the LLM), comparing the proposed strategies, so the Guardian's G12 can trace every %.
Selection (drop any strategy with a ✘, keep ≤ 3, say why) lives in `pipeline.run`.
"""

from __future__ import annotations

from ..data import period_label

import pandas as pd

from .. import data, metrics
from ..holdings import holdings as load_holdings
from . import checks as ck
from . import guardian, market
from .rules import DEFENSIVE


# ---- G. request handling -------------------------------------------------------------------------------

def base_strategy(strategies: list[dict]) -> dict | None:
    """The proposal the request is laid on: "Broad core" when offered (always simple), else the first one."""
    return next((s for s in strategies if s.get("key") == "core" or s.get("name") == "Broad core"),
                strategies[0] if strategies else None)


def overlay(base: dict[str, float], request: dict[str, float]) -> dict[str, float]:
    """The request exactly as asked, made room for in the growth part first, then (only if the growth part is too
    small, e.g. Robert's 25% TSLA vs 15% in stocks) in the defensive part. The total stays 100%."""
    req = {t: float(v) for t, v in request.items() if v > 0}
    need = min(1.0, sum(req.values()))
    growth = {t: v for t, v in base.items() if t not in DEFENSIVE and t not in req}
    defensive = {t: v for t, v in base.items() if t in DEFENSIVE and t not in req}
    g, d = sum(growth.values()), sum(defensive.values())
    from_g = min(need, g)
    from_d = min(need - from_g, d)
    sg = {t: v * (g - from_g) / g for t, v in growth.items()} if g > 0 else {}
    sd = {t: v * (d - from_d) / d for t, v in defensive.items()} if d > 0 else {}
    out = {**sg, **sd, **req}
    s = sum(out.values())
    return {t: round(v / s, 6) for t, v in out.items() if v > 1e-9}


def overlay_growth(base: dict[str, float], request: dict[str, float]) -> dict[str, float]:
    """Requested weights taken from the GROWTH part only: the defensive part (floor, horizon cap) stays as it is."""
    defensive = {t: v for t, v in base.items() if t in DEFENSIVE and t not in request}
    growth = {t: v for t, v in base.items() if t not in DEFENSIVE and t not in request}
    room = sum(growth.values())
    req = {t: v for t, v in request.items() if v > 0}
    scale = min(1.0, room / sum(req.values())) if req else 1.0
    req = {t: v * scale for t, v in req.items()}
    left = room - sum(req.values())
    scaled = {t: v * left / room for t, v in growth.items()} if room > 0 else {}
    out = {**defensive, **scaled, **req}
    s = sum(out.values())
    return {t: round(v / s, 6) for t, v in out.items() if v > 1e-9}


def _version(label: str, w: dict, requested: list[str], profile: dict, limits: dict, rets: pd.DataFrame,
             holdings: dict) -> dict:
    st = market.strategy_stats(w, rets=rets)
    s = {"weights": w, "stats": st}
    chk = ck.run(s, profile, limits, rets=rets, holdings=holdings)
    g = guardian.check_strategy(s, limits, profile, holdings)
    eff = metrics.look_through(w, holdings)
    cap = profile.get("capital")
    dd = abs(st["max_drawdown"])
    lim = limits.get("loss_limit", limits["max_drawdown"])
    fails = ([{"id": c["check"], "reason": c["reason"]} for c in chk if c["status"] == "fail"]
             + [{"id": c["rule"], "reason": c["detail"]} for c in g if c["status"] == "fail"])
    warns = ([{"id": c["check"], "reason": c["reason"]} for c in chk if c["status"] == "warn"]
             + [{"id": c["rule"], "reason": c["detail"]} for c in g if c["status"] == "warn"])
    return market._round({
        "label": label, "weights": w,
        "real_weight": {t: eff.get(t, 0.0) for t in requested},
        "max_drawdown": st["max_drawdown"], "drawdown_cad": round(cap * dd) if cap else None,
        "loss_limit": lim, "loss_limit_cad": round(cap * lim) if cap else None,
        "return_2022": st["return_2022"], "ann_vol": st["ann_vol"],
        "growth": sum(v for t, v in w.items() if t not in DEFENSIVE),
        "verdict": guardian.verdict(g + [{"status": c["status"]} for c in chk]),
        "fails": fails, "warnings": warns,
    })


def compare(profile: dict, limits: dict, strategies: list[dict], rets: pd.DataFrame | None = None,
            holdings=None) -> dict | None:
    """Side by side: our proposal with the request as asked, and with the request at what fits. None if no request."""
    req = {t: v for t, v in (profile.get("requested_positions") or {}).items() if v}
    base = base_strategy(strategies)
    if not req or base is None:
        return None
    rets = data.returns() if rets is None else rets
    holdings = load_holdings() if holdings is None else holdings
    notes = {r["ticker"]: r for r in limits.get("request_checks") or []}
    caps = limits.get("company_caps") or {}
    assessable = {t: v for t, v in req.items() if t in rets.columns}
    fit = {}
    for t, v in assessable.items():
        r = notes.get(t, {})
        if "fits_up_to" in r:
            fit[t] = min(v, r["fits_up_to"])
        elif t in limits.get("allowed_assets", []):
            fit[t] = min(v, caps.get(t, v))
    fit = {t: round(v, 4) for t, v in fit.items() if v > 1e-6}
    out = {"base": base["name"], "request": req,
           "not_assessable": sorted(set(req) - set(assessable)),
           "why": {t: notes[t]["reason"] for t in req if t in notes and "reason" in notes[t]}}
    if profile.get("request_stand_ins"):   # e.g. XSP.TO asked, measured with SPY (dh.standins, #42)
        out["stand_ins"] = list(profile["request_stand_ins"])
    if assessable:
        out["as_asked"] = _version("as asked", overlay(base["weights"], assessable), list(assessable), profile,
                                   limits, rets, holdings)
    same = fit == {t: round(v, 4) for t, v in assessable.items()}
    if fit and not same:
        out["fits"] = _version("fits your limits", overlay_growth(base["weights"], fit), list(fit), profile, limits,
                               rets, holdings)
        out["fits"]["request_at"] = fit
    out["summary"] = summary(out)
    return out


def summary(cmp: dict) -> str:
    """One line for the trace, numbers only from the comparison."""
    parts = [f"Request {', '.join(f'{t} {v:.0%}' for t, v in cmp['request'].items())} on '{cmp['base']}'"]
    for key in ("as_asked", "fits"):
        v = cmp.get(key)
        if not v:
            continue
        rw = ", ".join(f"{t} {x:.1%} real" for t, x in v["real_weight"].items())
        money = f" = {v['drawdown_cad']:,} $ vs {v['loss_limit_cad']:,} $" if v.get("drawdown_cad") else ""
        bad = ", ".join(f["id"] for f in v["fails"]) or "none"
        parts.append(f"{v['label']}: {rw}; worst drop {v['max_drawdown']:.1%}{money}; failing: {bad}")
    if cmp.get("not_assessable"):
        parts.append("no data for " + ", ".join(cmp["not_assessable"]))
    if cmp.get("stand_ins"):
        parts.append("stand-in: " + "; ".join(cmp["stand_ins"]))
    return ". ".join(parts) + "."


# ---- H. pros and cons -----------------------------------------------------------------------------------

SAME = 0.0005  # shown to 0.1%: closer than half a step looks equal on screen, so it's not called smallest/largest


def pros_cons(strategies: list[dict], limits: dict, profile: dict) -> list[dict]:
    """Fill strategies[i]["pros"] and ["cons"] from their own numbers, comparing them when there are several."""
    n = len(strategies)
    lim = limits.get("loss_limit", limits["max_drawdown"])
    key = lambda s, k: s["stats"].get(k)
    for s in strategies:
        st, pros, cons = s["stats"], [], []
        dd = abs(st["max_drawdown"])
        if n > 1:
            others = [o for o in strategies if o is not s]
            if dd < min(abs(key(o, "max_drawdown")) for o in others) - SAME:
                pros.append(f"smallest worst drop of the {n}: {st['max_drawdown']:.1%}")
            if dd > max(abs(key(o, "max_drawdown")) for o in others) + SAME:
                cons.append(f"largest worst drop of the {n}: {st['max_drawdown']:.1%}")
            # No "highest return" pro (audit P8): over one window the gap between strategies is noise (Robert's two:
            # -0.02%/yr, 95% interval ±1.6%), and the brief values faithful explanations over past returns.
            if st["return_2022"] > max(key(o, "return_2022") for o in others) + SAME:
                pros.append(f"held up best in 2022: {st['return_2022']:.1%}")
        if dd <= 0.5 * lim:
            pros.append(f"worst drop {st['max_drawdown']:.1%}, half or less of your {lim:.0%} loss limit")
        elif dd > 0.8 * lim:
            cons.append(f"worst drop {st['max_drawdown']:.1%}, close to your {lim:.0%} loss limit")
        if "prob_loss" in st:
            (pros if st["prob_loss"] <= 0.1 else cons).append(
                f"{st['prob_loss']:.0%} chance of ending below what you put in (without assuming past returns repeat)")
        chk = s.get("checks") or []
        warn = [c for c in chk if c["status"] == "warn"]
        if chk and not warn and all(c["status"] == "pass" for c in chk):
            pros.append(f"all {len(chk)} diversification and profile checks pass")
        cons += [f"{c['check']}: {c['reason']}" for c in warn]
        # No "most spread out" pro (audit P13): C5's count assumes 100 lines per ETF without holdings data, so the
        # comparison ranked the assumption, not the portfolios.
        s["pros"], s["cons"] = pros, cons
    return strategies
