"""Existing portfolio: the client's current holdings reviewed, then rebuilt. DETERMINISTIC numbers; the LLM Critic
only adds objections it backs with tool results (branch portefeuille_existant, notes/branches/portefeuille_existant.md).

Workshop gap (BN deck, slides 13-14): a decision starts from "what am I trying to improve?" in what the client
already holds, not from a blank page. Input: `profile["existing_positions"]` = {ticker: dollars invested}.

    review(profile, limits, strategies)  →  {"current", "critique", "target", "moves", "stand_ins", …}

- Each holding is measured with its own data, else with a LABELLED stand-in (`dh.standins`: XSP.TO → SPY with the
  CAD hedge simulated), else listed in `not_assessable` and kept out of the numbers. Never guessed silently.
- `current`: the holdings today through the SAME C-F checks and Guardian as any strategy, so the critique quotes the
  engine's own numbers (worst drop in % and $, real weight through ETFs, where the stocks are, ✘ / ⚠).
- `target`: the first proposed strategy (the most growth the client's limits allow, decision #32), same total.
- `moves`: per holding, dollars now → dollars in the target → change. A simulation, not an order.
- `critic` (optional): the Critic agent's objections on the CURRENT portfolio (disclose only: the rebuild is the fix).
"""

from __future__ import annotations

import pandas as pd

from .. import data, fees, standins
from ..holdings import holdings as load_holdings
from . import checks as ck
from . import guardian, market
from .rules import DEFENSIVE, EQUITY_ETFS, ETFS

MAX_POSITIONS = 30


def clean_positions(positions: dict | None, have=()) -> dict[str, float]:
    """{ticker: dollars}: tickers upper-cased ('xsp' → 'XSP.TO' when only the Toronto listing is known), amounts > 0,
    duplicates added up, at most MAX_POSITIONS."""
    out: dict[str, float] = {}
    for t, v in (positions or {}).items():
        t = standins.canonical(t, have)
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if t and v > 0:
            out[t] = out.get(t, 0.0) + v
    return dict(list(out.items())[:MAX_POSITIONS])


def weights(positions: dict[str, float]) -> dict[str, float]:
    total = sum(positions.values())
    return {t: round(v / total, 6) for t, v in positions.items()} if total > 0 else {}


def measure(pos: dict[str, float], rets: pd.DataFrame, fx_rets: pd.Series | None = None,
            gap: pd.Series | None = None) -> dict:
    """Map each holding to a column we have data for. Returns {measured: {ticker: $}, held_as: {measured: [held]},
    stand_ins: [...], not_assessable: [...], rets: returns with hedged stand-ins blended into their source column}."""
    have = set(rets.columns)
    measured, held_as, used, unknown = {}, {}, [], []
    hedged_cad: dict[str, float] = {}
    for t, v in pos.items():
        src = t if t in have else None
        si = None if src else standins.stand_in(t, have)
        if si:
            src = si["measured_with"]
            used.append({**si, "amount_cad": round(v, 2)})
            if si["hedged"]:
                hedged_cad[src] = hedged_cad.get(src, 0.0) + v
        if src is None:
            unknown.append(t)
            continue
        measured[src] = measured.get(src, 0.0) + v
        held_as.setdefault(src, []).append(t)
    r = rets
    for src, h in hedged_cad.items():
        hr, how = standins.hedged_returns(rets[src], fx_rets, gap)
        for s in used:
            if s["measured_with"] == src and s["hedged"]:
                s["hedge_method"] = how
        if hr is None:
            continue
        if r is rets:
            r = rets.copy()
        u = measured[src] - h                         # part of this column held unhedged (e.g. SPY itself)
        r[src] = (h * hr + u * rets[src]) / measured[src]
        for s in used:                                # what the hedge changed, for the disclosure
            if s["measured_with"] == src and s["hedged"]:
                a, b = market._stats(rets[src]), market._stats(hr)
                s["hedge_effect"] = market._round({k: {"unhedged": a.get(k), "hedged": b.get(k)}
                                                   for k in ("max_drawdown", "return_2022", "ann_vol")})
    return {"measured": measured, "held_as": held_as, "stand_ins": used, "not_assessable": sorted(unknown), "rets": r}


def assess(label: str, w: dict, profile: dict, limits: dict, rets: pd.DataFrame, holdings: dict) -> dict:
    """Same numbers and checks as `requests._version`, plus the raw checks and stats (for the Critic's tools)."""
    st = market.strategy_stats(w, rets=rets)
    s = {"weights": w, "stats": st}
    chk = ck.run(s, profile, limits, rets=rets, holdings=holdings)
    g = guardian.check_strategy(s, limits, profile, holdings)
    cap = profile.get("capital")
    dd = abs(st["max_drawdown"])
    lim = limits.get("loss_limit", limits["max_drawdown"])
    pick = lambda st_: ([{"id": c["check"], "reason": c["reason"]} for c in chk if c["status"] == st_]
                        + [{"id": c["rule"], "reason": c["detail"]} for c in g if c["status"] == st_])
    return market._round({
        "label": label, "weights": w, "stats": st, "checks": chk, "guardian_checks": g,
        "max_drawdown": st["max_drawdown"], "drawdown_cad": round(cap * dd) if cap else None,
        "loss_limit": lim, "loss_limit_cad": round(cap * lim) if cap else None,
        "return_2022": st["return_2022"], "ann_vol": st["ann_vol"],
        "growth": sum(v for t, v in w.items() if t not in DEFENSIVE),
        "verdict": guardian.verdict(g + [{"status": c["status"]} for c in chk]),
        "fails": pick("fail"), "warnings": pick("warn"),
    })


def moves(current_cad: dict[str, float], target_w: dict[str, float], total: float,
          held_as: dict[str, list[str]] | None = None) -> list[dict]:
    """Dollars now → dollars in the target, per measured holding, largest change first. `held` names what the client
    actually holds (XSP.TO for the SPY line), so keeping a same-index fund instead is visible."""
    held_as = held_as or {}
    rows = []
    for t in sorted(set(current_cad) | set(target_w)):
        now = round(current_cad.get(t, 0.0), 2)
        tgt = round(total * target_w.get(t, 0.0), 2)
        if abs(tgt - now) < 0.01:
            continue
        held = [h for h in held_as.get(t, []) if h != t]
        rows.append({"ticker": t, "held": held, "now_cad": now, "target_cad": tgt, "change_cad": round(tgt - now, 2),
                     "action": "add" if tgt > now else "reduce" if tgt > 0 else "remove",
                     "note": (f"you hold it as {', '.join(held)} (same or close index): keeping that fund works the same "
                              f"way for this line" if held and tgt > 0 else "")})
    return sorted(rows, key=lambda r: -abs(r["change_cad"]))


def critique(current: dict, m: dict) -> list[str]:
    """Plain lines from the current portfolio's own numbers and checks (no LLM)."""
    lines = []
    w = current["weights"]
    top, share = max(w.items(), key=lambda kv: kv[1])
    held = [h for h in m["held_as"].get(top, []) if h != top]
    lines.append(f"largest position {top}" + (f" (held as {', '.join(held)})" if held else "")
                 + f": {share:.0%} of what we could measure")
    dd, lim = abs(current["max_drawdown"]), current["loss_limit"]
    money = f" (about {current['drawdown_cad']:,} $)" if current.get("drawdown_cad") else ""
    lines.append(f"worst drop {current['max_drawdown']:.1%}{money} vs your {lim:.0%} loss limit"
                 + (": over your limit" if dd > lim + 1e-9 else ""))
    c2 = next((c for c in current["checks"] if c["check"] == "C2"), None)
    if c2 and c2.get("value") is not None:   # the workshop's question: where are the stocks? Always said.
        lines.append(("⚠ " if c2["status"] != "pass" else "") + "where the stocks are: " + c2["reason"].split(" (")[0]
                     + (f" (above the {c2['limit']:.0%} we flag)" if c2["status"] != "pass" else ""))
    for src, held in m["held_as"].items():
        if len(held) > 1:
            lines.append(f"{' and '.join(held)} follow the same index ({src}): one bet held twice")
    lines += [f"✘ {f['id']}: {f['reason']}" for f in current["fails"]]
    lines += [f"⚠ {f['id']}: {f['reason']}" for f in current["warnings"] if f["id"] != "C2"]
    return lines


def look_through_status(measured: dict[str, float], holdings: dict) -> dict:
    """Which equity ETFs held could be opened (issuer holdings file) for the company/sector overlap."""
    eq = sorted(t for t in measured if t in EQUITY_ETFS)
    return {"opened": [t for t in eq if t in holdings], "not_opened": [t for t in eq if t not in holdings]}


def extra_lines(r: dict) -> list[str]:
    out = []
    f = r["fees"]["today"]
    if f["by_ticker"]:
        out.append(f"fund fees: about {f['total_cad']:,.0f} $ a year ({f['weighted_mer']:.2%} of what we measured)"
                   + (f"; fee unknown for {', '.join(f['unknown'])}" if f["unknown"] else ""))
    lt = r["look_through"]
    if lt["not_opened"]:
        out.append(f"companies inside {', '.join(lt['not_opened'])} not opened (no issuer holdings file): "
                   "overlaps through these funds are a lower bound")
    return out


def review(profile: dict, limits: dict, strategies: list[dict], rets: pd.DataFrame | None = None, holdings=None,
           fx_rets: pd.Series | None = None, gap: pd.Series | None = None, critic: bool = False,
           provider: str | None = None) -> dict | None:
    """None when the client entered no existing portfolio. fx_rets / gap: USD/CAD returns and rate gap (tests)."""
    rets = data.returns() if rets is None else rets
    pos = clean_positions(profile.get("existing_positions"), set(rets.columns))
    if not pos:
        return None
    holdings = load_holdings() if holdings is None else holdings
    m = measure(pos, rets, fx_rets, gap)
    out = {"positions": pos, "total_cad": round(sum(pos.values()), 2), "not_assessable": m["not_assessable"],
           "stand_ins": m["stand_ins"], "limits_of_stand_ins": standins.LIMITS if m["stand_ins"] else None}
    if not m["measured"]:
        out["summary"] = ("Existing portfolio: no market data for " + ", ".join(out["not_assessable"])
                          + ", nothing could be measured.")
        return out
    total = sum(m["measured"].values())
    p = {**profile, "capital": total}           # the review is in the client's own dollars
    w = weights(m["measured"])
    current = assess("your portfolio today", w, p, limits, m["rets"], holdings)
    out.update(assessed_cad=round(total, 2), current=current, held_as=m["held_as"], critique=critique(current, m))
    funds = set(ETFS) | set(standins.STAND_INS)
    held = {t: v for t, v in pos.items() if t not in m["not_assessable"]}
    out["fees"] = {"today": fees.yearly(held, funds)}
    out["look_through"] = look_through_status(m["measured"], holdings)
    out["critique"] += extra_lines(out)
    base = strategies[0] if strategies else None
    if base is not None:
        target = assess(f"rebuilt: {base['name']}", dict(base["weights"]), p, limits, rets, holdings)
        target["name"] = base["name"]
        out["target"] = target
        out["moves"] = moves(m["measured"], base["weights"], total, m["held_as"])
        out["fees"]["rebuilt"] = fees.yearly({t: w * total for t, w in base["weights"].items()}, funds)
    if critic:
        from . import critic as critic_agent
        out["critic"] = critic_agent.review_existing(current, out, limits, p, provider, rets=m["rets"],
                                                     holdings=holdings)
    out["summary"] = summary(out)
    return out


def summary(r: dict) -> str:
    """One line for the trace, numbers only from the review."""
    c = r["current"]
    bad = ", ".join(f["id"] for f in c["fails"]) or "none"
    parts = [f"Existing portfolio {r['assessed_cad']:,.0f} $ in {len(r['positions']) - len(r['not_assessable'])} "
             f"holdings: worst drop {c['max_drawdown']:.1%}, failing: {bad}"]
    if r.get("stand_ins"):
        parts.append("stand-ins: " + "; ".join(s["label"] for s in r["stand_ins"]))
    t = r.get("target")
    if t:
        parts.append(f"rebuilt as '{t['name']}': worst drop {t['max_drawdown']:.1%}, "
                     f"{len(r['moves'])} changes, failing: {', '.join(f['id'] for f in t['fails']) or 'none'}")
    else:
        parts.append("no strategy fits the limits, so nothing to rebuild towards")
    if r.get("not_assessable"):
        parts.append("no data for " + ", ".join(r["not_assessable"]))
    return ". ".join(parts) + "."


def public(r: dict | None) -> dict | None:
    """The review without bulky internals (raw checks, stats), for facts, tools and the trace."""
    if not r:
        return r
    out = dict(r)
    for k in ("current", "target"):
        if out.get(k):
            out[k] = {x: v for x, v in out[k].items() if x not in ("checks", "guardian_checks", "stats")}
    return out
