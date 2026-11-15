"""KYC bets (dh.kyc) as a Profiler cross-check, and the expected-value question (decision #40). Offline."""
from dh.agents.profiler import derive_limits
from dh.agents.scenarios import AMIRA, MATEO, ROBERT
from dh.agents.trace import describe_limits


def _no_kyc(p):
    return {k: v for k, v in p.items() if k not in ("kyc_bets", "ev_answer_pct")}


def test_personas_bets_agree_and_change_no_limit():
    for p in (AMIRA, MATEO, ROBERT):
        lim, ref = derive_limits(p), derive_limits(_no_kyc(p))
        assert lim["kyc"]["agrees"] and not lim["kyc"]["flags"], lim["kyc"]
        assert {k: v for k, v in lim.items() if k != "kyc"} == {k: v for k, v in ref.items() if k != "kyc"}
        assert "cross-check only" in describe_limits(lim)


def test_bets_more_cautious_than_stated_are_flagged_not_applied():
    p = {**AMIRA, "kyc_bets": {"bet_small": 0.046, "bet_large": 0.0, "bet_savings": 0.038}}  # Robert's bets
    lim = derive_limits(p)
    assert not lim["kyc"]["agrees"] and any("to clarify" in f for f in lim["kyc"]["flags"])
    assert lim["risk_tolerance"] == derive_limits(_no_kyc(AMIRA))["risk_tolerance"]  # limits unchanged


def test_expected_value_wrong_caps_knowledge():
    p = {**ROBERT, "ev_answer_pct": 25}      # took the good case for the average
    lim = derive_limits(p)
    assert derive_limits(ROBERT)["knowledge_score"] > 3 and lim["knowledge_score"] == 3
    assert any("expected-value" in r for r in lim["reasons"])
    assert not lim["kyc"]["expected_value"]["correct"]


def test_no_answers_no_kyc_and_bad_answers_reported():
    assert derive_limits(_no_kyc(MATEO))["kyc"] is None
    lim = derive_limits({**_no_kyc(MATEO), "kyc_bets": {"bet_small": 0.5}})
    assert "error" in lim["kyc"]
