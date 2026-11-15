"""Risk/return numbers (every number an agent quotes comes from here) + the results log.

    log_run(0.9, experiment="governance-checks", metric="pass_rate", persona="robert")
"""

from __future__ import annotations

import csv
import getpass
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .data import RESULTS

TRADING_DAYS = 252  # fallback only, when the returns carry no dates (decision #12)
MIN_SPAN_DAYS = 90  # below this, the observed frequency is too noisy: fall back to TRADING_DAYS


def periods_per_year(returns) -> float:
    """Rows per year actually in the data: (rows - 1) / years between first and last date.

    About 261 on the weekday calendar of harness.toml (holidays kept as 0% days), so a 5-year series is
    annualised over 5 years, not 5.18. Falls back to TRADING_DAYS without a date index or on < 90 days.
    """
    idx = getattr(returns, "dropna", lambda: returns)()
    idx = getattr(idx, "index", None)
    if not isinstance(idx, pd.DatetimeIndex) or len(idx) < 2:
        return float(TRADING_DAYS)
    span = (idx[-1] - idx[0]).days
    return (len(idx) - 1) / (span / 365.25) if span >= MIN_SPAN_DAYS else float(TRADING_DAYS)


def _r(returns) -> np.ndarray:
    r = np.asarray(returns, dtype=float)
    return r[~np.isnan(r)]


def _p(returns, periods) -> float:
    return periods_per_year(returns) if periods is None else float(periods)


def ann_return(returns, periods: float | None = None) -> float:
    """Annualised compound return (CAGR). periods=None: observed rows per year (periods_per_year)."""
    p, r = _p(returns, periods), _r(returns)
    return float(np.prod(1 + r) ** (p / len(r)) - 1) if len(r) else 0.0


def ann_vol(returns, periods: float | None = None) -> float:
    p, r = _p(returns, periods), _r(returns)
    return float(r.std(ddof=1) * np.sqrt(p)) if len(r) > 1 else 0.0


def sharpe(returns, periods: float | None = None, rf: float = 0.0) -> float:
    """Annualised Sharpe; rf is an annual rate (e.g. 0.03)."""
    p = _p(returns, periods)
    r = _r(returns) - rf / p
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    return float(np.sqrt(p) * r.mean() / sd) if sd > 0 else 0.0


def max_drawdown(returns) -> float:
    """Most negative peak-to-trough drop of the compounded curve (e.g. -0.23)."""
    r = _r(returns)
    if not len(r):
        return 0.0
    equity = np.cumprod(1 + r)
    return float((equity / np.maximum.accumulate(equity) - 1).min())


def summary(rets: pd.DataFrame, rf: float = 0.0) -> pd.DataFrame:
    """One row per column: ann_return, ann_vol, sharpe, max_drawdown."""
    return pd.DataFrame(
        {
            c: {
                "ann_return": ann_return(rets[c]),
                "ann_vol": ann_vol(rets[c]),
                "sharpe": sharpe(rets[c], rf=rf),
                "max_drawdown": max_drawdown(rets[c]),
            }
            for c in rets.columns
        }
    ).T


def portfolio_returns(rets: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Daily-rebalanced fixed-weight portfolio (weights normalised to sum to 1).

    Only days where EVERY held asset has a return (decision #31): an asset that didn't trade yet is missing, not
    flat. Filling it with 0% made a young asset look calm and hid risk once histories differ in length. On the
    starter pack (every asset on every day after forward-filling) the result is unchanged."""
    w = pd.Series(weights, dtype=float)
    w = w / w.sum()
    return rets[w.index].dropna() @ w


# ---- ETF look-through (what the portfolio really owns) ----

def risk_contributions(rets: pd.DataFrame, weights: dict[str, float]) -> dict:
    """Each holding's share of the portfolio's risk (variance): w_i·(Σw)_i / w'Σw, summing to 1. Uses only the
    covariance of daily returns, never an average return, so it describes risk without forecasting anything (the
    stable part of Markowitz, decision #40). A holding whose risk share is far above its weight is where the swings
    come from (e.g. 10% of the money, 25% of the risk). Returns {"shares": {ticker: share}, "ann_vol": float}."""
    w = pd.Series({t: v for t, v in weights.items() if v > 0}, dtype=float)
    w = w / w.sum()
    cov = rets[list(w.index)].dropna().cov()
    sw = cov.values @ w.values
    var = float(w.values @ sw)
    if var <= 0:
        return {"shares": {t: 0.0 for t in w.index}, "ann_vol": 0.0}
    shares = dict(zip(w.index, (w.values * sw) / var))
    return {"shares": {t: float(v) for t, v in shares.items()}, "ann_vol": float(np.sqrt(var * periods_per_year(rets)))}


def look_through(weights: dict[str, float], holdings: dict[str, dict[str, float]] | None = None) -> dict[str, float]:
    """Effective exposure per underlying: direct weight + sum over ETFs of (ETF weight × holding weight).

    holdings = {"SPY": {"NVDA": 0.07, "AAPL": 0.06, ...}, ...} (issuer files, a snapshot date: document it).
    The part of an ETF not listed in `holdings` is kept as "<ETF> (other)". ETFs with no holdings data stay
    as themselves, so the result always sums to the portfolio's total weight.
    """
    out: dict[str, float] = {}
    for tk, w in weights.items():
        h = (holdings or {}).get(tk)
        if not h:
            out[tk] = out.get(tk, 0.0) + w
            continue
        for u, hw in h.items():
            out[u] = out.get(u, 0.0) + w * hw
        rest = 1 - sum(h.values())
        if rest > 1e-9:
            out[f"{tk} (other)"] = out.get(f"{tk} (other)", 0.0) + w * rest
    return out


def overlap(h_a: dict[str, float], h_b: dict[str, float]) -> float:
    """Share two funds have in common: sum over names of min(weight in A, weight in B). 1 = same fund."""
    return float(sum(min(w, h_b.get(k, 0.0)) for k, w in h_a.items()))


# ---- results log (append-only, merge=union in git) ----

FIELDS = ["run_id", "timestamp", "author", "commit", "experiment", "persona",
          "metric", "value", "notes"]


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def log_run(value: float, experiment: str, metric: str, persona: str = "", notes: str = "",
            results: Path = RESULTS) -> str:
    """Commit your code first so `commit` points at it."""
    commit = _git("rev-parse", "--short", "HEAD") or "uncommitted"
    if _git("status", "--porcelain", "--untracked-files=no", "--", ".", ":(top,exclude)results.csv"):
        commit += "-dirty"
    now = datetime.now(timezone.utc)
    author = os.environ.get("DH_AUTHOR") or _git("config", "user.name") or getpass.getuser()
    run_id = f"{now:%m%d-%H%M%S}-{author.split()[0].lower()}-{os.urandom(2).hex()}"
    new = not results.exists() or results.stat().st_size == 0
    with results.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(dict(run_id=run_id, timestamp=now.isoformat(timespec="seconds"), author=author,
                        commit=commit, experiment=experiment, persona=persona, metric=metric,
                        value=f"{value:.6g}", notes=notes))
    return run_id


def board(results: Path = RESULTS) -> pd.DataFrame:
    """Latest value per (experiment, persona, metric)."""
    df = pd.read_csv(results)
    if df.empty:
        return df
    return df.sort_values("timestamp").groupby(["experiment", "persona", "metric"], dropna=False).tail(1)
