"""The questions, in plain English, grouped in steps (Will's intake form, notes/intake-form.md, short mode).

Each question maps to a field of the engine's `profile` (contract §1). Its type, limits and choices come from the
engine's schema (`extractor.NUMBERS`, `ENUMS`, `LISTS`, `SECTORS`); only the wording, the help and the examples are
written here. `visible_if` hides a question until an earlier answer makes it relevant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from dh import kyc
from dh.agents import extractor


@dataclass(frozen=True)
class Question:
    id: str                       # profile field, or a helper answer (has_target, withdrawals, request)
    label: str                    # the question, plain language
    kind: str                     # whole | decimal | money | percent | choice | choices | name | yesno | position
    example: str = ""             # shown in italics under the field
    help: str = ""                # the ⓘ explanation
    required: bool = True
    advanced: bool = False        # folded under "More options" for beginners
    default: object = None
    options: tuple = ()           # (value, label) pairs for choice / choices
    visible_if: Callable[[dict], bool] | None = None
    bounds: tuple | None = None   # (min, max) when not a profile field with a schema range


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    intro: str
    questions: tuple = field(default_factory=tuple)


def _opts(pairs: dict) -> tuple:
    return tuple(pairs.items())


OBJECTIVES = {
    "growth": "Grow my money over the long term",
    "retirement": "Prepare for retirement",
    "major_project": "Save for a big project (a home, studies, a business)",
    "income": "Get a regular income from my savings",
    "legacy": "Pass it on to my family",
    "safety_cushion": "Keep a safety cushion for emergencies",
}
INCOME = {"stable": "Stable (for example a salary)", "variable": "It varies (commissions, freelance, seasonal)",
          "uncertain": "Uncertain (my job or income may change soon)"}
REACTION = {"sell_all": "Sell everything to stop the losses", "sell_some": "Sell part of it",
            "hold": "Do nothing and wait for it to recover", "buy_more": "Invest more while prices are low"}
KNOWLEDGE = {"none": "I'm new to investing", "basic": "I know the basics (what a stock or a fund is)",
             "intermediate": "I'm comfortable: I have invested in funds or stocks",
             "advanced": "Experienced: I follow markets and manage my own investments"}
PRODUCTS = {"etfs": "Index funds (ETFs)", "funds": "Mutual funds", "stocks": "Company shares (stocks)",
            "bonds": "Bonds", "gics": "GICs (guaranteed investment certificates)", "crypto": "Crypto-assets"}
INTERESTS = {"dividends": "Companies that pay regular dividends", "canada": "Canadian companies",
             "us": "U.S. companies", "esg": "Responsible investing (environmental and social criteria)",
             "tech": "Technology", "ai": "Artificial intelligence", "gold": "Gold", "bonds": "Bonds",
             "crypto": "Crypto-assets (Bitcoin, Ether)"}
EXCLUSIONS = {"fossil_fuels": "Fossil fuels (oil, gas, pipelines)", "crypto": "Crypto-assets",
              "single_stocks": "Individual company shares (funds only)"}
SECTORS = {s: s for s in extractor.SECTORS} | {"": "I'd rather not say"}
YESNO = (("no", "No"), ("yes", "Yes"))
SKIP = ("", "I'd rather skip this one")
# KYC bets (decision #40, Joud's questionnaire): wording and options come from dh.kyc, the same grid of attitudes on
# every bet (R6). The engine reads them as a cross-check only: they never change a limit.
BET_IDS = tuple(b.id for b in kyc.BETS)
EV_BET = kyc.BETS[0]  # the expected-value question uses the first bet (profiler.expected_value_check)


def _bet_question(b: kyc.Bet) -> Question:
    return Question(b.id, b.text, "choice", required=False, default="",
                    options=tuple((ce, b.label(ce)) for ce in b.options) + (SKIP,),
                    help="There is no right answer. Each option is a guaranteed amount you would take instead of "
                         "the uncertain investment; a higher one means you would rather keep the chance of the gain.")

assert set(OBJECTIVES) == set(extractor.ENUMS["objective"])          # wording covers every value the engine knows
assert set(INCOME) == set(extractor.ENUMS["income_stability"])
assert set(REACTION) == set(extractor.ENUMS["loss_reaction"])
assert set(KNOWLEDGE) == set(extractor.ENUMS["knowledge_level"])
assert set(PRODUCTS) <= extractor.LISTS["products_held"] and set(INTERESTS) <= extractor.LISTS["interests"]

STEPS = (
    Step("you", "About you", "A few facts about your situation. They decide how much risk your situation can carry.", (
        Question("name", "What should we call you?", "name", "Ex.: Robert", required=False,
                 help="Only used to address you in the explanation. Nothing is stored."),
        Question("age", "How old are you?", "whole", "Ex.: 45"),
        Question("income_stability", "How stable is your income?", "choice", options=_opts(INCOME),
                 help="A stable income can absorb a bad year in the markets more easily."),
        Question("emergency_fund_months", "How many months of expenses do you have set aside for emergencies?",
                 "decimal", "Ex.: 6", help="Money kept apart for job loss or repairs, not invested. "
                 "Without it, you might have to sell investments at a bad time."),
        Question("employment_sector", "In which sector do you work?", "choice", required=False, advanced=True,
                 options=_opts(SECTORS), default="",
                 help="We avoid putting too much of your savings in your own industry: if it has a hard year, your "
                      "job and your savings would suffer together."),
    )),
    Step("money", "Your money and your goal", "What the money is for, how much, and for how long.", (
        Question("objective", "What is this money mainly for?", "choice", options=_opts(OBJECTIVES)),
        Question("capital", "How much would you invest today, in dollars?", "money", "Ex.: 10,000",
                 help="The amount you already have and want to invest. Use 0 if you start with monthly amounts only."),
        Question("monthly_contribution", "How much could you add each month, in dollars?", "money", "Ex.: 250",
                 required=False, default="0", help="Leave 0 if you won't add money regularly."),
        Question("horizon_years", "In how many years will you need most of this money?", "decimal", "Ex.: 10",
                 help="Your investment horizon. The sooner you need the money, the less room there is to wait for "
                      "markets to recover after a drop."),
        Question("has_target", "Do you have a specific amount you want to reach?", "yesno", required=False,
                 options=YESNO, default="no"),
        Question("target_amount", "What amount would you like to reach, in dollars?", "money", "Ex.: 150,000",
                 visible_if=lambda a: a.get("has_target") == "yes",
                 help="We'll show your chance of reaching it, without assuming past returns will repeat."),
        Question("withdrawals", "Might you need part of this money within the next 3 years?", "yesno",
                 required=False, options=YESNO, default="no"),
        Question("withdrawal_share_3y", "What share might you need within 3 years, in %?", "percent", "Ex.: 20",
                 visible_if=lambda a: a.get("withdrawals") == "yes",
                 help="That part will be kept in safer investments, so it is there when you need it."),
    )),
    Step("risk", "Ups and downs", "Investments go up and down. These two answers set the loss you can live with.", (
        Question("loss_reaction", "If your investments lost a fifth of their value in 3 months, what would you do?",
                 "choice", options=_opts(REACTION),
                 help="There is no right answer. People who sell after a drop often lock in the loss."),
        Question("max_loss_pct", "What is the largest drop from a high point, at any time while invested, that you "
                 "could live with, in %?", "percent", "Ex.: 15 (for 15%)",
                 help="From the highest value your investments reach to the lowest point after it, whenever it "
                      "happens. For example, 15 means that 10,000 $ could fall to 8,500 $ for a while."),
    )),
    Step("experience", "Your experience", "We only propose what you can understand and follow.", (
        Question("knowledge_level", "How would you describe your investing experience?", "choice",
                 options=_opts(KNOWLEDGE)),
        Question("years_experience", "For how many years have you been investing?", "whole", "Ex.: 5",
                 required=False, visible_if=lambda a: a.get("knowledge_level") not in (None, "", "none")),
        Question("products_held", "Which of these have you already owned?", "choices", required=False,
                 options=_opts(PRODUCTS), default=(),
                 visible_if=lambda a: a.get("knowledge_level") not in (None, "", "none")),
        Question("ev_answer_pct", f"An investment ends the year at {EV_BET.up:+.0%} or at "
                 f"{EV_BET.down:+.0%}".replace("-", "−") + ", with equal chances. On average, what return would you "
                 "expect, in %?", "percent", "Digits only, e.g. 3.5 for 3.5%", required=False, bounds=(-100, 100),
                 visible_if=lambda a: a.get("knowledge_level") not in (None, "", "none"),
                 help="A quick check of how an average works. If the answer is off, your experience counts as "
                      "intermediate at most. You can leave it empty."),
    )),
    Step("attitude", "Three quick choices (optional)",
         "Each time, choose between an uncertain investment and a guaranteed amount. These answers only check your "
         "other answers: they never change your limits. Answer all three, or skip them all.",
         tuple(_bet_question(b) for b in kyc.BETS)),
    Step("preferences", "Your preferences (optional)", "Tell us what you like or want to avoid. You can skip this step.", (
        Question("investment_mode", "What kind of portfolio would you like?", "choice", required=False, default="market",
                 options=(("market", "Market portfolio (stocks and/or bond funds)"),
                          ("fixed_rate", "Bonds only, held to maturity"))),
        Question("fixed_income_market", "Where should we look for bonds?", "choice", required=False, default="both",
                 options=(("both", "Canada and U.S."), ("canada", "Canada only"), ("us", "U.S. only")),
                 visible_if=lambda a: a.get("investment_mode") == "fixed_rate"),
        Question("fixed_rate_pct", "What annual bond rate are you looking for, in %?", "decimal", "Ex.: 3",
                 default="3", visible_if=lambda a: a.get("investment_mode") == "fixed_rate",
                 help="We look for sourced Canadian and U.S. fixed-income instruments near your horizon. Unsupported rates are flagged, never invented."),
        Question("interests", "Is there anything you'd like to invest in?", "choices", required=False,
                 options=_opts(INTERESTS), default=()),
        Question("exclusions", "Is there anything you want to avoid?", "choices", required=False,
                 options=_opts(EXCLUSIONS), default=()),
        Question("request", "Is there one investment you'd like to include, and what share?", "position",
                 "Ex.: Tesla and 10 (for 10%)", required=False, advanced=True,
                 help="We'll show you what it does to your risk, next to a version that fits your limits. "
                      "The choice stays yours."),
    )),
)
REVIEW = Step("review", "Check and run", "Check your answers, then run the analysis.")
ALL_STEPS = STEPS + (REVIEW,)
BY_ID = {q.id: q for s in STEPS for q in s.questions}
