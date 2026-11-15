"""Portfolio checks C-F (layer 3, branch portfolio/checks). DETERMINISTIC, no LLM.

Every check returns the same shape (notes/system-design.md, "What each check returns"):
    {check, value, limit, status, reason, source}      status: "pass" · "warn" (disclose) · "fail" (blocks)
They go into strategies[i]["checks"], the trace, the Guardian (G14-G17 call these functions) and the Critic's tools.

    C  diversification   C1 company cap · C2 geography · C3 sector · C3b job sector · C4 classes · C5 concentration
                         · C6 duplicates and overlap        (wraps diversification.report, doesn't rewrite it)
    D  risk vs client    D1 tolerance · D2 drawdown capacity in % and $ · D3 stress (2022, worst 12 months, CVaR)
    E  goal              chance of reaching the target, risk-only view first
    F  profile fit       F1 objective · F2 horizon · F3 liquidity · F4 knowledge · F5 ESG · F6 exclusions

Thresholds: rules.py (decision #20, team assumptions). Data limits are said in the reason: countries and sectors of
ETF holdings are only known where the issuer file has them (SPY's has neither), so they are lower bounds.
"""

from __future__ import annotations

from ..data import period_label

from functools import lru_cache

import pandas as pd

from .. import metrics
from ..holdings import default_path, holdings as load_holdings
from . import diversification as dv
from . import market
from .rules import (BEGINNER_MAX_KNOWLEDGE, CORR_WARN, CRYPTO, DEFENSIVE, DIVIDEND_PAYERS, EQUITY_ETFS, ETF_ASSUMED_LINES, ETFS, EXCLUSIONS,
                    GOAL_MIN_PROB, MAX_COUNTRY_EQUITY, MAX_JOB_SECTOR, MIN_EFFECTIVE_N, OVERLAP_WARN, SECTOR_WARN,
                    STOCKS, TOLERANCE_CLOSE, excluded_tickers, horizon_max_growth)

FOSSIL = EXCLUSIONS["fossil_fuels"]  # one list, in rules.py (audit P10)


def _c(check: str, value, limit, status: str, reason: str, source: str) -> dict:
    return {"check": check, "value": value, "limit": limit, "status": status, "reason": reason, "source": source}


def _status(fail: bool = False, warn: bool = False) -> str:
    return "fail" if fail else ("warn" if warn else "pass")


@lru_cache(maxsize=2)
def _holding_countries(path: str | None = None) -> dict[str, str]:
    """Country of each ETF holding, from the issuer file (empty when the file or the column is missing)."""
    try:
        df = pd.read_csv(default_path() if path is None else path, usecols=["holding", "country"])
    except (FileNotFoundError, ValueError):
        return {}
    return {h: c for h, c in zip(df.holding, df.country) if isinstance(c, str) and c.strip()}


# ---- C. diversification -------------------------------------------------------------------------------

def c1_company(w: dict, limits: dict, holdings: dict) -> dict:
    """Each company through the ETFs vs ITS OWN cap (`limits["company_caps"]`, decision #24), like G4.
    Reports the company furthest over its cap, else the one closest to it. `max_single` only when no per-company caps."""
    eff = metrics.look_through(w, holdings)
    caps = limits.get("company_caps") or {}
    held = [(k, v, caps.get(k, limits["max_single"])) for k, v in eff.items() if k in STOCKS and v > 0]
    if not held:
        return _c("C1", 0.0, limits["max_single"], "pass", "no single company held", "dh.metrics.look_through")
    k, v, cap = max(held, key=lambda x: x[1] - x[2])          # most over (or least under) its own cap
    over = [f"{t} {x:.1%} vs {c:.1%}" for t, x, c in held if x > c + 1e-9]
    reason = (f"over their own cap: {', '.join(over)}" if over
              else f"closest to its cap: {k} {v:.1%} vs {cap:.1%} (each company has its own cap, from its worst drop)")
    return _c("C1", round(v, 4), round(cap, 4), _status(fail=bool(over)), reason + " — counted through the ETFs",
              "dh.metrics.look_through, profiler company_caps")


def c2_geography(w: dict, holdings: dict) -> dict:
    """Country of the equities: holdings' countries where the issuer file has them, else where the holdings are
    (a catalogue's `exposure`: XEF.TO → Developed ex-North America), else the country of listing."""
    hc = _holding_countries()
    eq = {t: v for t, v in w.items() if t in STOCKS or t in EQUITY_ETFS}
    listing = market.exposures(list(eq))
    by: dict[str, float] = {}
    known = 0.0
    for t, v in eq.items():
        h = holdings.get(t) or {}
        mapped = {k: x for k, x in h.items() if k in hc}
        for k, x in mapped.items():
            by[hc[k]] = by.get(hc[k], 0.0) + v * x
            known += v * x
        rest = v * (1 - sum(mapped.values()))
        by[listing[t]] = by.get(listing[t], 0.0) + rest
    tot = sum(eq.values())
    if tot <= 0:
        return _c("C2", None, MAX_COUNTRY_EQUITY, "pass", "no equities", "market.countries")
    share = {k: v / tot for k, v in by.items()}
    top = max(share.items(), key=lambda kv: kv[1])
    cur = {}
    for t, v in w.items():
        c = dv.currency_of(t)
        cur[c] = cur.get(c, 0.0) + v
    basis = "holdings' countries where known, else country of listing" if known else "country of listing"
    from .. import products
    if set(eq) & set(products.column_map("exposure")):   # a catalogue product: its holdings' region, not its listing
        basis = basis.replace("country of listing", "where the holdings are (catalogue), else country of listing")
    return _c("C2", round(top[1], 4), MAX_COUNTRY_EQUITY, _status(warn=top[1] > MAX_COUNTRY_EQUITY + 1e-9),
              f"{top[0]} {top[1]:.0%} of the equities ({basis}); currency "
              + ", ".join(f"{k} {v:.0%}" for k, v in sorted(cur.items(), key=lambda kv: -kv[1])),
              "market.countries, dh.holdings")


def c3_sector(rep: dict) -> dict:
    ls = rep["largest_sector"]
    lower = rep["look_through_coverage"] < 0.999
    status = _status(fail=ls["weight"] > dv.MAX_SECTOR + 1e-9, warn=ls["weight"] > SECTOR_WARN + 1e-9)
    head = (f"largest sector {ls['name']} {ls['weight']:.0%}" if ls["weight"] > 0
            else "no sector known (broad ETFs without holdings data)")
    return _c("C3", ls["weight"], SECTOR_WARN, status,
              f"{head} (⚠ above {SECTOR_WARN:.0%}, ✘ above {dv.MAX_SECTOR:.0%})"
              + (f"; lower bound, {rep['look_through_coverage']:.0%} of equity ETFs looked through" if lower else ""),
              "diversification.report")


def c3b_job_sector(rep: dict, profile: dict) -> dict:
    job = profile.get("employment_sector")
    if not job:
        return _c("C3b", None, MAX_JOB_SECTOR, "pass", "job sector not given", "profile.employment_sector")
    v = float(rep["sectors"].get(job, 0.0))
    return _c("C3b", round(v, 4), MAX_JOB_SECTOR, _status(fail=v > MAX_JOB_SECTOR + 1e-9),
              f"{job} (the client's own job sector) {v:.0%} vs cap {MAX_JOB_SECTOR:.0%}: income and savings would "
              "fall together" + (" (lower bound)" if rep["look_through_coverage"] < 0.999 else ""),
              "diversification.report, profile.employment_sector")


def c4_classes(rep: dict) -> dict:
    n = rep["n_asset_classes"]
    return _c("C4", n, dv.MIN_CLASSES, _status(fail=n < dv.MIN_CLASSES),
              f"{n} asset classes: " + ", ".join(f"{k} {v:.0%}" for k, v in rep["asset_classes"].items()),
              "diversification.report")


def effective_n(w: dict, holdings: dict) -> float:
    """1 / Σ w² on look-through weights; an ETF (or remainder) without holdings data = ETF_ASSUMED_LINES equal lines."""
    eff = metrics.look_through(w, holdings)
    s = 0.0
    for k, v in eff.items():
        if k.endswith("(other)") or (k in ETFS and k not in holdings):
            s += v * v / ETF_ASSUMED_LINES
        else:
            s += v * v
    return 1 / s if s > 0 else 0.0


def c5_concentration(w: dict, holdings: dict) -> dict:
    n = effective_n(w, holdings)
    return _c("C5", round(n, 1), MIN_EFFECTIVE_N, _status(warn=n < MIN_EFFECTIVE_N),
              f"{n:.1f} effective holdings (1/Σw² through the ETFs; an ETF without holdings data counts as "
              f"{ETF_ASSUMED_LINES} equal lines)", "dh.metrics.look_through")


def c6_duplicates(w: dict, rep: dict, holdings: dict, rets: pd.DataFrame | None) -> dict:
    hard = rep["redundant_pairs"]
    soft = []
    if rets is not None and len(w) > 1:
        names = [t for t in w if t in rets.columns]
        c = dv.corr_matrix(rets[names])  # weekly for crypto pairs (audit P21), same as the C6 ✘ test
        soft = [(a, b, float(c.loc[a, b])) for i, a in enumerate(names) for b in names[i + 1:]
                if CORR_WARN < c.loc[a, b] < dv.MAX_PAIR_CORR]
    eq = sorted(t for t in w if t in EQUITY_ETFS and t in holdings)
    overlaps = [(a, b, metrics.overlap(holdings[a], holdings[b])) for i, a in enumerate(eq) for b in eq[i + 1:]]
    overlaps = [o for o in overlaps if o[2] > OVERLAP_WARN]
    parts = [f"same bet twice {p['a']}/{p['b']} {p['correlation']:.3f}" for p in hard]
    parts += [f"{a}/{b} correlated {x:.3f}" for a, b, x in soft] + [f"{a}/{b} share {x:.0%}" for a, b, x in overlaps]
    worst = max([p["correlation"] for p in hard] + [x for _, _, x in soft] + [0.0])
    return _c("C6", round(worst, 3), CORR_WARN, _status(fail=bool(hard), warn=bool(soft or overlaps)),
              "; ".join(parts) or "no near-duplicate holdings", "diversification.report, dh.metrics.overlap")


# ---- D. risk vs the client --------------------------------------------------------------------------

def d1_tolerance(stats: dict, profile: dict) -> dict:
    tol = (profile.get("max_loss_pct") or 0) / 100
    dd = abs(stats.get("max_drawdown", 0.0))
    st = _status(fail=dd > tol + 1e-9, warn=dd > TOLERANCE_CLOSE * tol)
    return _c("D1", round(dd, 4), tol, st, f"worst drop {dd:.1%} vs the {tol:.0%} the client said they'd accept"
              + (" (close to it)" if st == "warn" else ""), "market.strategy_stats")


def d2_capacity(stats: dict, limits: dict, profile: dict) -> dict:
    dd = abs(stats.get("max_drawdown", 0.0))
    lim = limits.get("loss_limit", limits["max_drawdown"])
    cap = profile.get("capital")
    money = f" = {cap * dd:,.0f} $ vs {cap * lim:,.0f} $" if cap else ""
    return _c("D2", round(dd, 4), lim, _status(fail=dd > lim + 1e-9),
              f"worst drop {dd:.1%} vs loss limit {lim:.0%}{money}", "market.strategy_stats, profiler loss limit")


def d3_stress(stats: dict, limits: dict) -> dict:
    lim = limits.get("loss_limit", limits["max_drawdown"])
    w12 = stats.get("worst_12m")
    s22 = stats.get("stress_2022_drawdown")
    cv = stats.get("cvar_95")
    warn = w12 is not None and -w12 > lim + 1e-9
    return _c("D3", w12, lim, _status(warn=warn),
              f"2022 sell-off drop {s22:.1%}, worst 12 months {w12:.1%}, CVaR 95% {cv:.2%} a day"
              if None not in (w12, s22, cv) else "stress figures unavailable", "market.strategy_stats")


# ---- E. goal ---------------------------------------------------------------------------------------

def e_goal(outlook: dict | None, profile: dict) -> dict:
    if not outlook:
        return _c("E", None, GOAL_MIN_PROB, "pass", "no capital given: no goal simulation", "market.goal_outlook")
    ro = outlook["risk_only"]
    if profile.get("target_amount"):
        p = ro["prob_target"]
        return _c("E", round(p, 3), GOAL_MIN_PROB, _status(warn=p < GOAL_MIN_PROB),
                  f"{p:.0%} chance of reaching {profile['target_amount']:,.0f} $ without assuming past returns "
                  f"repeat ({outlook['replay']['prob_target']:.0%} if {period_label()} repeated); {ro['prob_loss']:.0%} chance "
                  "of ending below what was put in", "market.goal_outlook")
    return _c("E", round(ro["prob_loss"], 3), None, "pass",
              f"no target given; {ro['prob_loss']:.0%} chance of ending below what was put in (risk-only view)",
              "market.goal_outlook")


# ---- F. profile fit ----------------------------------------------------------------------------------

def f_profile(w: dict, profile: dict, limits: dict, holdings: dict) -> list[dict]:
    growth = sum(v for t, v in w.items() if t not in DEFENSIVE)
    out = []
    obj = profile.get("objective")
    if obj == "safety_cushion":
        out.append(_c("F1", round(growth, 4), 0.05, _status(fail=growth > 0.05 + 1e-9),
                      f"safety cushion: growth {growth:.0%} (should be close to 0)", "profile.objective"))
    elif obj == "income":
        payers, src, what = DIVIDEND_PAYERS, "profile.objective", "dividend payers"
        if data_extra():  # research mode: payers judged on their coverage, plus dividend ETFs (decision #41)
            from .. import fundamentals, products
            covered = fundamentals.covered_payers(w)
            if covered is not None:
                funds = {t for t, sc in products.column_map("sub_class").items() if sc == "factor_dividend"}
                payers, src = covered | funds, "profile.objective, dh.fundamentals"
                what = "dividend payers covered by their earnings or dividend ETFs"
        inc = sum(v for t, v in w.items() if t in DEFENSIVE or t in payers)
        out.append(_c("F1", round(inc, 4), 0.5, _status(warn=inc < 0.5),
                      f"income objective: {inc:.0%} in bonds or {what}", src))
    else:
        out.append(_c("F1", obj, None, "pass", f"objective {obj}: no extra constraint", "profile.objective"))
    hcap = limits.get("horizon_max_growth", horizon_max_growth(profile["horizon_years"]))
    out.append(_c("F2", round(growth, 4), hcap, _status(fail=growth > hcap + 1e-9),
                  f"growth {growth:.0%} vs {hcap:.0%} allowed for a {profile['horizon_years']:g}-year horizon",
                  "rules.horizon_max_growth (#22)"))
    liq = limits.get("liquidity_floor") or 0.0
    out.append(_c("F3", round(1 - growth, 4), liq, _status(fail=1 - growth < liq - 1e-9),
                  f"defensive {1 - growth:.0%} vs {liq:.0%} needed within 3 years", "profile.withdrawal_share_3y"))
    beginner = limits.get("knowledge_score", 5) <= BEGINNER_MAX_KNOWLEDGE
    risky = sorted(t for t in w if t in STOCKS or t in CRYPTO)
    out.append(_c("F4", limits.get("knowledge_score"), BEGINNER_MAX_KNOWLEDGE + 1,
                  _status(fail=beginner and bool(risky)),
                  ("beginner: broad ETFs only" + (f", but holds {', '.join(risky)}" if risky else ""))
                  if beginner else f"knowledge {limits.get('knowledge_score')}/5: single names allowed",
                  "profiler knowledge score"))
    esg = "esg" in (profile.get("interests") or [])
    fossil = sorted(t for t in w if t in FOSSIL)
    out.append(_c("F5", "esg" if esg else None, None, _status(warn=esg and (bool(fossil) or "SPY" in w)),
                  (f"ESG interest: " + ("holds " + ", ".join(fossil + (["SPY"] if "SPY" in w else []))
                                        if fossil or "SPY" in w else "no fossil-fuel names, ESGV used"))
                  if esg else "no ESG preference", "profile.interests"))
    excl = excluded_tickers(profile.get("exclusions"))
    direct = sorted(t for t in w if t in excl)
    via = sorted(k for k, v in metrics.look_through(w, holdings).items() if k in excl and k not in w and v > 0)
    out.append(_c("F6", direct + via, [], _status(fail=bool(direct), warn=bool(via)),
                  ("held directly: " + ", ".join(direct) + ". " if direct else "")
                  + ("held through ETFs: " + ", ".join(via) if via else ("" if direct else "none held")),
                  "profile.exclusions, dh.metrics.look_through"))
    return out


# ---- all of them -------------------------------------------------------------------------------------

def f7_dividends(w: dict) -> dict | None:
    """Research mode (harness.toml [data] extra): single companies whose dividend is not covered by their last 3
    years' earnings (dh.fundamentals). ⚠ only, never ✘: earnings understate some businesses' cash (pipelines), so it
    discloses. None when the statements are not downloaded (no row rather than a guess)."""
    from .. import fundamentals
    names = sorted(t for t in w if t in STOCKS and w[t] > 0)
    try:
        facts = {t: fundamentals.dividend_facts(t) for t in names}
        fundamentals.annual()
    except SystemExit:
        return None
    bad = {t: f for t, f in facts.items() if f.get("status") in ("not covered", "loss")}
    reason = ("; ".join(f"{t}: {f['reason']}" for t, f in bad.items()) if bad
              else f"every dividend payer held is covered by its last {fundamentals.YEARS} years' earnings"
              if names else "no single company held")
    return _c("F7", sorted(bad), [], _status(warn=bool(bad)), reason, "dh.fundamentals (annual statements, Yahoo Finance)")


def run(strategy: dict, profile: dict, limits: dict, rets: pd.DataFrame | None = None, holdings=None) -> list[dict]:
    """Every C-F check for one strategy (needs strategy["weights"], ["stats"], optionally ["outlook"])."""
    holdings = load_holdings() if holdings is None else holdings
    w = strategy["weights"]
    rep = strategy.get("diversification") or dv.report(w, rets=rets, holdings=holdings)
    st = strategy.get("stats", {})
    return [c1_company(w, limits, holdings), c2_geography(w, holdings), c3_sector(rep), c3b_job_sector(rep, profile),
            c4_classes(rep), c5_concentration(w, holdings), c6_duplicates(w, rep, holdings, rets),
            d1_tolerance(st, profile), d2_capacity(st, limits, profile), d3_stress(st, limits),
            e_goal(strategy.get("outlook"), profile), *f_profile(w, profile, limits, holdings),
            *([f7] if data_extra() and (f7 := f7_dividends(w)) is not None else [])]


def data_extra() -> bool:
    """Research mode: an extra product catalogue is configured (harness.toml [data] extra)."""
    from ..data import load_config
    return bool(load_config().extra)


def summary(checks: list[dict]) -> str:
    n = {s: sum(c["status"] == s for c in checks) for s in ("pass", "warn", "fail")}
    bad = [f"{c['check']} {c['status']}" for c in checks if c["status"] != "pass"]
    return f"{n['pass']} ✔, {n['warn']} ⚠, {n['fail']} ✘" + (f" ({', '.join(bad)})" if bad else "")
