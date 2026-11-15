"""(A) Equity ceiling from the distribution of FUTURE losses, not from one past drawdown.

Root cause (audit A1): `portfolio.split_search` kept the largest growth share whose drawdown over 2021-2026 is
≤ the loss limit. That drawdown is one realisation; picking the share at the edge of the constraint selects the
windows where luck was good (winner's curse), and the same number was then shown as proof (G7). The drawdown also
depends on the length of the period: over a 15-year horizon the expected drawdown is deeper than over 5 years.
On a model with known parameters the limit was exceeded in 39-71% of futures (tests/test_risk_loss_model.py).

Methods (each a `LossModel`, so they can be compared on the same inputs):
- HistoricalWindow          what happened on the data window (Evidence.OBSERVED): shown, never a guarantee.
- StationaryBootstrapLoss   Politis & Romano (1994) block bootstrap of the portfolio's daily returns over the
                            client's horizon → distribution of MDD_HORIZON (Evidence.SIMULATED). Its mean can be
                            recentred on a named Assumption (central: cash + growth share × premium, decision R1/R3).
                            One index matrix per (series length, horizon) is reused for every share (common random
                            numbers): the curve over shares is smooth and cheap, differences are not sampling noise.
Decision rule (R1): ceiling = the last share, scanning up from 0%, before the first share with
P(MDD over the horizon > loss limit) > alpha. Uncertainty (R2): the same rule on 3-year sub-windows gives a range.
Measured on known-parameter markets (doc): the realised breach rate falls from 39-71% to 15-24% for alpha = 10%,
still above alpha: 5 years cannot pin down a tail. Hence the horizon rule stays and the range is shown.
Limits (to state in texts): the bootstrap only reuses past days (no new kind of crisis); 5 years hold one bear
market; daily rebalancing; nominal values.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import numpy as np
import pandas as pd

from .. import metrics
from .. import quant_toolkit as qt
from .contracts import Assumption, Evidence, Issue, LossMeasure


@dataclass
class LossDistribution:
    """Drawdowns (≤ 0) of one portfolio, one per scenario (one value for an observed window)."""
    samples: np.ndarray
    measure: LossMeasure
    evidence: Evidence
    method: str
    horizon_years: float | None

    def exceedance(self, limit: float) -> float:
        """P(loss deeper than `limit`), limit as a positive fraction (0.15 = 15%)."""
        if not 0 < limit < 1:
            raise ValueError("limit must be in (0, 1)")
        return float(np.mean(-self.samples > limit + 1e-12))

    def quantile(self, q: float) -> float:
        """Loss quantile as a negative number (q=0.05 → the 5% worst drawdown)."""
        return float(np.quantile(self.samples, q))


class LossModel(Protocol):
    name: str

    def distribution(self, port: pd.Series, horizon_years: float,
                     growth_share: float | None = None) -> LossDistribution: ...


def drawdowns(paths: np.ndarray) -> np.ndarray:
    """Max drawdown of each row of a (scenarios × periods) matrix of simple returns; the starting value 1 counts as a
    peak, so a loss on day 1 is counted (same convention as metrics.max_drawdown since A10). In place on one buffer:
    this is the hot loop of the ceiling scan."""
    eq = np.cumprod(1 + paths, axis=1)
    peak = np.maximum(eq, 1.0)
    np.maximum.accumulate(peak, axis=1, out=peak)
    np.divide(eq, peak, out=eq)
    return np.minimum(eq.min(axis=1) - 1, 0.0).astype(float)


@lru_cache(maxsize=6)
def _indices(n_obs: int, n_periods: int, n_scenarios: int, block: float, seed: int) -> np.ndarray:
    """Stationary-bootstrap indices, cached: every model with the same sizes and seed draws the SAME paths (common
    random numbers across shares, strategies and sub-windows of equal length), and they are drawn once."""
    idx = qt._stationary_indices(n_obs, n_periods, n_scenarios, block, np.random.default_rng(seed))
    idx.setflags(write=False)
    return idx


@dataclass
class HistoricalWindow:
    """The one drawdown observed on the data window. The horizon is ignored (that is its limit)."""
    name: str = "historical_window"

    def distribution(self, port: pd.Series, horizon_years: float, growth_share: float | None = None) -> LossDistribution:
        r = _clean(port)
        return LossDistribution(drawdowns(r.to_numpy()[None, :]), LossMeasure.MDD_WINDOW, Evidence.OBSERVED,
                                self.name, None)


@dataclass
class StationaryBootstrapLoss:
    """Block bootstrap of the portfolio over the horizon. `assumption` recentres the mean (None = keep the window's own
    mean); then `cash_daily` is needed and `growth_share` is passed per call (the premium applies to growth only)."""
    n_scenarios: int = 1000
    block_mean: float | None = None
    seed: int = 0
    assumption: Assumption | None = None
    cash_daily: float | None = None
    name: str = "stationary_bootstrap"

    def indices(self, n_obs: int, n_periods: int) -> np.ndarray:
        """(scenarios × periods) indices into a series of n_obs days; the same for every call with the same sizes."""
        if n_periods * self.n_scenarios > 50_000_000:
            raise ValueError("horizon × scenarios too large")
        b = n_obs ** (1 / 3) if self.block_mean is None else self.block_mean
        return _indices(n_obs, n_periods, self.n_scenarios, float(b), self.seed)

    def distribution(self, port: pd.Series, horizon_years: float, growth_share: float | None = None) -> LossDistribution:
        if horizon_years <= 0:
            raise ValueError("horizon_years must be > 0")
        r = _clean(port)
        if self.assumption is not None:
            from .goals import recentre
            if growth_share is None:
                raise ValueError("growth_share needed to recentre on an assumption")
            r = recentre(r, self.cash_daily, self.assumption, growth_share)
        n = max(1, round(horizon_years * metrics.periods_per_year(r)))
        x = r.to_numpy()
        if (x <= -1).any():
            raise ValueError("a recentred return ≤ -100%")
        paths = x.astype(np.float32)[self.indices(len(x), n)]   # float32: drawdowns to ~1e-6, half the memory traffic
        return LossDistribution(drawdowns(paths), LossMeasure.MDD_HORIZON, Evidence.SIMULATED, self.name, horizon_years)


@dataclass
class CeilingDecision:
    share: float | None                  # ≤ max_share; None: even 0% breaks the rule (say so, never force it)
    loss_only: float | None              # what the loss test alone would allow (ignoring max_share)
    alpha: float
    limit: float
    method: str
    table: list[dict]                    # per share scanned: exceedance, p5 drawdown, observed drawdown
    issues: list[Issue] = field(default_factory=list)


def equity_ceiling(port_of: Callable[[float], pd.Series], grid: list[float], limit: float, horizon_years: float,
                   alpha: float, model: LossModel, max_share: float = 1.0,
                   growth_of: Callable[[float], float] | None = None) -> CeilingDecision:
    """Scan the grid upward; the ceiling is the last share before the first one with P(loss over the horizon > limit)
    > alpha (the exceedance rises with the share; stopping at the first breach avoids picking a lucky share above a
    breach). The scan continues past max_share only to report `loss_only`. port_of(s) = the portfolio's daily
    returns at growth share s (built by the Portfolio); growth_of(s) = its real growth share (default s)."""
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1): it is a policy choice (decision R1), no default")
    if not 0 < limit < 1:
        raise ValueError("limit must be in (0, 1)")
    growth_of = growth_of or (lambda s: s)
    table, last_ok = [], None
    for s in sorted(grid):
        port = port_of(s)
        d = model.distribution(port, horizon_years, growth_share=growth_of(s))
        p = d.exceedance(limit)
        table.append({"share": s, "exceedance": p, "p5_drawdown": d.quantile(0.05), "alpha_drawdown": d.quantile(alpha),
                      "observed_drawdown": metrics.max_drawdown(port)})
        if p > alpha:
            break
        last_ok = s
    share = None if last_ok is None else max((x for x in sorted(grid) if x <= min(last_ok, max_share) + 1e-9),
                                             default=None)
    issues = [] if share is not None else [Issue(
        "A-none", "block", "method", "even the smallest share breaks the loss limit with more than the allowed "
        "probability", {"limit": limit, "alpha": alpha})]
    return CeilingDecision(share, last_ok, alpha, limit, model.name, table, issues)


def window_ceilings(port_of: Callable[[float], pd.Series], grid: list[float], limit: float, horizon_years: float,
                    alpha: float, model_factory: Callable[[], LossModel], years: float, step_years: float,
                    max_share: float = 1.0, growth_of: Callable[[float], float] | None = None) -> dict:
    """The same ceiling rule on sub-windows of `years`, one every `step_years` (R2). Returns {"by_window": {(start,
    end): share}, "range": (min, max) | None, "issues"}: 'disclose' when the range spans more than 2 grid steps (the
    split then depends on the window more than on the client)."""
    # Windows start once EVERY share scanned has data: a portfolio's returns begin when all its assets have a price
    # (metrics.portfolio_returns), so with a long history a share holding a young asset (ETH 2017, SHOP.TO 2015)
    # starts later than the 0% one. A window before that would hold no days for it (decision #47).
    series = [port_of(s).dropna() for s in sorted({0.0, *grid})]
    series = [x for x in series if len(x)]
    if not series:
        return {"by_window": {}, "range": None, "issues": []}
    start, end = max(x.index[0] for x in series), min(x.index[-1] for x in series)
    out = {}
    a = start
    while a + pd.DateOffset(years=years) <= end + pd.Timedelta(days=10):   # a few days short still counts
        b = a + pd.DateOffset(years=years)
        m = model_factory()
        dec = equity_ceiling(lambda s, a=a, b=b: port_of(s).loc[a:b], grid, limit, horizon_years, alpha, m,
                             max_share, growth_of)
        out[(a.date().isoformat(), b.date().isoformat())] = dec.share
        a = a + pd.DateOffset(years=step_years)
    vals = [v for v in out.values() if v is not None]
    rng = (min(vals), max(vals)) if vals else None
    g = sorted(grid)
    step = min(np.diff(g)) if len(g) > 1 else 0.0
    issues = [Issue("A-unstable", "disclose", "method", "the ceiling depends on the data window", {"range": rng})] \
        if rng and rng[1] - rng[0] > 2 * step + 1e-9 else []
    return {"by_window": out, "range": rng, "issues": issues}


def walk_forward(port_of_split: Callable[[str], Callable[[float], pd.Series]], **ceiling_kw) -> dict:
    """Out-of-sample check: ceiling chosen on the 'in' part, drawdown realised on the 'out' part at that share.
    With 5 years of data this is ONE test, reported as such. port_of_split('in'|'out') → port_of(share)."""
    dec = equity_ceiling(port_of_split("in"), **ceiling_kw)
    if dec.share is None:
        return {"in_sample": dec, "out_of_sample_drawdown": None, "breached": None}
    dd = metrics.max_drawdown(port_of_split("out")(dec.share))
    return {"in_sample": dec, "out_of_sample_drawdown": dd, "breached": abs(dd) > dec.limit}


def _clean(port: pd.Series) -> pd.Series:
    r = pd.Series(port).dropna()
    if len(r) < 20:
        raise ValueError(f"{len(r)} observations: too short for a loss distribution (≥ 20)")
    if (r <= -1).any():
        raise ValueError("a return ≤ -100%")
    return r
