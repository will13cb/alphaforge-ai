"""KYC questionnaire → the risk-aversion coefficient A of the mean-variance utility U = E(r) − ½·A·σ² (decision #38).

How A is scored (no table invented): each "bet" question is a 50/50 investment with a known mean m and variance σ².
The person picks the smallest GUARANTEED return they would take instead of it: their certainty equivalent CE. In the
mean-variance model the person is indifferent when U(bet) = U(sure), i.e. m − ½·A·σ² = CE, so

    A = 2 · (m − CE) / σ²

Three bets of different sizes give three estimates; A is their median. Bets of different sizes rarely give exactly
the same A (the model is an approximation), so the spread is reported.

KYC rules (Canadian practice: when answers conflict, the advisor clarifies; until then, the more cautious reading):
- the three bets disagree by more than ONE "average investor" band width (the 2–4 range → spread > 2), or
- the behaviour answer contradicts the bets: selling everything after a drop with A < 2 (bolder than average), or
  buying more with A > 4 (more cautious than average),
→ flagged, and A = the most cautious of the three bets (the largest), with the reason.
Bands (from the usual reading of A): < 2 above-average risk tolerance, 2–4 average investor, > 4 cautious.

Capacity is NOT folded into A: horizon, the largest loss the person can live with, and exclusions become constraints
of the optimizer (dh.markowitz), as the engine does (willingness ≠ capacity).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

AVERAGE_BAND = (2.0, 4.0)    # typical A of an average investor (textbook reading of U = E(r) − ½Aσ²)
SPREAD_MAX = AVERAGE_BAND[1] - AVERAGE_BAND[0]


@dataclass(frozen=True)
class Bet:
    id: str
    text: str
    up: float          # yearly return in the good case (probability 1/2)
    down: float        # yearly return in the bad case (probability 1/2)
    amount: float      # the stake in the story, to show $ amounts
    options: tuple     # certainty equivalents offered, highest first (returns)

    @property
    def mean(self) -> float:
        return (self.up + self.down) / 2

    @property
    def var(self) -> float:
        return ((self.up - self.down) / 2) ** 2

    def a_for(self, ce: float) -> float:
        """A at which this person is indifferent between the bet and `ce` for sure."""
        return max(0.0, 2 * (self.mean - ce) / self.var)

    def label(self, ce: float) -> str:
        return f"{ce:.1%} guaranteed ({self.amount * (1 + ce):,.0f} $ after one year)"


BETS = (
    Bet("bet_small", "You invest 10,000 $ for one year. With equal chances, you end the year at +25% (12,500 $) or at "
        "−5% (9,500 $). Instead, you can have a guaranteed return. What is the SMALLEST guaranteed return you would "
        "take instead of the investment?", 0.25, -0.05, 10_000,
        (0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.02, 0.0)),
    Bet("bet_large", "You invest 10,000 $ for one year. With equal chances, you end at +40% (14,000 $) or at −10% "
        "(9,000 $). What is the SMALLEST guaranteed return you would take instead?", 0.40, -0.10, 10_000,
        (0.15, 0.12, 0.10, 0.08, 0.06, 0.04, 0.02, 0.0)),
    Bet("bet_savings", "Your savings are 100,000 $. An investment ends the year, with equal chances, at 120,000 $ or "
        "at 95,000 $. What is the SMALLEST guaranteed amount after one year you would take instead?", 0.20, -0.05,
        100_000, (0.075, 0.065, 0.055, 0.045, 0.035, 0.025, 0.015, 0.0)),
)
BY_ID = {b.id: b for b in BETS}

REACTION = {"sell_all": "Sell everything to stop the losses", "sell_some": "Sell part of it",
            "hold": "Do nothing and wait", "buy_more": "Invest more while prices are low"}

# The rest of the KYC form: capacity, used as optimizer constraints (not in A).
QUESTIONS = (
    *[{"id": b.id, "text": b.text, "kind": "choice", "options": [(ce, b.label(ce)) for ce in b.options]} for b in BETS],
    {"id": "loss_reaction", "text": "If your investments lost a fifth of their value in 3 months, what would you do?",
     "kind": "choice", "options": list(REACTION.items())},
    {"id": "max_loss_pct", "text": "What is the largest drop in one year you could live with, in %?", "kind": "number",
     "bounds": (0, 100)},
    {"id": "horizon_years", "text": "In how many years will you need most of this money?", "kind": "number",
     "bounds": (0, 60)},
    {"id": "exclusions", "text": "Anything you want to avoid? (crypto, fossil_fuels, single_stocks)", "kind": "list",
     "options": ["crypto", "fossil_fuels", "single_stocks"]},
)

# Fictional example answers for the three reference personas (they are NOT in the brief: chosen to match their stories).
EXAMPLES = {
    "amira": {"bet_small": 0.08, "bet_large": 0.10, "bet_savings": 0.065, "loss_reaction": "buy_more",
              "max_loss_pct": 35, "horizon_years": 15, "exclusions": []},
    "mateo": {"bet_small": 0.06, "bet_large": 0.06, "bet_savings": 0.045, "loss_reaction": "hold",
              "max_loss_pct": 20, "horizon_years": 10, "exclusions": ["fossil_fuels"]},
    "robert": {"bet_small": 0.04, "bet_large": 0.02, "bet_savings": 0.035, "loss_reaction": "hold",
               "max_loss_pct": 15, "horizon_years": 4, "exclusions": ["crypto"]},
}


def band(a: float) -> str:
    lo, hi = AVERAGE_BAND
    return ("above-average risk tolerance" if a < lo else "average investor" if a <= hi else
            "cautious (below-average risk tolerance)")


def check(answers: dict) -> list[str]:
    """Missing or invalid answers, as plain messages (empty = complete)."""
    out = []
    for b in BETS:
        v = answers.get(b.id)
        if v is None:
            out.append(f"{b.id}: answer needed")
        elif not isinstance(v, (int, float)) or not -1 < v <= b.mean:
            out.append(f"{b.id}: choose one of the guaranteed returns offered (at most {b.mean:.1%})")
    if answers.get("loss_reaction") not in REACTION:
        out.append("loss_reaction: choose one option")
    for k, (lo, hi) in (("max_loss_pct", (0, 100)), ("horizon_years", (0, 60))):
        v = answers.get(k)
        if v is not None and not lo <= v <= hi:
            out.append(f"{k}: between {lo} and {hi}")
    return out


def score(answers: dict) -> dict:
    """{A, A_median, A_by_bet, spread, band, flags, used, reasons}. Raises ValueError on incomplete answers."""
    bad = check(answers)
    if bad:
        raise ValueError("; ".join(bad))
    by_bet = {b.id: round(b.a_for(float(answers[b.id])), 2) for b in BETS}
    vals = list(by_bet.values())
    a_med, a_max = median(vals), max(vals)
    spread = a_max - min(vals)
    lo, hi = AVERAGE_BAND
    flags = []
    if spread > SPREAD_MAX:
        flags.append(f"the three bets disagree (A from {min(vals):.1f} to {a_max:.1f}, spread {spread:.1f} > "
                     f"{SPREAD_MAX:.0f})")
    r = answers["loss_reaction"]
    if r == "sell_all" and a_med < lo:
        flags.append(f"selling everything after a drop does not match bets of an investor bolder than average "
                     f"(A {a_med:.1f} < {lo:.0f})")
    if r == "buy_more" and a_med > hi:
        flags.append(f"buying more after a drop does not match bets of a cautious investor (A {a_med:.1f} > {hi:.0f})")
    a = a_max if flags else a_med
    reasons = [f"{b.id}: bet with mean {b.mean:.1%} and σ {b.var ** 0.5:.1%}, guaranteed {answers[b.id]:.1%} chosen "
               f"→ A = 2 × ({b.mean:.3f} − {answers[b.id]:.3f}) / {b.var:.4f} = {by_bet[b.id]:.2f}" for b in BETS]
    reasons.append(f"A used = {'most cautious bet (answers to clarify)' if flags else 'median of the three bets'} = "
                   f"{a:.2f} → {band(a)}")
    return {"A": round(a, 2), "A_median": round(a_med, 2), "A_by_bet": by_bet, "spread": round(spread, 2),
            "band": band(a), "flags": flags, "used": "most_cautious" if flags else "median", "reasons": reasons}


def constraints(answers: dict) -> dict:
    """The capacity answers → optimizer constraints (dh.markowitz.optimal keyword arguments)."""
    from .agents import rules

    out = {}
    if answers.get("max_loss_pct") is not None:
        out["loss_limit"] = answers["max_loss_pct"] / 100
    if answers.get("horizon_years") is not None:
        out["growth_cap"] = rules.horizon_max_growth(answers["horizon_years"])
    excl = set()
    for k in answers.get("exclusions") or []:
        excl |= rules.EXCLUSIONS.get(k, set())
    out["exclude"] = sorted(excl)
    return out


def ask_in_terminal() -> dict:  # pragma: no cover — interactive
    """The questionnaire in a terminal (python -m dh markowitz --ask)."""
    ans = {}
    for q in QUESTIONS:
        print("\n" + q["text"])
        while True:
            if q["kind"] == "choice":
                for i, (_, lab) in enumerate(q["options"], 1):
                    print(f"  {i}. {lab}")
                raw = input("Your choice (number): ").strip()
                if raw.isdigit() and 1 <= int(raw) <= len(q["options"]):
                    ans[q["id"]] = q["options"][int(raw) - 1][0]
                    break
            elif q["kind"] == "number":
                raw = input("Your answer: ").strip().rstrip("%").replace(",", ".")
                try:
                    v = float(raw)
                    lo, hi = q["bounds"]
                    if lo <= v <= hi:
                        ans[q["id"]] = v
                        break
                except ValueError:
                    pass
            else:
                raw = input("Comma-separated, or Enter for none: ").strip()
                items = [x.strip() for x in raw.split(",") if x.strip()]
                if all(x in q["options"] for x in items):
                    ans[q["id"]] = items
                    break
            print("  Please answer with one of the options shown.")
    return ans
