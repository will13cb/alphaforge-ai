"""Guided interface: the KYC bets and the expected-value question (decision #40) reach the Profiler.

The engine already scores them (profiler.kyc_check, expected_value_check); these tests check that the form asks them
with dh.kyc's own options, refuses a partial set, round-trips the demo clients, and says the result in plain words.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dh import kyc  # noqa: E402
from dh.agents import profiler  # noqa: E402
from dh.agents.scenarios import DEMO_PROFILES  # noqa: E402
from interface.core import services  # noqa: E402
from interface.core import wizard as w  # noqa: E402
from interface.core.questions import BET_IDS, BY_ID, STEPS  # noqa: E402

GOOD = {"age": "59", "income_stability": "stable", "emergency_fund_months": "12", "objective": "retirement",
        "capital": "400,000", "horizon_years": "4", "loss_reaction": "hold", "max_loss_pct": "15",
        "knowledge_level": "advanced", "years_experience": "20"}
IDX = {s.id: i for i, s in enumerate(STEPS)}
ROBERT_BETS = {"bet_small": 0.046, "bet_large": 0.0, "bet_savings": 0.038}


def test_bets_use_the_questionnaire_options_and_can_be_skipped():
    for b in kyc.BETS:
        q = BY_ID[b.id]
        assert q.label == b.text and not q.required and q.default == ""
        assert [o for o, _ in q.options][:-1] == list(b.options)          # same grid of attitudes (R6), then skip
        assert q.options[-1][0] == ""
    vals, errs = w.check_step(IDX["attitude"], {})
    assert not errs and all(vals[b] is None for b in BET_IDS)
    assert "kyc_bets" not in w.to_profile(w.all_values(GOOD)[0])


def test_all_three_bets_or_none():
    _, errs = w.check_step(IDX["attitude"], {"bet_small": 0.046})
    assert set(errs) == {"bet_large"} and "all three" in errs["bet_large"]
    vals, errs = w.check_step(IDX["attitude"], ROBERT_BETS)
    assert not errs
    p = w.to_profile(w.all_values({**GOOD, **ROBERT_BETS})[0])
    assert p["kyc_bets"] == ROBERT_BETS                       # 0.0 is an answer, not a skip


def test_expected_value_question_reaches_the_knowledge_score():
    e = IDX["experience"]
    assert "ev_answer_pct" not in [q.id for q in w.visible(e, {"knowledge_level": "none"})]
    assert "ev_answer_pct" in [q.id for q in w.visible(e, {"knowledge_level": "advanced"})]
    assert "+25%" in BY_ID["ev_answer_pct"].label and "−5%" in BY_ID["ev_answer_pct"].label
    _, errs = w.check_step(e, {**GOOD, "ev_answer_pct": "abc"})
    assert set(errs) == {"ev_answer_pct"}
    right = w.to_profile(w.all_values({**GOOD, "ev_answer_pct": "10%"})[0])
    wrong = w.to_profile(w.all_values({**GOOD, "ev_answer_pct": "-5"})[0])
    assert right["ev_answer_pct"] == 10 and wrong["ev_answer_pct"] == -5
    assert profiler.knowledge_score(right)[0] > profiler.EV_WRONG_CAP
    assert profiler.knowledge_score(wrong)[0] == profiler.EV_WRONG_CAP   # the engine's rule, not the form's


def test_demo_clients_keep_their_kyc_answers_through_the_form():
    for key, prof in DEMO_PROFILES.items():
        vals, errs = w.all_values(w.from_profile(prof))
        assert not errs, (key, errs)
        back = w.to_profile(vals)
        assert back.get("kyc_bets") == prof.get("kyc_bets"), key
        assert back.get("ev_answer_pct") == prof.get("ev_answer_pct"), key


def test_cross_check_in_plain_words_and_limits_unchanged():
    p = w.to_profile(w.all_values({**GOOD, **ROBERT_BETS, "ev_answer_pct": "10"})[0])
    with_kyc = profiler.derive_limits(p)
    without = profiler.derive_limits({k: v for k, v in p.items() if k not in ("kyc_bets", "ev_answer_pct")})
    assert {k: v for k, v in with_kyc.items() if k != "kyc"} == {k: v for k, v in without.items() if k != "kyc"}
    lines = services.kyc_lines(with_kyc)
    assert lines and with_kyc["kyc"]["band"] in lines[0] and "did not change your limits" in lines[-1]
    assert services.kyc_lines(without) == [] and services.kyc_lines({}) == []
    bold = profiler.derive_limits({**p, "loss_reaction": "sell_all", "max_loss_pct": 5,
                                   "kyc_bets": {"bet_small": 0.1, "bet_large": 0.15, "bet_savings": 0.075}})
    text = " ".join(services.kyc_lines(bold))
    assert "bolder than your other answers" in text and "To clarify:" in text   # selling all vs bold bets
