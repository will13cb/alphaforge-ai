"""(B) Is the client's goal reachable, under which return assumption, and with how much in growth assets?

Root cause (audit A2): `portfolio.split_search` looks for the smallest growth share with P(target) ≥ 50% in the
`risk_only` view, where every portfolio earns cash on average. With no equity premium, more stocks only add
variance: the median falls (≈ μ − σ²/2) and P(target) for a target above the cash path never reaches 50%. The floor
is then 0% or "impossible", and the client is told the goal "needs more than 100% in growth assets", which the model
itself contradicts. The view is right for RISK, wrong for a REQUIRED-RETURN question.

Method here: one simulation engine (stationary bootstrap, reused), several NAMED assumptions, and a status:
    ZERO_PREMIUM  growth part earns cash: "can the goal be met without counting on stocks?"
    CENTRAL       growth part earns cash + a moderate premium (value to approve, decision R3)
    FAVOURABLE    the data window's own average repeats (today's `replay`; 2021-2026 was strong)
    STRESS        historical stress windows / hypothetical shocks: reported, never used to size the goal
The minimum share is searched ONLY under an assumption with a positive premium, and only up to the client's
ceiling. Used by portfolio.split_search (goal_assessment). Statuses (GoalStatus) replace the "more than 100%" message.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

from .. import metrics
from .. import quant_toolkit as qt
from .contracts import Assumption, Issue

ZERO_PREMIUM = Assumption("zero_premium", 0.0, "growth assets earn what cash earned, same swings as in the data")
FAVOURABLE = Assumption("favourable", None, "the data window's own average return repeats (hindsight, strong period)",
                        source="data window")


def central() -> Assumption:
    """Decision R3: growth part earns cash + rules.CENTRAL_PREMIUM a year (read at call time, so tests can patch it)."""
    from ..agents.rules import CENTRAL_PREMIUM
    return Assumption("central", CENTRAL_PREMIUM, f"growth assets earn cash + {CENTRAL_PREMIUM:.0%} a year, same swings "
                      "as in the data", source="rules.CENTRAL_PREMIUM (decision R3, order of magnitude of the long-run "
                      "equity premium over bills, Dimson-Marsh-Staunton)")


class GoalStatus(str, Enum):
    NO_TARGET = "no_target"
    WITHOUT_EQUITY = "reachable_without_equity"          # zero premium, 0% growth, P ≥ p_min
    NEEDS_EQUITY = "needs_equity"                        # central: smallest share ≤ ceiling with P ≥ p_min
    ONLY_FAVOURABLE = "only_under_favourable"            # central fails within the ceiling, favourable succeeds
    LOW_PROBABILITY = "insufficient_probability"         # best P within the ceiling in [p_low, p_min) under central
    IMPOSSIBLE = "impossible_within_limits"              # even favourable at the ceiling < p_low


@dataclass
class GoalAssessment:
    status: GoalStatus
    min_share: float | None                  # only for WITHOUT_EQUITY (0.0) and NEEDS_EQUITY; never > ceiling
    curves: dict[str, list[dict]]            # assumption name → [{share, prob, p50}]
    ceiling: float
    p_min: float
    issues: list[Issue] = field(default_factory=list)


def recentre(r: pd.Series, cash_daily: float | None, a: Assumption, growth_share: float) -> pd.Series:
    """Same daily swings, mean replaced by cash + growth_share × premium (per day). premium None → unchanged.
    The premium applies to the growth part only: a 100% defensive portfolio earns cash under every assumption."""
    if a.equity_premium is None:
        return r
    if cash_daily is None:
        raise ValueError("cash_daily needed to recentre on an assumption")
    ppy = metrics.periods_per_year(r)
    return r - r.mean() + cash_daily + growth_share * a.equity_premium / ppy


def probability_curve(port_of: Callable[[float], pd.Series], grid: list[float], a: Assumption, cash_daily: float,
                      capital: float, horizon_years: float, target: float, monthly_contribution: float = 0.0,
                      n_scenarios: int = 2000, seed: int = 0,
                      growth_of: Callable[[float], float] | None = None) -> list[dict]:
    """P(final ≥ target) and median final value per growth share, under one assumption. Same seed for every share
    (common random numbers), so differences between shares are not sampling noise."""
    if capital <= 0 and monthly_contribution <= 0:
        raise ValueError("no capital and no contribution")
    if target <= 0 or horizon_years <= 0:
        raise ValueError("target and horizon must be > 0")
    out = []
    for s in grid:
        r = recentre(port_of(s).dropna(), cash_daily, a, growth_of(s) if growth_of else s)
        ppy = metrics.periods_per_year(r)
        n = max(1, round(horizon_years * ppy))
        paths = qt.bootstrap_paths(r, n_periods=n, n_scenarios=n_scenarios, seed=seed)
        g = qt.goal_probability(paths, initial=capital, target=target, contribution=monthly_contribution,
                                contribution_every=max(1, round(ppy / 12)))
        out.append({"share": s, "prob": g["probabilite_atteinte"], "p50": g["richesse_finale_quantiles"]["p50"]})
    return out


def min_share(curve: list[dict], a: Assumption, p_min: float, ceiling: float) -> float | None:
    """Smallest share ≤ ceiling with prob ≥ p_min. Refuses to search under a zero (or negative) premium beyond 0%:
    there, a higher share can only win by adding variance, which is not a reason to hold stocks."""
    pts = [c for c in curve if c["share"] <= ceiling + 1e-9]
    if a.equity_premium is not None and a.equity_premium <= 0:
        pts = [c for c in pts if c["share"] <= 1e-9]
    return next((c["share"] for c in sorted(pts, key=lambda c: c["share"]) if c["prob"] >= p_min), None)


def classify(curves: dict[str, list[dict]], assumptions: dict[str, Assumption], ceiling: float, p_min: float,
             p_low: float, central: str = "central") -> GoalAssessment:
    """Status from the curves (computed by `probability_curve`, one per assumption). p_min / p_low: decision R4."""
    if not 0 < p_low < p_min < 1:
        raise ValueError("need 0 < p_low < p_min < 1")
    within = lambda name: [c for c in curves[name] if c["share"] <= ceiling + 1e-9]
    best = lambda name: max((c["prob"] for c in within(name)), default=0.0)
    zp = next((c for c in curves.get(ZERO_PREMIUM.name, []) if c["share"] <= 1e-9), None)
    if zp and zp["prob"] >= p_min:
        return GoalAssessment(GoalStatus.WITHOUT_EQUITY, 0.0, curves, ceiling, p_min)
    s = min_share(curves[central], assumptions[central], p_min, ceiling)
    if s is not None:
        return GoalAssessment(GoalStatus.NEEDS_EQUITY, s, curves, ceiling, p_min)
    if FAVOURABLE.name in curves and best(FAVOURABLE.name) >= p_min:
        return GoalAssessment(GoalStatus.ONLY_FAVOURABLE, None, curves, ceiling, p_min)
    if best(central) >= p_low:
        return GoalAssessment(GoalStatus.LOW_PROBABILITY, None, curves, ceiling, p_min)
    return GoalAssessment(GoalStatus.IMPOSSIBLE, None, curves, ceiling, p_min)


def explanation_facts(g: GoalAssessment) -> dict:
    """Facts for the Explainer (it writes the sentence; numbers stay traceable, G12). Options are listed for the
    statuses where the goal does not fit; the client is never told to exceed 100% or their ceiling."""
    best = {k: max((c["prob"] for c in v if c["share"] <= g.ceiling + 1e-9), default=None) for k, v in g.curves.items()}
    options = [] if g.status in (GoalStatus.WITHOUT_EQUITY, GoalStatus.NEEDS_EQUITY, GoalStatus.NO_TARGET) else [
        "a longer horizon", "a lower target", "larger contributions", "accepting a larger loss (your choice, not ours)"]
    return {"status": g.status.value, "min_share": g.min_share, "ceiling": g.ceiling, "p_min": g.p_min,
            "best_probability_by_assumption": best, "options": options}


def is_monotone_where_expected(curve: list[dict], a: Assumption, tol: float = 0.02) -> bool:
    """Sanity property: with a positive premium, the median final value should not fall as the share rises by more
    than `tol` (relative) — if it does, volatility drag dominates and the premium is too small to justify stocks."""
    if a.equity_premium is None or a.equity_premium <= 0:
        return True
    p50 = np.array([c["p50"] for c in sorted(curve, key=lambda c: c["share"])])
    return bool(np.all(np.diff(p50) >= -tol * p50[:-1]))
