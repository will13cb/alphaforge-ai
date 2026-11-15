"""Shared vocabulary of `dh.risk`. Pure declarations: no computation, no import from the rest of the project.

Why it exists: the audit found the same word used for different quantities (a "drop in one year" compared with a
drawdown over five years; a frontier optimised on the arithmetic mean and drawn in CAGR; "prob_loss" computed on old
weights). Every result produced by `dh.risk` says WHICH measure, WHICH assumption and WHICH weights it used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReturnMeasure(str, Enum):
    """How a return is summarised. They are NOT interchangeable (E):
    ARITHMETIC  mean of simple daily returns × periods per year. Additive across assets (w'μ): the only one a
                mean-variance optimiser can use exactly.
    GEOMETRIC   compound annual growth (CAGR). What an investor lives; NOT linear in the weights (≈ μ − σ²/2).
    LOG         mean of log returns × periods per year (= ln(1 + CAGR) on the same window)."""
    ARITHMETIC = "arithmetic"
    GEOMETRIC = "geometric"
    LOG = "log"


class LossMeasure(str, Enum):
    """Which loss a number or a client answer refers to (A, D). Comparing two different ones is an error unless a
    documented conversion is applied (kyc_validation.normalise_loss_limit).
    MDD_WINDOW       peak-to-trough over the whole data window (today's `max_drawdown`): ONE observed event.
    WORST_12M        worst compounded return over any 12 rolling months of the window (`worst_12m`).
    MDD_HORIZON      peak-to-trough over the client's horizon, as a DISTRIBUTION (simulated, loss_model).
    LOSS_12M_DIST    12-month return, as a distribution (simulated).
    BELOW_INVESTED   final value below the total invested at the horizon (today's `prob_loss`)."""
    MDD_WINDOW = "mdd_window"
    WORST_12M = "worst_12m"
    MDD_HORIZON = "mdd_horizon"
    LOSS_12M_DIST = "loss_12m_dist"
    BELOW_INVESTED = "below_invested"


class Evidence(str, Enum):
    """Where a risk number comes from. OBSERVED is history; SIMULATED is a model. Neither is a guarantee (A)."""
    OBSERVED = "observed"
    SIMULATED = "simulated"
    RULE = "rule"            # a team judgment rule (e.g. the horizon rule, decision #22)


@dataclass(frozen=True)
class Assumption:
    """A named return assumption for simulations (B). `equity_premium` is the extra yearly return of the GROWTH part
    over cash; None means "replay the data window's own average" (today's `replay`).
    zero premium = today's `risk_only`: right for describing risk, unable to justify holding MORE stocks."""
    name: str
    equity_premium: float | None
    description: str
    source: str = "team assumption (to approve)"


@dataclass(frozen=True)
class Issue:
    """A finding any module can return. severity: 'block' (never shown as valid), 'disclose' (shown with the
    message), 'info'. kind tells the reader what went wrong (5. tests distinguish them):
    'technical' (bad input, missing data), 'method' (a method used outside its domain), 'interpretation' (a correct
    number presented with the wrong meaning)."""
    code: str
    severity: str
    kind: str
    message: str
    evidence: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.severity not in ("block", "disclose", "info"):
            raise ValueError(f"severity {self.severity!r}")
        if self.kind not in ("technical", "method", "interpretation"):
            raise ValueError(f"kind {self.kind!r}")
