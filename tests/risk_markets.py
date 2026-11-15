"""Synthetic markets for the dh.risk tests: known parameters, so a method's answer can be compared with the truth.

Three assets: EQ (stocks), BOND (aggregate bonds), CASH. Daily simple returns on a weekday calendar.
Regimes (5. stress scenarios): calm, equity crash, rate shock (bonds fall), joint drop (stocks AND bonds fall,
like 2022), persistent inflation (cash pays more, real returns negative), high volatility, exceptional one-day shock.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

D = 261  # weekdays per year, as dh.metrics.periods_per_year on this calendar

BASE = {"mu": np.array([0.07, 0.03, 0.025]), "vol": np.array([0.16, 0.05, 0.003]),
        "corr": np.array([[1, 0.1, 0], [0.1, 1, 0], [0, 0, 1]])}
REGIMES = {
    "calm": {},
    "equity_crash": {"shock": {"EQ": -0.35}},
    "rate_shock": {"shock": {"BOND": -0.15}},
    "joint_drop": {"shock": {"EQ": -0.20, "BOND": -0.13}},
    "inflation": {"mu": np.array([0.05, 0.0, 0.05])},
    "high_vol": {"vol": np.array([0.32, 0.08, 0.003])},
    "exceptional": {"jump": {"EQ": -0.20}},
}


def market(years: float = 5, regime: str = "calm", seed: int = 0, start: str = "2021-11-15") -> pd.DataFrame:
    """One history. 'shock' spreads a total drop over the first year (like 2022); 'jump' is one day."""
    p = {**BASE, **{k: v for k, v in REGIMES[regime].items() if k in ("mu", "vol")}}
    rng = np.random.default_rng(seed)
    n = int(years * D)
    sd = p["vol"] / np.sqrt(D)
    x = rng.multivariate_normal(p["mu"] / D, p["corr"] * np.outer(sd, sd), n)
    df = pd.DataFrame(x, index=pd.bdate_range(start, periods=n), columns=["EQ", "BOND", "CASH"])
    for t, total in REGIMES[regime].get("shock", {}).items():
        df.iloc[:D, df.columns.get_loc(t)] += (1 + total) ** (1 / D) - 1
    for t, total in REGIMES[regime].get("jump", {}).items():
        df.iloc[D // 2, df.columns.get_loc(t)] = total
    return df


def mix(df: pd.DataFrame, share: float) -> pd.Series:
    """Growth share in EQ, the rest in BOND, rebalanced daily (as dh.metrics.portfolio_returns)."""
    return share * df["EQ"] + (1 - share) * df["BOND"]


def true_exceedance(share: float, limit: float, years: float, n: int = 400, seed: int = 99) -> float:
    """P(drawdown over `years` > limit) under the calm model's TRUE parameters (fresh futures)."""
    from dh.risk.loss_model import drawdowns
    rng = np.random.default_rng(seed)
    sd = BASE["vol"] / np.sqrt(D)
    x = rng.multivariate_normal(BASE["mu"] / D, BASE["corr"] * np.outer(sd, sd), (n, int(years * D)))
    port = share * x[:, :, 0] + (1 - share) * x[:, :, 1]
    return float(np.mean(-drawdowns(port) > limit))
