"""KYC questionnaire → the risk-aversion coefficient A of the mean-variance utility U = E(r) − ½·A·σ² (decision #38).

How A is scored (no table invented): each "bet" question is a 50/50 investment with a known mean m and variance σ².
The person picks the smallest GUARANTEED return they would take instead of it: their certainty equivalent CE. In the
mean-variance model the person is indifferent when U(bet) = U(sure), i.e. m − ½·A·σ² = CE, so

    A = 2 · (m − CE) / σ²

Three bets of different sizes give three estimates; A is their median.

Comparable answers (audit A4, decision R6): each bet offers the guaranteed returns that correspond to the SAME grid of
A values (A_GRID), so the n-th option means the same attitude on every bet. The grid stops at 4.8, the largest A the
+40%/−10% bet can express without a negative guaranteed return; a client at the most cautious option everywhere has
A ≥ 4.8 ("censored"), which is consistent, not contradictory. Consistency is judged on option RANKS (0 = boldest,
1 = most cautious), not on raw A.

KYC rules (Canadian practice: when answers conflict, the advisor clarifies; until then, the more cautious reading):
- the three bets' option ranks are further apart than MAX_RANK_GAP (0.3, about two options), or
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
A_GRID = (0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 4.8)   # the same attitudes offered on every bet (R6), boldest first
MAX_RANK_GAP = 0.3           # R6: option ranks further apart than this → the bets disagree (about two options)


def _options(up: float, down: float) -> tuple:
    """Guaranteed returns matching A_GRID for a 50/50 bet (CE = m − A·σ²/2), to 0.1%, highest (boldest) first."""
    m, var = (up + down) / 2, ((up - down) / 2) ** 2
    return tuple(round(m - a * var / 2, 3) + 0.0 for a in A_GRID)


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
        "take instead of the investment?", 0.25, -0.05, 10_000, _options(0.25, -0.05)),
    Bet("bet_large", "You invest 10,000 $ for one year. With equal chances, you end at +40% (14,000 $) or at −10% "
        "(9,000 $). What is the SMALLEST guaranteed return you would take instead?", 0.40, -0.10, 10_000,
        _options(0.40, -0.10)),
    Bet("bet_savings", "Your savings are 100,000 $. An investment ends the year, with equal chances, at 120,000 $ or "
        "at 95,000 $. What is the SMALLEST guaranteed amount after one year you would take instead?", 0.20, -0.05,
        100_000, _options(0.20, -0.05)),
)
BY_ID = {b.id: b for b in BETS}

REACTION = {"sell_all": "Sell everything to stop the losses", "sell_some": "Sell part of it",
            "hold": "Do nothing and wait", "buy_more": "Invest more while prices are low"}

# The rest of the KYC form: capacity, used as optimizer constraints (not in A).
QUESTIONS = (
    *[{"id": b.id, "text": b.text, "kind": "choice", "options": [(ce, b.label(ce)) for ce in b.options]} for b in BETS],
    {"id": "loss_reaction", "text": "If your investments lost a fifth of their value in 3 months, what would you do?",
     "kind": "choice", "options": list(REACTION.items())},
    {"id": "max_loss_pct", "text": "What is the largest drop from a high point, at any time while invested, that you "
     "could live with, in %?", "kind": "number",
     "bounds": (0, 100)},
    {"id": "horizon_years", "text": "In how many years will you need most of this money?", "kind": "number",
     "bounds": (0, 60)},
    {"id": "exclusions", "text": "Anything you want to avoid? (crypto, fossil_fuels, single_stocks)", "kind": "list",
     "options": ["crypto", "fossil_fuels", "single_stocks"]},
)

# Fictional example answers for the three reference personas (they are NOT in the brief: chosen to match their stories).
EXAMPLES = {
    "amira": {"bet_small": 0.083, "bet_large": 0.103, "bet_savings": 0.063, "loss_reaction": "buy_more",
              "max_loss_pct": 35, "horizon_years": 15, "exclusions": []},
    "mateo": {"bet_small": 0.055, "bet_large": 0.056, "bet_savings": 0.044, "loss_reaction": "hold",
              "max_loss_pct": 20, "horizon_years": 10, "exclusions": ["fossil_fuels"]},
    "robert": {"bet_small": 0.046, "bet_large": 0.0, "bet_savings": 0.038, "loss_reaction": "hold",
               "max_loss_pct": 15, "horizon_years": 4, "exclusions": ["crypto"]},
}


def band(a: float) -> str:
    lo, hi = AVERAGE_BAND
    return ("above-average risk tolerance" if a < lo else "average investor" if a <= hi else
            "cautious (below-average risk tolerance)")


def rank(bet: Bet, ce: float) -> float:
    """Position of the answer in the bet's options: 0 = boldest, 1 = most cautious. ValueError if not an option."""
    for i, o in enumerate(bet.options):
        if abs(float(ce) - o) <= 5e-4:
            return i / (len(bet.options) - 1)
    raise ValueError(f"{bet.id}: {ce} is not one of the options {bet.options}")


def check(answers: dict) -> list[str]:
    """Missing or invalid answers, as plain messages (empty = complete)."""
    out = []
    for b in BETS:
        v = answers.get(b.id)
        if v is None:
            out.append(f"{b.id}: answer needed")
            continue
        try:
            rank(b, v)
        except (ValueError, TypeError):
            out.append(f"{b.id}: choose one of the guaranteed returns offered ({', '.join(f'{o:.1%}' for o in b.options)})")
    if answers.get("loss_reaction") not in REACTION:
        out.append("loss_reaction: choose one option")
    for k, (lo, hi) in (("max_loss_pct", (0, 100)), ("horizon_years", (0, 60))):
        v = answers.get(k)
        if v is not None and not lo <= v <= hi:
            out.append(f"{k}: between {lo} and {hi}")
    return out


def consistency(answers: dict, max_rank_gap: float = MAX_RANK_GAP) -> dict:
    """{status, ranks, gap}: 'censored_cautious' (most cautious option everywhere: A ≥ the grid's top, consistent),
    'censored_bold', 'inconsistent' (ranks further apart than max_rank_gap) or 'consistent'."""
    ranks = {b.id: rank(b, answers[b.id]) for b in BETS}
    vals = list(ranks.values())
    gap = max(vals) - min(vals)
    status = ("censored_cautious" if all(v == 1.0 for v in vals) else "censored_bold" if all(v == 0.0 for v in vals)
              else "inconsistent" if gap > max_rank_gap + 1e-9 else "consistent")
    return {"status": status, "ranks": ranks, "gap": gap}


def score(answers: dict) -> dict:
    """{A, A_median, A_by_bet, spread, rank_gap, consistency, band, flags, used, reasons}. ValueError on incomplete
    answers."""
    bad = check(answers)
    if bad:
        raise ValueError("; ".join(bad))
    by_bet = {b.id: round(b.a_for(float(answers[b.id])), 2) for b in BETS}
    vals = list(by_bet.values())
    a_med, a_max = median(vals), max(vals)
    spread = a_max - min(vals)
    cons = consistency(answers)
    lo, hi = AVERAGE_BAND
    flags = []
    if cons["status"] == "inconsistent":
        flags.append(f"the three bets point to different attitudes (options {min(cons['ranks'].values()):.0%} to "
                     f"{max(cons['ranks'].values()):.0%} of the way to the most cautious, gap > {MAX_RANK_GAP:.0%})")
    r = answers["loss_reaction"]
    if r == "sell_all" and a_med < lo:
        flags.append(f"selling everything after a drop does not match bets of an investor bolder than average "
                     f"(A {a_med:.1f} < {lo:.0f})")
    if r == "buy_more" and a_med > hi:
        flags.append(f"buying more after a drop does not match bets of a cautious investor (A {a_med:.1f} > {hi:.0f})")
    a = a_max if flags else a_med
    reasons = [f"{b.id}: bet with mean {b.mean:.1%} and σ {b.var ** 0.5:.1%}, guaranteed {answers[b.id]:.1%} chosen "
               f"→ A = 2 × ({b.mean:.3f} − {answers[b.id]:.3f}) / {b.var:.4f} = {by_bet[b.id]:.2f}" for b in BETS]
    used = "most cautious bet (answers to clarify)" if flags else "median of the three bets"
    if cons["status"] == "censored_cautious" and not flags:
        reasons.append(f"most cautious option on every bet: A is at least {a:.2f} (the top of the scale), consistent")
    reasons.append(f"A used = {used} = {a:.2f} → {band(a)}")
    return {"A": round(a, 2), "A_median": round(a_med, 2), "A_by_bet": by_bet, "spread": round(spread, 2),
            "rank_gap": round(cons["gap"], 3), "consistency": cons["status"], "band": band(a), "flags": flags,
            "used": "most_cautious" if flags else "median", "reasons": reasons}


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
