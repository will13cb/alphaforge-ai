"""Company data to judge a dividend: payout ratio and coverage by earnings (and by free cash flow).

    from dh import fundamentals
    fundamentals.dividend_facts("ENB.TO")   # dividends 130% of 3 years' earnings → "not covered"

Two sources, kept apart:
- dividends per share, yield, growth and cuts: OUR data (corporate_actions.csv + prices_daily.csv, trading currency),
  the same files every agent uses;
- payout and coverage: the companies' annual statements from Yahoo Finance (`scripts/build_fundamentals.py`,
  `make data-fundamentals` → data/raw/fundamentals/). Ratios are computed from the statements (dividends paid to
  common shareholders / net income to common shareholders), never taken from Yahoo's `payoutRatio`, which is not
  reliable (152.08 for CAR-UN.TO, i.e. 15 208%, on 2026-11-15). Both numbers come from the same statements, so a
  company reporting in USD but trading in CAD (SHOP.TO) has no currency mix in its ratios.
Snapshot only: statements as published when downloaded, not point-in-time. Never use them in a backtest (look-ahead).
For a fund (ETF), only the distribution yield: payout and coverage describe companies, not funds.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from . import data

# Team rule (a convention, not a regulation), on the LAST 3 FISCAL YEARS together: one year can mislead (BCE.TO paid
# 32% of 2025 earnings, 107% over 3 years, and cut its dividend in 2025). coverage = earnings / dividends.
COVERAGE_THIN = 1.25          # below: "thin" (payout above 80% of earnings)
COVERAGE_MIN = 1.0            # below: "not covered" (dividends exceed earnings): a definition, not a judgment
YEARS = 3
CUT_TOLERANCE = 0.01          # a year's last regular dividend more than 1% below the previous year's = a cut
SPECIAL_MULTIPLE = 3.0        # a payment above 3x the company's median payment = special (COST 2023, CNQ 2022)
ITEMS = ("net_income_common", "dividends_paid_common", "free_cash_flow", "operating_cash_flow")
FOLDER = "fundamentals"

SECTOR_NOTES = {
    "Real Estate": "a REIT's earnings include fair-value changes: payout on FFO/AFFO is the usual measure, not available here",
    "Utilities": "regulated utilities usually pay out most of their earnings; compare with the sector, not the general rule",
    "Financials": "free cash flow is not meaningful for banks and insurers (deposits and policy flows): not computed",
}


def folder(cfg: data.Config | None = None):
    return (cfg or data.load_config()).data_dir / FOLDER


@lru_cache(maxsize=1)
def annual() -> pd.DataFrame:
    """Long format: ticker, period_end, item, value, currency (the statements' currency), source, retrieved."""
    p = folder() / "annual.csv"
    if not p.exists():
        raise SystemExit(f"{p} missing: run `make data-fundamentals`.")
    return pd.read_csv(p, parse_dates=["period_end"])


@lru_cache(maxsize=1)
def info() -> pd.DataFrame:
    """One row per ticker: financial_currency, trading_currency, retrieved, error (why statements are missing)."""
    p = folder() / "info.csv"
    if not p.exists():
        raise SystemExit(f"{p} missing: run `make data-fundamentals`.")
    return pd.read_csv(p).set_index("ticker")


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _ratio(a, b) -> float | None:
    a, b = _num(a), _num(b)
    return None if a is None or b is None or b == 0 else a / b


def dividend_history(ticker: str) -> dict:
    """From our own files (trading currency): trailing-12-month dividend per share, yield, growth, cuts."""
    acts = data.corporate_actions()
    d = acts[(acts.ticker == ticker) & (acts.action == "dividend")].copy()
    px = data.prices()
    p = px[px.ticker == ticker].sort_values("date")
    if p.empty:
        return {"error": f"{ticker}: no prices in the loaded data"}
    end, close = p["date"].iloc[-1], _num(p["close"].iloc[-1])
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    d = d.dropna(subset=["value"]).sort_values("ex_date")
    special = d["value"] > SPECIAL_MULTIPLE * d["value"].median() if len(d) else d["value"].astype(bool)
    regular = d[~special]
    ttm = float(d.loc[d.ex_date > end - pd.Timedelta(days=365), "value"].sum())
    first_year, last_year = p["date"].iloc[0].year + 1, end.year - 1          # full calendar years only
    full = regular[regular.ex_date.dt.year.between(first_year, last_year)]
    by_year = full.groupby(full.ex_date.dt.year)["value"].sum()
    by_year = by_year.reindex(range(first_year, last_year + 1), fill_value=0.0) if last_year >= first_year else by_year
    # cuts and growth on the year's LAST regular payment: a monthly payer with 11 or 13 ex-dates in a calendar year
    # (CAR-UN.TO) or a special dividend (COST, CNQ) is not a cut
    last_pay = full.groupby(full.ex_date.dt.year)["value"].last()
    cuts = [int(y) for y, prev, cur in zip(last_pay.index[1:], last_pay.values[:-1], last_pay.values[1:])
            if prev > 0 and cur < prev * (1 - CUT_TOLERANCE)]
    cuts += [int(y) for y in by_year.index if by_year[y] == 0 and by_year[:y].gt(0).any()]   # stopped paying
    growth = None
    if len(last_pay) >= 2 and last_pay.iloc[0] > 0 and last_pay.iloc[-1] > 0:
        growth = float((last_pay.iloc[-1] / last_pay.iloc[0]) ** (1 / (last_pay.index[-1] - last_pay.index[0])) - 1)
    return {"dps_ttm": round(ttm, 4), "yield_ttm": _ratio(ttm, close),
            "dps_by_year": {int(k): round(float(v), 4) for k, v in by_year.items()},
            "special_dividends": {str(r.ex_date.date()): float(r.value) for r in d[special].itertuples()},
            "dps_growth_per_year": growth, "cuts": sorted(set(cuts)), "as_of": str(end.date()),
            "source": "corporate_actions.csv and prices_daily.csv (Yahoo Finance via the organizers' script)"}


def coverage(ticker: str, years: int = YEARS) -> dict:
    """From the annual statements: payout and coverage for the last fiscal year and the last `years` together."""
    a = annual()
    a = a[a.ticker == ticker]
    if a.empty:
        why = info()["error"].get(ticker) if ticker in info().index else None
        return {"error": f"{ticker}: no statements" + (f" ({why})" if isinstance(why, str) and why else "")}
    wide = a.pivot_table(index="period_end", columns="item", values="value", aggfunc="first").sort_index()
    wide = wide.reindex(columns=list(ITEMS))
    last = wide.iloc[-1]
    recent = wide.tail(years)
    ni, div, fcf = last["net_income_common"], last["dividends_paid_common"], last["free_cash_flow"]
    sum_ni, sum_div = recent["net_income_common"].sum(min_count=1), recent["dividends_paid_common"].sum(min_count=1)
    return {"fiscal_year_end": str(wide.index[-1].date()), "currency": a["currency"].iloc[0],
            "net_income_common": _num(ni), "dividends_paid_common": _num(div), "free_cash_flow": _num(fcf),
            "payout_ratio": _ratio(div, ni) if (_num(ni) or 0) > 0 else None,
            "earnings_coverage": _ratio(ni, div), "fcf_coverage": _ratio(fcf, div),
            "net_income_3y": _num(sum_ni), "dividends_3y": _num(sum_div),
            "payout_ratio_3y": _ratio(sum_div, sum_ni) if (_num(sum_ni) or 0) > 0 else None,
            "earnings_coverage_3y": _ratio(sum_ni, sum_div),
            "years_used": [str(x.date()) for x in recent.index],
            "retrieved": str(a["retrieved"].iloc[0]), "source": str(a["source"].iloc[0])}


def verdict(cov: dict, hist: dict | None = None, sector: str | None = None) -> tuple[str, str]:
    """(status, reason) on the last 3 fiscal years together. Status: no dividend / not measurable (REIT) / loss /
    not covered / thin / covered / no data. A free-cash-flow shortfall (last year) is added to the reason, except for
    banks and insurers, where free cash flow means nothing."""
    div = cov.get("dividends_paid_common")
    paid = (div or 0) > 0 or ((hist or {}).get("dps_ttm") or 0) > 0
    if not paid:
        return "no dividend", "no dividend paid in the last fiscal year nor the last 12 months"
    if sector == "Real Estate":
        return "not measurable", ("a REIT: its earnings include fair-value changes; the usual measure (payout of "
                                  "FFO/AFFO) is not available here")
    ni, ni3, c3 = cov.get("net_income_common"), cov.get("net_income_3y"), cov.get("earnings_coverage_3y")
    if ni is None or ni3 is None or cov.get("dividends_3y") is None:
        return "no data", "net income or dividends paid missing from the statements"
    n = len(cov.get("years_used") or []) or YEARS
    if ni <= 0 or ni3 <= 0:
        status, reason = "loss", (f"dividends paid while net income was {ni:,.0f} {cov['currency']} in the last fiscal year"
                                  if ni <= 0 else f"dividends paid while the last {n} years lost money together")
    elif c3 < COVERAGE_MIN:
        status, reason = "not covered", f"dividends are {cov['payout_ratio_3y']:.0%} of the last {n} years' earnings (more than earned)"
    elif c3 < COVERAGE_THIN:
        status, reason = "thin", (f"dividends are {cov['payout_ratio_3y']:.0%} of the last {n} years' earnings "
                                  f"(above {1 / COVERAGE_THIN:.0%})")
    else:
        status, reason = "covered", f"dividends are {cov['payout_ratio_3y']:.0%} of the last {n} years' earnings"
    fcf = cov.get("fcf_coverage")
    if sector != "Financials" and fcf is not None and fcf < COVERAGE_MIN:
        reason += ("; free cash flow was negative last year (the dividend was paid from other sources)" if fcf < 0
                   else f"; free cash flow covered only {fcf:.1f}× the dividend last year")
    return status, reason


def dividend_facts(ticker: str) -> dict:
    """Everything to judge one dividend, with sources and caveats. Errors are returned, never raised."""
    try:
        uni = data.universe().set_index("ticker")
    except SystemExit as e:
        return {"ticker": ticker, "error": str(e)}
    if ticker not in uni.index:
        return {"ticker": ticker, "error": f"{ticker} is not in the loaded universe"}
    row = uni.loc[ticker]
    out = {"ticker": ticker, "name": row.get("name"), "sector": row.get("sector"), "asset_class": row.get("asset_class")}
    hist = dividend_history(ticker)
    out["history"] = hist
    if row.get("asset_class") != "equity":
        out["status"] = "fund"
        y, cuts = hist.get("yield_ttm"), hist.get("cuts") or []
        out["reason"] = ("a fund: payout and coverage describe companies, not funds"
                         + (f"; distributions {y:.1%} of the price over 12 months" if y else "; no distribution in 12 months")
                         + (f"; distributions lower in {', '.join(map(str, cuts))}" if cuts else ""))
        return out
    try:
        cov = coverage(ticker)
    except SystemExit as e:
        cov = {"error": str(e)}
    out["coverage"] = cov
    if "error" in cov:
        out["status"], out["reason"] = "no data", cov["error"]
    else:
        if row.get("sector") == "Financials":
            cov["fcf_coverage"] = None
        out["status"], out["reason"] = verdict(cov, hist, row.get("sector"))
    notes = [SECTOR_NOTES[row.get("sector")]] if row.get("sector") in SECTOR_NOTES else []
    try:
        fin = info()["financial_currency"].get(ticker)
    except SystemExit:
        fin = None
    if isinstance(fin, str) and fin != row.get("currency"):
        notes.append(f"statements in {fin}, shares trade in {row.get('currency')}: the ratios are unitless "
                     "(both from the statements); the yield is in the trading currency")
    notes.append("snapshot of the latest published statements: not point-in-time, never for a backtest")
    out["notes"] = notes
    return out


COVERED = ("covered", "thin")          # a dividend the company earns (thin: 80-100% of 3 years' earnings)


def held_dividends(weights: dict) -> list[dict] | None:
    """For each single company held that pays a dividend: ticker, status, 3-year payout, reason. None when the
    statements are not downloaded (callers then say nothing rather than guess)."""
    from .agents.rules import STOCKS
    try:
        annual()
    except SystemExit:
        return None
    out = []
    for t in sorted((t for t, w in weights.items() if t in STOCKS and w > 0), key=lambda t: -weights[t]):
        d = dividend_facts(t)
        if d.get("status") in (None, "no dividend", "no data") or "error" in d:
            continue
        out.append({"ticker": t, "status": d["status"], "payout_3y": (d.get("coverage") or {}).get("payout_ratio_3y"),
                    "reason": d["reason"]})
    return out


def covered_payers(weights: dict) -> set[str] | None:
    """Single companies held whose dividend is covered (or thin) on 3 years; None without statements."""
    held = held_dividends(weights)
    return None if held is None else {h["ticker"] for h in held if h["status"] in COVERED}

