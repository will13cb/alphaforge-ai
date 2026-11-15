"""(G) Every control has one job, and an "independent" check never repeats the rule that built the portfolio.

Root cause (audit A7): one inequality, |MDD_WINDOW| ≤ loss limit, is used to BUILD the split (split_search) and then
checked again as D1 (vs tolerance, implied by D2 since loss_limit ≤ tolerance), D2, G7 and G17 (D2 in dollars:
identical up to the capital). For a strategy the Portfolio built, G7 can only fail in the "even 0% growth exceeds"
case: the pass rate is guaranteed by construction, and "17 checks" counts one fact up to five times.

Method here: a registry of ControlSpec. Each control declares its kind, the question it answers, its inputs as
(quantity, measure, method) and its criterion. `audit` finds duplicates (same inputs and criterion) and circular
checks (an INDEPENDENT control equal to a CONSTRUCTION constraint). CURRENT describes today's rules as they are;
TARGET is the set implemented in phase 2 (decision R8). The registry is documentation the code can test, not a new
agent; tests/test_risk_controls.py checks that the Guardian's rules match it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import Issue


class Kind(str, Enum):
    CONSTRUCTION = "construction"      # a constraint the Portfolio uses to build (not a check)
    INDEPENDENT = "independent"        # verifies the result with another measure, method or data
    DATA_QUALITY = "data_quality"
    CONSISTENCY = "consistency"        # results agree with each other (stamps, orderings, measures)
    GOVERNANCE = "governance"          # safety: disclaimer, traced numbers, refused requests, KYC complete


@dataclass(frozen=True)
class ControlSpec:
    id: str
    kind: Kind
    question: str
    inputs: tuple[tuple[str, str, str], ...]     # (quantity, measure, method)
    criterion: str                                # e.g. "<= loss_limit"
    blocks: bool
    owner: str                                    # module that runs it


MDD_HIST = ("drawdown", "mdd_window", "historical_window")

CURRENT = (
    ControlSpec("split_search", Kind.CONSTRUCTION, "largest growth share", (MDD_HIST,), "<= loss_limit", True,
                "portfolio.split_search"),
    ControlSpec("D1", Kind.INDEPENDENT, "worst drop vs tolerance", (MDD_HIST,), "<= tolerance", True, "checks.d1_tolerance"),
    ControlSpec("D2", Kind.INDEPENDENT, "worst drop vs loss limit", (MDD_HIST,), "<= loss_limit", True, "checks.d2_capacity"),
    ControlSpec("G7", Kind.INDEPENDENT, "worst drop vs loss limit", (MDD_HIST,), "<= loss_limit", True, "guardian"),
    ControlSpec("G17", Kind.INDEPENDENT, "worst drop in $ vs limit in $", (MDD_HIST,), "<= loss_limit", True,
                "guardian → checks.d2_capacity"),
    ControlSpec("D3", Kind.INDEPENDENT, "worst 12 months vs loss limit", (("return", "worst_12m", "historical_window"),),
                "<= loss_limit", False, "checks.d3_stress"),
)

# The controls as implemented in phase 2 (decision R8). G7 is the Guardian's name for D2 (one function).
TARGET = (
    ControlSpec("A-ceiling", Kind.CONSTRUCTION, "largest growth share",
                (("drawdown", "mdd_horizon", "bootstrap central, grid points, seed 0"),), "P(> loss_limit) <= alpha",
                True, "portfolio.split_search → risk.loss_model.equity_ceiling"),
    ControlSpec("G7=D2", Kind.INDEPENDENT, "do the FINAL weights (after rounding, caps, fixes, Critic) pass the loss "
                "rule, in a fresh simulation", (("drawdown", "mdd_horizon", "bootstrap central, final weights, seed 1"),),
                "P(> loss_limit) <= alpha + 2 standard errors", True, "checks.d2_capacity (Guardian G7)"),
    ControlSpec("D1", Kind.INDEPENDENT, "what happened on the data window (shown, not a guarantee)", (MDD_HIST,),
                "<= 80% of loss_limit else disclose", False, "checks.d1_tolerance"),
    ControlSpec("D3", Kind.INDEPENDENT, "worst 12 months and 2022 sell-off (shown)",
                (("return", "worst_12m", "historical_window"),), "<= loss_limit else disclose", False, "checks.d3_stress"),
    ControlSpec("G18", Kind.CONSISTENCY, "every section describes the final weights", (("stamp", "-", "sync"),),
                "all stamps match", True, "risk.sync.verify (Guardian G18)"),
    ControlSpec("C-ladder", Kind.CONSISTENCY, "levels ordered by risk", (("risk_vector", "-", "levels"),),
                "no inverted step (dropped), mixed disclosed", True, "portfolio.levels → risk.levels.check_labels"),
    ControlSpec("E-frontier", Kind.CONSISTENCY, "frontier coherent", (("frontier", "-", "frontier"),),
                "no dominated point, one measure", True, "market_charts → risk.frontier.check"),
    ControlSpec("D-kyc", Kind.CONSISTENCY, "KYC answers comparable and coherent", (("kyc", "-", "kyc"),),
                "option-rank gap <= 0.3, censoring is not a contradiction", False, "kyc.consistency"),
)


def audit(registry=CURRENT) -> list[Issue]:
    """Duplicates (same inputs + criterion, two controls) and circular checks (an INDEPENDENT control identical to a
    CONSTRUCTION constraint). A dollar version of a percentage check is a duplicate (same inequality × capital)."""
    out, seen = [], {}
    build = {(c.inputs, c.criterion) for c in registry if c.kind is Kind.CONSTRUCTION}
    for c in registry:
        key = (c.inputs, c.criterion)
        if c.kind is Kind.INDEPENDENT and key in build:
            out.append(Issue("G-circular", "block", "method", f"{c.id} re-checks the rule that built the portfolio",
                             {"control": c.id}))
        if c.kind is not Kind.CONSTRUCTION and key in seen:
            out.append(Issue("G-duplicate", "disclose", "method", f"{c.id} repeats {seen[key]}",
                             {"control": c.id, "same_as": seen[key]}))
        seen.setdefault(key, c.id)
    return out


def count_independent(registry=TARGET) -> int:
    """How many genuinely different checks a deliverable may claim (after `audit` is clean)."""
    return len({(c.inputs, c.criterion) for c in registry if c.kind is not Kind.CONSTRUCTION})
