"""Same request, three clients (brief p.15: contrasting personas). DETERMINISTIC, no LLM.

Amira, Mateo and Robert each ask for the same position (default: 25% in TSLA). Each one goes through the real
pipeline (`pipeline.run`, no Critic) with that request added to their own profile, so the three rows show three
limits, three verdicts and three reasons, all read from the pipeline result: loss limit, the asset's cap for that
client, the request "as asked" and "at the cap" side by side (`requests.compare`), and the checks that fail.
No number is computed here except the row layout; the app and `python -m dh contrast` only show this.
"""

from __future__ import annotations

from .scenarios import DEMO_PROFILES

PERSONAS = ("amira", "mateo", "robert")


def row(persona: str, res: dict, ticker: str, weight: float) -> dict:
    """One client's answer to the request, from their pipeline result."""
    lim = res["limits"]
    note = next((r for r in lim.get("request_checks") or [] if r["ticker"] == ticker), {})
    cmp = res.get("request_comparison") or {}
    asked, fits = cmp.get("as_asked") or {}, cmp.get("fits") or {}
    cap = note.get("fits_up_to", (lim.get("company_caps") or {}).get(ticker))
    fits_ok = bool(fits) and fits.get("verdict") != "fail"
    return {
        "persona": persona, "ticker": ticker, "asked": weight,
        "risk_level": lim.get("risk_level"), "loss_limit": lim.get("loss_limit", lim.get("max_drawdown")),
        "loss_limit_cad": asked.get("loss_limit_cad"), "capital": res.get("profile", {}).get("capital"),
        "worst_drop": note.get("worst_drop"), "loss_at_asked": note.get("loss_at_asked"), "cap": cap,
        "base": cmp.get("base"),
        "as_asked": {k: asked.get(k) for k in ("max_drawdown", "drawdown_cad", "verdict")} | {
            "fails": [f["id"] for f in asked.get("fails", [])]},
        "at_cap": ({k: fits.get(k) for k in ("max_drawdown", "drawdown_cad", "verdict", "chance_beyond_limit")}
                   | {"fails": [f["id"] for f in fits.get("fails", [])],
                      "fail_reasons": [f["reason"] for f in fits.get("fails", [])]}) if fits else None,
        "reason": note.get("reason", ""),
        # the one-word answer: the request as asked passes / passes at the cap / doesn't pass even at the cap
        "answer": ("as asked" if asked.get("verdict") != "fail" else
                   f"up to {cap:.1%}" if fits_ok else
                   f"not on this strategy, even at {cap:.1%}" if cap else "not in this profile"),
    }


def contrast(ticker: str = "TSLA", weight: float = 0.25, personas=PERSONAS, run=None, **run_kw) -> list[dict]:
    """The same request through each persona's pipeline. `run` defaults to `pipeline.run` (tests can pass rets/drops
    through `run_kw`)."""
    if run is None:
        from .pipeline import run
    out = []
    for p in personas:
        prof = {**DEMO_PROFILES[p], "requested_positions": {ticker: weight}}
        res = run(prof, critic=False, **run_kw)
        res.setdefault("profile", prof)
        out.append(row(p, res, ticker, weight))
    return out


def markdown(rows: list[dict]) -> str:
    """The side by side as text (CLI, trace, video notes). Numbers only from `rows`."""
    if not rows:
        return ""
    t, w = rows[0]["ticker"], rows[0]["asked"]
    lines = [f"Same request, three clients: {w:.0%} in {t}"
             + (f" (worst drop {rows[0]['worst_drop']:.1%} in the data)" if rows[0].get("worst_drop") is not None else ""),
             "", "| client | level | loss limit | cap for this client | as asked | at the cap | answer |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        money = lambda d: (f" = {d['drawdown_cad']:,} $" if d and d.get("drawdown_cad") else "")
        lim = f"{r['loss_limit']:.0%}" + (f" ({r['loss_limit_cad']:,} $)" if r.get("loss_limit_cad") else "")
        a = r["as_asked"]
        asked = f"worst drop {a['max_drawdown']:.1%}{money(a)}, " + (("✘ " + ", ".join(a["fails"])) if a["fails"] else "✔")
        c = r["at_cap"]
        at_cap = (f"worst drop {c['max_drawdown']:.1%}{money(c)}, " + (("✘ " + ", ".join(c["fails"])) if c["fails"] else "✔")
                  ) if c else "–"
        cap = f"{r['cap']:.1%}" if r.get("cap") is not None else "–"
        lines.append(f"| {r['persona'].capitalize()} | {r['risk_level']} | {lim} | {cap} | {asked} | {at_cap} | "
                     f"{r['answer']} |")
    lines.append("")
    for r in rows:
        at_cap = "; at the cap: " + r["at_cap"]["fail_reasons"][0] if r["at_cap"] and r["at_cap"]["fail_reasons"] else ""
        if r.get("reason"):
            lines.append(f"- {r['persona'].capitalize()}: {r['reason']}{at_cap}")
    return "\n".join(lines)
