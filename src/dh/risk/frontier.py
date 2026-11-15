"""(E) A frontier is drawn in the measure it was optimised in, and its points are checked for dominance.

Root cause (audit A5): `market_charts.risk_return_data` optimises on the ARITHMETIC mean (rets.mean() × ppy, the only
measure linear in the weights, Markowitz 1952) and then plots each point's CAGR (GEOMETRIC ≈ μ − σ²/2). For risky
points the drag σ²/2 grows faster than μ, so the plotted curve bends back: on synthetic data the CAGR rises to 29.1%
then falls to 27.6% while volatility keeps rising. Dominated points are drawn as "efficient".

Method here: the frontier, the assets and the strategies on one chart use ONE measure (`ReturnMeasure`), stated in
the result. Two exact options:
- ARITHMETIC: Markowitz frontier (qt.efficient_frontier), everything plotted as arithmetic mean. Exact.
- GEOMETRIC: the Pareto envelope (non-dominated set) of CAGR vs volatility over a candidate set of portfolios. It is
  "efficient" only within the candidates, and said so.
In every case `check` flags dominated points, backtracking, and a mix of measures. The frontier stays a picture of
the data window (hindsight, survivors): decision #1, unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import metrics
from .. import quant_toolkit as qt
from .contracts import Issue, ReturnMeasure


def measure_of(port: pd.Series, measure: ReturnMeasure) -> float:
    """Annual return of a daily series in the requested measure."""
    r = port.dropna()
    ppy = metrics.periods_per_year(r)
    if measure is ReturnMeasure.ARITHMETIC:
        return float(r.mean() * ppy)
    if measure is ReturnMeasure.GEOMETRIC:
        return metrics.ann_return(r)
    return float(np.log1p(r).mean() * ppy)


@dataclass
class Frontier:
    measure: ReturnMeasure
    points: pd.DataFrame                  # columns: ret, vol, + one weight column per asset
    method: str
    issues: list[Issue] = field(default_factory=list)


def frontier(rets: pd.DataFrame, measure: ReturnMeasure = ReturnMeasure.ARITHMETIC, n_points: int = 20) -> Frontier:
    """Frontier in one measure. ARITHMETIC: Markowitz. GEOMETRIC: Pareto envelope of the Markowitz candidates
    (re-measured in CAGR); LOG is treated like GEOMETRIC (same ordering on one window)."""
    r = rets.dropna()
    if r.shape[1] < 2 or len(r) < 60:
        raise ValueError("need ≥ 2 assets and ≥ 60 common days")
    ppy = metrics.periods_per_year(r)
    try:
        ef = qt.efficient_frontier(r.mean() * ppy, r.cov() * ppy, n_points=n_points)["frontiere"]
    except (RuntimeError, ValueError) as e:   # SLSQP can stop at its iteration limit near the top point
        return Frontier(measure, pd.DataFrame(columns=["ret", "vol"]), "markowitz (failed)",
                        [Issue("E-solver", "block", "technical", f"optimiser failed: {e}")])
    rows = []
    for _, row in ef.iterrows():
        w = {t: float(row[t]) for t in r.columns if row[t] > 1e-6}
        port = metrics.portfolio_returns(r[list(w)], w)
        rows.append({"ret": measure_of(port, measure), "vol": metrics.ann_vol(port), **{t: float(row[t]) for t in r.columns}})
    pts = pd.DataFrame(rows)
    method = "markowitz (arithmetic mean)"
    if measure is not ReturnMeasure.ARITHMETIC:
        pts = pts[~dominated(pts)].reset_index(drop=True)
        method = "pareto envelope of markowitz candidates, re-measured"
    return Frontier(measure, pts, method, check(pts, measure, measure))


def dominated(points: pd.DataFrame, tol: float = 1e-6) -> pd.Series:
    """True where another point has ≤ vol and ≥ ret, one of them strictly (Pareto)."""
    v, m = points["vol"].to_numpy(), points["ret"].to_numpy()
    out = [bool(np.any((v <= v[i] + tol) & (m >= m[i] - tol) & ((v < v[i] - tol) | (m > m[i] + tol))))
           for i in range(len(points))]
    return pd.Series(out, index=points.index)


def check(points: pd.DataFrame, frontier_measure: ReturnMeasure, overlay_measure: ReturnMeasure) -> list[Issue]:
    """Issues: dominated points, backtracking (return falls while volatility rises), mixed measures."""
    out = []
    if frontier_measure != overlay_measure:
        out.append(Issue("E-measures", "block", "interpretation", "frontier and plotted points use different return "
                         "measures", {"frontier": frontier_measure.value, "overlay": overlay_measure.value}))
    p = points.sort_values("vol")
    d = dominated(p)
    if d.any():
        out.append(Issue("E-dominated", "block", "method", f"{int(d.sum())} frontier point(s) are dominated",
                         {"vol": p.loc[d, "vol"].round(4).tolist()}))
    back = np.diff(p["ret"].to_numpy()) < -1e-6
    if back.any():
        out.append(Issue("E-backtrack", "block", "method", "the frontier bends back (return falls as volatility rises)"))
    return out


def drag_gap(mu_arith: float, vol: float, cagr: float) -> float:
    """Observed CAGR minus the approximation μ − σ²/2: near 0 when the two measures are consistent; a large gap
    signals fat tails or a short window (the approximation is exact only for log-normal returns)."""
    return cagr - (np.expm1(np.log1p(mu_arith) - vol ** 2 / 2) if mu_arith > -1 else np.nan)
