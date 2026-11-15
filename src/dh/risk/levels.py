"""(C) Risk levels that are really ordered by risk, or a reported contradiction.

Root cause (audit A3, results.csv): `portfolio.levels` builds level k with 10·(k−1) points less growth AND, when the
client has several flavours, with ANOTHER flavour (`order[i]`), so another defensive basket. Two things change at
once, and only the growth share is used as the label. Robert: "more prudent" (income, 5% growth) has a worst drop of
−9.5% and prob_loss 5.7% vs −8.6% / 3.9% for the level above; Mateo's "most prudent" (−11.6%) is riskier than his
"more prudent" (−9.6%). Aggregate bonds fell with stocks in 2022: a growth share is not a risk measure.

Method here: each strategy gets a RiskVector (several distinct risks, each with its own definition, direction and
source — never merged into one number). Strategy A is "safer" than B only if A is no riskier on every PRIMARY
dimension (Pareto order, with a tolerance); otherwise the pair is "mixed" and the contradiction is reported.
`check_labels` blocks any "more prudent" label contradicted by a primary dimension.
Which dimensions are primary is a decision (R5); the default below is a proposal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import pairwise

from ..agents.rules import BOND_ETFS, DEFENSIVE
from .contracts import Issue

# name: (definition, source in today's strategy dict, higher_is_riskier)
DIMENSIONS = {
    "ann_vol": ("annualised volatility of daily returns", "stats.ann_vol", True),
    "max_drawdown": ("worst peak-to-trough on the data window, OBSERVED (positive fraction)", "stats.max_drawdown", True),
    "prob_loss": ("P(final < total invested) at the horizon, zero-premium view, SIMULATED", "outlook.risk_only.prob_loss", True),
    "tail": ("CVaR 95%: average loss on the worst 5% of days", "stats.cvar_95", True),
    "worst_12m": ("worst 12 rolling months, OBSERVED (positive fraction)", "stats.worst_12m", True),
    "permanent_loss": ("5% worst final value vs invested at the horizon (positive = loss), SIMULATED",
                       "outlook.risk_only.final_p5", True),
    "liquidity_gap": ("money needed within 3 years not covered by defensive assets", "limits.liquidity_floor", True),
    "concentration": ("1 / effective number of holdings through ETFs (C5)", "checks C5", True),
    "rate_risk": ("share in bond ETFs (aggregate/long), not ultra-short; PROVISIONAL proxy until durations are sourced",
                  "weights", True),
}
PRIMARY = ("max_drawdown", "prob_loss")      # decision R5: worst drop and chance of loss order the levels


@dataclass
class RiskVector:
    ann_vol: float | None = None
    max_drawdown: float | None = None
    prob_loss: float | None = None
    tail: float | None = None
    worst_12m: float | None = None
    permanent_loss: float | None = None
    liquidity_gap: float | None = None
    concentration: float | None = None
    rate_risk: float | None = None


def risk_vector(strategy: dict, limits: dict | None = None, capital: float | None = None) -> RiskVector:
    """Read (never recompute) the numbers a strategy already carries. Missing ones stay None and are reported by
    `compare`; positive fractions everywhere so 'higher = riskier' holds for every dimension."""
    st, out, w = strategy.get("stats") or {}, strategy.get("outlook") or {}, strategy.get("weights") or {}
    ro = out.get("risk_only") or {}
    neg = lambda x: None if x is None else max(0.0, -float(x))
    c5 = next((c for c in strategy.get("checks") or [] if c.get("check") == "C5"), None)
    inv = out.get("total_invested") or capital
    defensive = sum(v for t, v in w.items() if t in DEFENSIVE)
    return RiskVector(
        ann_vol=st.get("ann_vol"), max_drawdown=neg(st.get("max_drawdown")),
        prob_loss=ro.get("prob_loss"), tail=st.get("cvar_95"), worst_12m=neg(st.get("worst_12m")),
        permanent_loss=(max(0.0, 1 - ro["final_p5"] / inv) if ro.get("final_p5") and inv else None),
        liquidity_gap=(max(0.0, (limits or {}).get("liquidity_floor", 0.0) - defensive) if limits else None),
        concentration=(1 / c5["value"] if c5 and c5.get("value") else None),
        rate_risk=sum(v for t, v in w.items() if t in BOND_ETFS and t != "ZST.TO"))


def compare(a: RiskVector, b: RiskVector, dims=PRIMARY, tol: float = 0.002) -> dict:
    """'safer' | 'riskier' | 'equal' | 'mixed' | 'unknown' (A vs B) with the per-dimension verdicts.
    tol: differences smaller than this (absolute) count as equal (rounding of shown numbers)."""
    per = {}
    for d in dims:
        x, y = getattr(a, d), getattr(b, d)
        per[d] = None if x is None or y is None else ("equal" if abs(x - y) <= tol else "lower" if x < y else "higher")
    known = [v for v in per.values() if v is not None]
    if not known:
        verdict = "unknown"
    elif all(v == "equal" for v in known):
        verdict = "equal"
    elif all(v in ("lower", "equal") for v in known):
        verdict = "safer"
    elif all(v in ("higher", "equal") for v in known):
        verdict = "riskier"
    else:
        verdict = "mixed"
    return {"verdict": verdict, "per_dimension": per, "missing": [d for d, v in per.items() if v is None]}


def check_labels(ladder: list[tuple[str, RiskVector]], dims=PRIMARY, tol: float = 0.002) -> list[Issue]:
    """ladder = [(label, vector)] from the boldest to the most prudent, as shown to the client. Each step must be
    'safer' or 'equal'; 'riskier' blocks (the label lies), 'mixed' is disclosed (no honest single order)."""
    out = []
    for (la, va), (lb, vb) in pairwise(ladder):
        c = compare(vb, va, dims, tol)
        if c["verdict"] == "riskier":
            out.append(Issue("C-inverted", "block", "interpretation",
                             f"'{lb}' is presented as more prudent than '{la}' but is riskier", {**c, "pair": (la, lb)}))
        elif c["verdict"] == "mixed":
            out.append(Issue("C-mixed", "disclose", "interpretation",
                             f"'{lb}' vs '{la}': the risk measures disagree", {**c, "pair": (la, lb)}))
        elif c["verdict"] == "unknown" or c["missing"]:
            out.append(Issue("C-missing", "disclose", "technical", f"'{lb}' vs '{la}': risk measures missing",
                             {**c, "pair": (la, lb)}))
    return out


def order(named: dict[str, RiskVector], dims=PRIMARY, tol: float = 0.002) -> dict:
    """Pareto layers from the safest: {'layers': [[names]...], 'contradictions': [(a, b, per_dimension)]}.
    Strategies in the same layer cannot be ranked honestly; the caller shows them as alternatives, not as levels."""
    names, layers, left = list(named), [], set(named)
    while left:
        layer = [n for n in left if not any(compare(named[m], named[n], dims, tol)["verdict"] == "safer"
                                            for m in left if m != n)]
        layers.append(sorted(layer))
        left -= set(layer)
    contra = [(a, b, compare(named[a], named[b], dims, tol)["per_dimension"]) for i, a in enumerate(names)
              for b in names[i + 1:] if compare(named[a], named[b], dims, tol)["verdict"] == "mixed"]
    return {"layers": layers, "contradictions": contra}


def as_dict(v: RiskVector) -> dict:
    return {k: x for k, x in asdict(v).items()}
