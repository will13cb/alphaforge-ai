"""Do the risk-level thresholds in rules.py hold on 2021-2026 data (incl. 2022)? Decision #5, item 2 of lane/market-data.

For each risk level, build the RISKIEST portfolio its rules allow with broad ETFs only: defensive share at
min_defensive, crypto at max_crypto, the rest in equity ETFs. Two defensive baskets (equal-weight, short-term heavy)
× two equity baskets (broad, tech-tilted). Compare max drawdown (G7, hard limit) and volatility (G8, warning) to the
level's limits. If the riskiest allowed mix stays inside the drawdown limit, the limit and min_defensive agree.

    PYTHONPATH=src python experiments/data/threshold_check.py          # print only
    PYTHONPATH=src python experiments/data/threshold_check.py --log    # also log_run to results.csv (commit first)
"""

from __future__ import annotations

import sys

import pandas as pd

from dh import data, log_run
from dh.agents import market
from dh.agents.rules import RISK_LEVELS

DEFENSIVE = {"equal": {"ZST.TO": .25, "XBB.TO": .25, "AGG": .25, "GLD": .25},
             "short": {"ZST.TO": .60, "XBB.TO": .20, "GLD": .20}}
EQUITY = {"broad": {"XIU.TO": .4, "SPY": .4, "QQQ": .2},
          "tech": {"XIU.TO": .3, "SPY": .2, "QQQ": .5}}


def riskiest_allowed(level: int, defensive: dict, equity: dict) -> dict[str, float]:
    c = RISK_LEVELS[level]
    w = {t: c["min_defensive"] * v for t, v in defensive.items()}
    if c["max_crypto"]:
        w.update({"BTC-USD": c["max_crypto"] / 2, "ETH-USD": c["max_crypto"] / 2})
    rest = 1 - c["min_defensive"] - c["max_crypto"]
    w.update({t: w.get(t, 0) + rest * v for t, v in equity.items()})
    return w


def run() -> pd.DataFrame:
    rets = data.returns()
    rows = []
    for level, c in RISK_LEVELS.items():
        for dn, dv in DEFENSIVE.items():
            for en, ev in EQUITY.items():
                s = market.strategy_stats(riskiest_allowed(level, dv, ev), rets=rets)
                rows.append(dict(level=level, name=c["name"], defensive=dn, equity=en,
                                 max_drawdown=s["max_drawdown"], dd_limit=-c["max_drawdown"],
                                 dd_ok=-s["max_drawdown"] <= c["max_drawdown"] + 1e-9,
                                 ann_vol=s["ann_vol"], vol_target=c["target_vol"],
                                 vol_ok=s["ann_vol"] <= c["target_vol"] + 1e-9,
                                 return_2022=s["return_2022"], ann_return=s["ann_return"]))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = run()
    print(df.round(3).to_string(index=False))
    print(f"\nG7 drawdown limit holds in {df.dd_ok.mean():.0%} of cases; G8 vol target in {df.vol_ok.mean():.0%}.")
    if "--log" in sys.argv:
        note = "riskiest mix allowed by rules.py, broad ETFs, 4 baskets per level, experiments/data/threshold_check.py"
        log_run(df.dd_ok.mean(), "threshold-check", "dd_limit_pass_rate", notes=note)
        log_run(df.vol_ok.mean(), "threshold-check", "vol_target_pass_rate", notes=note)
        for level, g in df.groupby("level"):
            log_run(g.max_drawdown.min(), "threshold-check", f"L{level}_worst_max_drawdown", notes=note)
            log_run(g.ann_vol.max(), "threshold-check", f"L{level}_worst_ann_vol", notes=note)
        print("logged to results.csv")
