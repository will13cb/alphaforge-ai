"""interface/core/questions.py + wizard.py: which questions show, what blocks, what the engine receives."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dh.agents import extractor, rules  # noqa: E402
from dh.agents.scenarios import DEMO_PROFILES  # noqa: E402
from interface.core import wizard as w  # noqa: E402
from interface.core.questions import ALL_STEPS, BY_ID, STEPS  # noqa: E402

GOOD = {"age": "59", "income_stability": "stable", "emergency_fund_months": "12", "objective": "retirement",
        "capital": "400,000", "horizon_years": "4", "loss_reaction": "hold", "max_loss_pct": "15",
        "knowledge_level": "advanced", "years_experience": "20"}
IDX = {s.id: i for i, s in enumerate(STEPS)}


def test_every_essential_field_is_asked_and_required():
    for f in rules.ESSENTIAL_FIELDS:
        assert f in BY_ID and BY_ID[f].required, f


def test_every_profile_question_matches_the_schema():
    for q in BY_ID.values():
        if q.kind in ("whole", "decimal", "money", "percent") and q.bounds is None:
            assert q.id in extractor.NUMBERS, q.id
        if q.kind == "choice" and q.id in extractor.ENUMS:
            assert {o for o, _ in q.options} == set(extractor.ENUMS[q.id])


def test_questions_appear_only_when_relevant():
    ids = lambda i, a: [q.id for q in w.visible(i, a)]  # noqa: E731
    m = IDX["money"]
    assert "target_amount" not in ids(m, {}) and "target_amount" in ids(m, {"has_target": "yes"})
    assert "withdrawal_share_3y" not in ids(m, {}) and "withdrawal_share_3y" in ids(m, {"withdrawals": "yes"})
    e = IDX["experience"]
    assert "years_experience" not in ids(e, {"knowledge_level": "none"})
    assert "years_experience" in ids(e, {"knowledge_level": "basic"})
    assert "employment_sector" not in [q.id for q in w.visible(IDX["you"], {}, show_advanced=False)]


def test_a_step_blocks_until_fixed_and_hidden_answers_are_ignored():
    _, errs = w.check_step(IDX["you"], {})
    assert set(errs) == {"age", "income_stability", "emergency_fund_months"}
    _, errs = w.check_step(IDX["you"], {**GOOD, "age": "abc"})
    assert set(errs) == {"age"}
    _, errs = w.check_step(IDX["money"], {**GOOD, "target_amount": "nonsense"})   # hidden: not checked
    assert not errs
    _, errs = w.check_step(IDX["money"], {**GOOD, "has_target": "yes"})          # shown and empty: needed
    assert set(errs) == {"target_amount"}


def test_incompatible_combination_nothing_to_invest():
    _, errs = w.check_step(IDX["money"], {**GOOD, "capital": "0", "monthly_contribution": "0"})
    assert "nothing to invest" in errs["capital"]
    assert not w.check_step(IDX["money"], {**GOOD, "capital": "0", "monthly_contribution": "500"})[1]


def test_percent_fields_use_the_engine_units():
    vals, errs = w.check_step(IDX["money"], {**GOOD, "withdrawals": "yes", "withdrawal_share_3y": "20"})
    assert not errs and w.to_profile(vals)["withdrawal_share_3y"] == 0.20
    _, errs = w.check_step(IDX["money"], {**GOOD, "withdrawals": "yes", "withdrawal_share_3y": "120"})
    assert "between 0 and 100" in errs["withdrawal_share_3y"]


def test_full_answers_give_a_complete_profile():
    vals, errs = w.all_values(GOOD)
    assert not errs
    p = w.to_profile(vals)
    assert extractor.missing(p) == [] and p["capital"] == 4e5 and p["max_loss_pct"] == 15 and p["name"] == "You"
    assert w.first_step_with_errors({}) == 0 and w.first_step_with_errors(GOOD) is None


def test_progress_and_round_trip_of_demo_clients():
    assert w.progress(0) == 0 and w.progress(len(ALL_STEPS) - 1) == 1
    for key, prof in DEMO_PROFILES.items():
        vals, errs = w.all_values(w.from_profile(prof))
        assert not errs, (key, errs)
        back = w.to_profile(vals)
        for f in rules.ESSENTIAL_FIELDS:
            assert back[f] == prof[f], (key, f)
        assert back.get("requested_positions", {}) == prof.get("requested_positions", {}) or not prof.get("requested_positions")
