"""(D) dh.risk.kyc_validation: bet comparability, cautious ≠ inconsistent, question measure = engine measure."""
import pytest

from dh import kyc
from dh.risk import kyc_validation as kv
from dh.risk.contracts import LossMeasure

CAUTIOUS = {b.id: b.options[-1] for b in kyc.BETS}
GAP = 0.3   # test value for decision R6


class TestInterpretation:
    def test_cautious_everywhere_is_censored_not_inconsistent(self):
        c = kv.consistency(CAUTIOUS, GAP)
        assert c.status == "censored_cautious" and all(i.severity == "info" for i in c.issues)

    def test_real_gap_is_inconsistent(self):
        ans = {"bet_small": kyc.BETS[0].options[0], "bet_large": kyc.BETS[1].options[-1],
               "bet_savings": kyc.BETS[2].options[3]}
        assert kv.consistency(ans, GAP).status == "inconsistent"

    def test_personas_examples_consistent(self):
        for name, ex in kyc.EXAMPLES.items():
            assert kv.consistency(ex, GAP).status in ("consistent", "censored_cautious"), name

    def test_loss_question_matches_the_engine_measure(self):
        """R7: the question asks for a drop from a high point at any time = the simulated drawdown over the horizon."""
        assert kv.comparable("max_loss_pct") == []
        assert "from a high point" in next(q["text"] for q in kyc.QUESTIONS if q["id"] == "max_loss_pct")
        assert [i.code for i in kv.comparable("max_loss_pct", LossMeasure.MDD_WINDOW)] == ["D-measure"]


class TestTechnical:
    def test_answer_not_in_options_refused(self):
        with pytest.raises(ValueError):
            kv.rank(kyc.BETS[0], 0.033)

    def test_normalisation_waits_for_decision(self):
        assert kv.normalise_loss_limit(.2, LossMeasure.WORST_12M, LossMeasure.WORST_12M) == .2
        with pytest.raises(NotImplementedError):
            kv.normalise_loss_limit(.2, LossMeasure.WORST_12M, LossMeasure.MDD_WINDOW)


class TestAnomaly:
    def test_bets_are_comparable(self):
        """A4, fixed by the common A grid (R6); was xfail strict (max A was 8.9 / 4.8 / 9.6)."""
        assert kv.comparability()["comparable"]

    def test_kyc_score_does_not_flag_cautious(self):
        """A4, fixed: a consistently cautious client is censored, not inconsistent; was xfail strict."""
        sc = kyc.score({**CAUTIOUS, "loss_reaction": "hold"})
        assert sc["flags"] == [] and sc["consistency"] == "censored_cautious" and sc["A"] == pytest.approx(4.8, abs=.1)

    def test_old_answers_off_the_grid_are_refused(self):
        assert kyc.check({"bet_small": 0.08, "bet_large": 0.10, "bet_savings": 0.065, "loss_reaction": "hold"})
