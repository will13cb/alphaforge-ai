"""Guardian: deterministic checks, no LLM. "The LLM argues (Critic), code enforces (Guardian)."

Suitability checks MODELLED ON the Canadian KYC / suitability duties (NI 31-103 s.13.2 and s.13.3).
This is not a legal compliance test; it checks the explicit rules below, each with an id the trace shows.

Each check returns {rule, status, detail}; status is "pass", "warn" or "fail". Any fail → send back.
"""

from __future__ import annotations

import re

from ..holdings import holdings as load_holdings
from ..metrics import look_through
from ..personas import DISCLAIMER
from .rules import LOSS_SHARE_ONE_COMPANY, MIN_COMPANIES, CRYPTO, DEFENSIVE, ETFS, STOCKS, excluded_tickers

RULES = {
    "G1": "KYC complete: essential facts known before any proposal (NI 31-103 s.13.2)",
    "G2": "Weights are valid: no negatives, sum to 100%",
    "G3": "Only allowed assets (in the universe, not excluded by the client or the profile)",
    "G4": "Each company ≤ its own cap (from its worst drop and the client's limits, #24), counted through ETFs",
    "G5": "Crypto ≤ crypto cap",
    "G6": "Defensive share ≥ defensive floor (money needed within 3 years, never 100% growth)",
    "G7": "Loss rule: chance of a drop deeper than the loss limit over the horizon ≤ 10% (simulated, final weights; "
          "in % and $)",
    "G8": "Volatility within target (warning only)",
    "G9": "Requests that break a limit are refused, not quietly applied",
    "G10": "Exclusions respected through ETFs too (warning: disclose)",
    "G11": "Explanation carries the simulation disclaimer",
    "G12": "Every % in the explanation matches a computed number",
    "G13": "Explanation addresses each refused request",
    "G14": "Geography: no country above 70% of the equities (warning: disclose)",
    "G15": "Sector ≤ 30% (warning) and ≤ 40% (blocks); the client's own job sector ≤ 15% (blocks)",
    "G16": "Concentration: at least 8 effective holdings through the ETFs (warning: disclose)",
    "G18": "Consistency: every number shown describes the final weights and data (dh.risk.sync)",
}
# G17 (worst drop in $ vs limit in $) was G7 times the capital: merged into G7 (decision R8, audit A7).


def research_mode() -> bool:
    """harness.toml [data] extra set (decision #41): G19 exists only then, G18 remains the result-consistency rule in every mode."""
    from ..data import load_config
    return bool(load_config().extra)


if research_mode():
    RULES["G19"] = "Dividends of single companies held are covered by their last 3 years' earnings (warning: disclose)"


def _c(rule, ok, detail, warn=False):
    return dict(rule=rule, status="pass" if ok else ("warn" if warn else "fail"), detail=detail, text=RULES[rule])


def check_profile(limits: dict) -> list[dict]:
    m = limits.get("missing") or []
    return [_c("G1", not m, "all essentials known" if not m else f"ask first: {', '.join(m)}")]


def check_strategy(s: dict, limits: dict, profile: dict, holdings=None) -> list[dict]:
    """holdings=None → issuer data from dh.holdings (empty if not built: "direct only"); {} forces direct only."""
    if holdings is None:
        holdings = load_holdings()
    w = s["weights"]
    st = s.get("stats", {})
    out = []
    tot = sum(w.values())
    out.append(_c("G2", min(w.values()) >= 0 and abs(tot - 1) < 1e-6, f"sum {tot:.2%}"))

    bad = sorted(set(w) - set(limits["allowed_assets"]))
    out.append(_c("G3", not bad, "ok" if not bad else f"not allowed: {', '.join(bad)}"))

    eff = look_through(w, holdings)
    caps = limits.get("company_caps") or {}
    singles = {k: v for k, v in eff.items() if k in STOCKS and v > 1e-9}
    cap_of = lambda k: caps.get(k, limits["max_single"])  # noqa: E731
    has_lt = bool(holdings) and any(t in holdings for t in w if t in ETFS)
    note = "" if has_lt or not set(w) & ETFS else " (direct only: no ETF holdings data)"
    if singles:
        # the company closest to (or over) its cap; a 0% cap (loss limit 0%, or horizon <= 2 years) = infinitely over
        k = max(singles, key=lambda k: singles[k] / cap_of(k) if cap_of(k) > 0 else float("inf"))
        over = sorted(t for t, v in singles.items() if v > cap_of(t) + 1e-9)
        out.append(_c("G4", not over, (f"over their cap: {', '.join(f'{t} {singles[t]:.1%} vs {cap_of(t):.1%}' for t in over)}"
                                       if over else f"closest to its cap: {k} {singles[k]:.1%} vs {cap_of(k):.1%}") + note))
    else:
        out.append(_c("G4", True, "no single company held directly" + note))

    cr = sum(v for k, v in w.items() if k in CRYPTO)
    out.append(_c("G5", cr <= limits["max_crypto"] + 1e-9, f"crypto {cr:.0%} vs cap {limits['max_crypto']:.0%}"))

    d = sum(v for k, v in w.items() if k in DEFENSIVE)
    out.append(_c("G6", d >= limits["min_defensive"] - 1e-9, f"defensive {d:.0%} vs floor {limits['min_defensive']:.0%}"))

    if "max_drawdown" in st or s.get("risk"):
        from . import checks
        d2 = checks.d2_capacity(st, limits, profile, s.get("risk"))   # one implementation of the loss rule (R8)
        out.append(dict(rule="G7", status=d2["status"], detail=d2["reason"], text=RULES["G7"]))
    if "ann_vol" in st:
        out.append(_c("G8", st["ann_vol"] <= limits["target_vol"] + 1e-9,
                      f"volatility {st['ann_vol']:.1%} vs target {limits['target_vol']:.0%}", warn=True))

    refused = _refused(limits)
    applied = [tk for tk in refused if w.get(tk, 0) >= profile["requested_positions"][tk] - 1e-9]
    out.append(_c("G9", not applied, "ok" if not applied else f"refused request applied anyway: {', '.join(applied)}"))

    excl = excluded_tickers(profile.get("exclusions"))
    via = sorted(k for k, v in eff.items() if k in excl and k not in w and v > 0)
    out.append(_c("G10", not via, "ok" if not via else f"held through ETFs: {', '.join(via)}", warn=True))
    out += _portfolio_checks(s, limits, profile, holdings)
    if s.get("stamps"):   # strategies the Portfolio built carry stamps; hand-made ones (scenarios) do not
        from ..risk import sync
        stale = [i for i in sync.verify(s) if i.severity == "block"]
        out.append(_c("G18", not stale, "every section describes the final weights" if not stale else
                      "; ".join(i.message for i in stale)))
    return out


def _portfolio_checks(s: dict, limits: dict, profile: dict, holdings: dict) -> list[dict]:
    """G14-G16: the Portfolio's C checks (checks.py), so there is one implementation of each rule."""
    from . import checks
    from . import diversification as dv
    w = s["weights"]
    rep = s.get("diversification") or dv.report(w, holdings=holdings, correlations=False)
    c2, c3, c3b, c5 = (checks.c2_geography(w, holdings), checks.c3_sector(rep), checks.c3b_job_sector(rep, profile),
                       checks.c5_concentration(w, holdings))
    out = [dict(rule="G14", status=c2["status"], detail=c2["reason"], text=RULES["G14"])]
    worst = "fail" if "fail" in (c3["status"], c3b["status"]) else ("warn" if "warn" in (c3["status"], c3b["status"])
                                                                   else "pass")
    out.append(dict(rule="G15", status=worst, detail=f"{c3['reason']}; {c3b['reason']}", text=RULES["G15"]))
    out.append(dict(rule="G16", status=c5["status"], detail=c5["reason"], text=RULES["G16"]))
    if "G19" in RULES and research_mode():
        f7 = checks.f7_dividends(w)
        if f7 is not None:
            out.append(dict(rule="G19", status=f7["status"], detail=f7["reason"], text=RULES["G19"]))
    return out


def _refused(limits) -> list[str]:
    return [f.split()[1].rstrip(":") for f in limits.get("flags", []) if f.startswith("request ")]


PCT = re.compile(r"(-?\d+(?:\.\d+)?)\s?%")


def _known_numbers(s: dict, limits: dict, profile: dict) -> list[float]:
    w = s["weights"]
    vals = [v * 100 for v in w.values()]
    vals += [100 * sum(v for k, v in w.items() if k in grp) for grp in (DEFENSIVE, CRYPTO)]
    vals += [v * 100 for v in s.get("stats", {}).values() if isinstance(v, (int, float))]
    # Request side by side (G, branch portfolio/requests): the "as asked" and "fits" versions' numbers
    for v in ((limits.get("request_comparison") or {}).get(k) for k in ("as_asked", "fits")):
        if v:
            vals += [v[k] * 100 for k in ("max_drawdown", "return_2022", "ann_vol", "growth", "loss_limit")
                     if isinstance(v.get(k), (int, float))]
            vals += [x * 100 for x in v.get("real_weight", {}).values()]
            vals += [x * 100 for x in (v.get("request_at") or {}).values()]
    # Existing portfolio (branch portefeuille_existant): today's and the rebuilt version's numbers, stand-in effects
    ex = limits.get("existing_review") or {}
    for v in (ex.get("current"), ex.get("target")):
        if v:
            vals += [v[k] * 100 for k in ("max_drawdown", "return_2022", "ann_vol", "growth", "loss_limit")
                     if isinstance(v.get(k), (int, float))]
            vals += [x * 100 for x in (v.get("weights") or {}).values()]
    for si in ex.get("stand_ins") or []:
        vals += [x * 100 for d in (si.get("hedge_effect") or {}).values() for x in d.values() if isinstance(x, (int, float))]
        vals += [x * 100 for x in (si.get("checked_against_real") or {}).values() if isinstance(x, (int, float))]
    vals += [float(m) for line in ex.get("critique") or [] for m in PCT.findall(line)]
    # C-F checks (#20): their values and every % in their reasons are computed by code, so the text may quote them
    for c in s.get("checks") or []:
        vals += [x * 100 for x in (c.get("value"), c.get("limit")) if isinstance(x, (int, float)) and abs(x) <= 1]
        vals += [float(m) for m in PCT.findall(c.get("reason") or "")]
    vals += [limits[k] * 100 for k in ("max_drawdown", "target_vol", "min_defensive", "max_single", "max_crypto")
             if limits.get(k) is not None]
    # decision #24: caps of the companies held or requested, the request facts, the loss budget and stock room
    caps = limits.get("company_caps") or {}
    vals += [caps[t] * 100 for t in list(w) + list(profile.get("requested_positions") or {}) if t in caps]
    for r in limits.get("request_checks") or []:
        vals += [v * 100 for k, v in r.items() if k in ("asked", "worst_drop", "loss_at_asked", "fits_up_to") and v]
    if limits.get("loss_limit") is not None and limits.get("min_defensive") is not None:
        room = 1 - limits["min_defensive"]
        vals += [room * 100, room * 100 / MIN_COMPANIES, LOSS_SHARE_ONE_COMPANY * 100,
                 LOSS_SHARE_ONE_COMPANY * limits["loss_limit"] * 100, limits["loss_limit"] * 100]
    vals += [v * 100 for v in (profile.get("requested_positions") or {}).values()]
    vals += [profile.get("max_loss_pct") or 0, (profile.get("withdrawal_share_3y") or 0) * 100]
    return vals


GAIN = re.compile(r"(?:\+\s*|\b(?:gain(?:ed|s)?|rose|earn(?:ed|s)?|grew|up(?: by)?|increased(?: by)?)\s+(?:of\s+|about\s+|by\s+)?)$",
                  re.I)


def _is_gain(text: str, start: int) -> bool:
    """The number is written as a gain: "+6%", "gained 6%", "rose by 6%"... (plain "a drop of 6%" is not)."""
    return bool(GAIN.search(text[max(0, start - 25):start]))


def check_explanation(text: str, s: dict, limits: dict, profile: dict, tol_pp: float = 0.05) -> list[dict]:
    """G12 tolerance 0.05 pt: only rounding to one decimal passes (was 0.5, which let ~1 random number in 4 through).
    The Explainer goes further: its numbers must equal the facts it was given (explainer.check)."""
    known = _known_numbers(s, limits, profile)
    unknown = []
    for m in PCT.finditer(text):
        x = float(m.group(1))
        if _is_gain(text, m.start()):  # "gained 6%" must match a value that really is >= 0 (audit P6: was -6%)
            ok = any(k >= -1e-9 and abs(abs(x) - k) <= tol_pp for k in known)
            if not ok:
                unknown.append(m.group(1) + (" (sign: a loss written as a gain)" if any(abs(abs(x) - abs(k)) <= tol_pp
                                                                                       for k in known) else ""))
        elif not any(abs(abs(x) - abs(k)) <= tol_pp for k in known):
            unknown.append(m.group(1))
    missing_req = [tk for tk in _refused(limits) if tk not in text]
    return [
        _c("G11", DISCLAIMER in text, "present" if DISCLAIMER in text else "disclaimer missing"),
        _c("G12", not unknown, "all numbers traced" if not unknown else
           f"untraced: {', '.join(u.replace(' (', '% (', 1) if ' (' in u else u + '%' for u in unknown)}"),
        _c("G13", not missing_req, "ok" if not missing_req else f"not explained: {', '.join(missing_req)}"),
    ]


def verdict(checks: list[dict]) -> str:
    """pass | warn | fail (fail = send back to the step that produced it)."""
    st = {c["status"] for c in checks}
    return "fail" if "fail" in st else "warn" if "warn" in st else "pass"

