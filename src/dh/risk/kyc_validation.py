"""(D) The KYC questions measure what the engine later compares them with.

Root causes (audit A4, A8):
1. The three bets give A = 2(m − CE)/σ² on grids with different ranges: the most cautious answer (0% guaranteed)
   gives A = 8.89, 4.80 and 9.60. A client who picks the most cautious option everywhere is flagged "the bets
   disagree (spread 4.8 > 2)" and gets A = 9.6: CENSORING is read as inconsistency. One option step also moves A by
   0.6 to 1.3, so the spread threshold (2) is about two steps on one bet and three on another.
2. `max_loss_pct` asks for "the largest drop IN ONE YEAR" (LossMeasure.WORST_12M) and is compared with the
   peak-to-trough over the whole window (MDD_WINDOW, D1/D2/G7/G17). The two are not the same quantity
   (MDD_WINDOW ≥ |WORST_12M| on the same data, and grows with the period length).

Method here: compare answers by their RANK in each bet's option list (0 = boldest, 1 = most cautious), not by raw A;
a client at a bound is "censored" (A ≥ that bound), never "inconsistent". Inconsistency = ranks further apart than
an explicit number of steps (decision R6). The loss question declares its measure; `comparable` refuses to compare
two different measures, and `normalise_loss_limit` lists the documented ways to convert (decision R7).
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import kyc
from .contracts import Issue, LossMeasure

# The measure each KYC answer refers to, as worded today (interface/core/questions.py, dh.kyc.QUESTIONS).
# Since R7 it asks for a drop "from a high point, at any time while invested" = a drawdown over the horizon.
QUESTION_MEASURE = {"max_loss_pct": LossMeasure.MDD_HORIZON}
# The measure the engine compares it with (portfolio.split_search ceiling and D2/G7, simulated over the horizon, R1).
ENGINE_MEASURE = {"max_loss_pct": LossMeasure.MDD_HORIZON}


def a_grid(bet: kyc.Bet) -> list[float]:
    """A for each option offered, in the order shown (highest guaranteed return first = boldest)."""
    return [bet.a_for(ce) for ce in bet.options]


def comparability(bets=kyc.BETS, tol: float = 0.5) -> dict:
    """Ranges and steps of A per bet; comparable when every bet spans the same A range within `tol`."""
    rows = {b.id: {"a_min": min(a_grid(b)), "a_max": max(a_grid(b)),
                   "max_step": max(abs(x - y) for x, y in zip(a_grid(b), a_grid(b)[1:]))} for b in bets}
    maxes = [r["a_max"] for r in rows.values()]
    ok = max(maxes) - min(maxes) <= tol
    issues = [] if ok else [Issue("D-ranges", "block", "method", "the bets cannot reach the same A: their answers are "
                                  "not comparable on the A scale", {"a_max": dict(zip(rows, maxes))})]
    return {"bets": rows, "comparable": ok, "issues": issues}


def rank(bet: kyc.Bet, ce: float) -> float:
    """Position of the answer in the option list: 0 = boldest option, 1 = most cautious (kyc.rank)."""
    return kyc.rank(bet, ce)


@dataclass
class Consistency:
    status: str               # 'consistent' | 'censored_cautious' | 'censored_bold' | 'inconsistent'
    ranks: dict[str, float]
    a_bounds: dict[str, tuple[float, float]]   # per bet: A interval implied by the option (open at the bounds)
    issues: list[Issue]


def consistency(answers: dict, max_rank_gap: float = kyc.MAX_RANK_GAP, bets=kyc.BETS) -> Consistency:
    """kyc.consistency (the rule lives with the questionnaire, used by kyc.score) plus the A interval behind each
    answer and Issues for the trace. Censored answers are 'info', a real gap is 'disclose' (to clarify)."""
    c = kyc.consistency(answers, max_rank_gap)
    bounds = {}
    for b in bets:
        g = a_grid(b)
        i = round(c["ranks"][b.id] * (len(g) - 1))
        lo = (g[i - 1] + g[i]) / 2 if i > 0 else 0.0
        hi = (g[i] + g[i + 1]) / 2 if i < len(g) - 1 else float("inf")
        bounds[b.id] = (lo, hi)
    issues = {"censored_cautious": [Issue("D-censored", "info", "interpretation", "most cautious option on every "
                                          "bet: A is at least the top of the scale, the answers agree")],
              "inconsistent": [Issue("D-gap", "disclose", "interpretation", "the bets point to different attitudes "
                                     "to risk: to clarify", {"rank_gap": c["gap"], "allowed": max_rank_gap})]}
    return Consistency(c["status"], c["ranks"], bounds, issues.get(c["status"], []))


def comparable(question: str, engine_measure: LossMeasure | None = None) -> list[Issue]:
    """Issue when a KYC answer is compared with a different loss measure than the one the question asked about."""
    q = QUESTION_MEASURE.get(question)
    e = engine_measure or ENGINE_MEASURE.get(question)
    if q is None or e is None or q == e:
        return []
    return [Issue("D-measure", "block", "interpretation", f"'{question}' asks about {q.value} but is compared with "
                  f"{e.value}", {"question": q.value, "engine": e.value})]


def normalise_loss_limit(limit: float, from_measure: LossMeasure, to_measure: LossMeasure, **kw) -> float:
    """Convert a loss limit between measures. NOT IMPLEMENTED: the choice is decision R7. Options documented:
    (a) reword the question to ask for a peak-to-trough drop ("from its highest point, at any time") → no conversion;
    (b) keep the wording and compare with LOSS_12M_DIST (12-month losses, simulated) → no conversion;
    (c) convert with the ratio MDD_HORIZON / worst 12-month loss estimated on the client's own portfolio by bootstrap
        (model-dependent; the ratio must be shown).
    (a) or (b) avoid a model-dependent conversion and are preferred."""
    if from_measure == to_measure:
        return limit
    raise NotImplementedError("decision R7: reword the question (a) or compare with 12-month losses (b)")
