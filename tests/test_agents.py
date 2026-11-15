"""Profiler + Guardian rules: every scenario behaves as expected; look-through adds up."""
import pytest

from dh.agents.scenarios import SCENARIOS, evaluate
from dh.metrics import look_through, overlap


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_scenario(sc):
    _, bad = evaluate(sc)
    assert not bad, bad


def test_look_through():
    eff = look_through({"NVDA": 0.10, "QQQ": 0.50}, {"QQQ": {"NVDA": 0.10}})
    assert eff["NVDA"] == pytest.approx(0.15)
    assert sum(eff.values()) == pytest.approx(0.60)
    assert overlap({"A": 0.5, "B": 0.5}, {"A": 0.3, "C": 0.7}) == pytest.approx(0.3)


def test_company_caps_follow_client_and_data():
    """Decision #24: caps move with each client and each asset's own worst drop; no fixed per-level cap."""
    from dh.agents.profiler import derive_limits
    from dh.agents.scenarios import AMIRA, MATEO, ROBERT

    a = derive_limits(AMIRA)
    assert a["company_caps"]["TSLA"] < a["company_caps"]["NVDA"] < a["company_caps"]["JNJ"]   # more volatile, smaller
    m = derive_limits(MATEO)
    assert m["company_caps"]["TSLA"] < a["company_caps"]["TSLA"]                              # more cautious client
    r = derive_limits({**ROBERT, "requested_positions": {"TSLA": 0.25}})
    assert r["risk_capacity"] == 2 and r["max_crypto"] == 0.0                                 # crypto excluded
    req = r["request_checks"][0]
    assert req["fits_up_to"] < 0.25 and "-70.9%" in req["reason"] and "refus" not in req["reason"]
    beginner = derive_limits({**AMIRA, "knowledge_level": "none", "years_experience": 0, "quiz_correct": 0})
    assert beginner["max_crypto"] == 0.0 and beginner["company_caps"]["TSLA"] < a["company_caps"]["TSLA"]
    nodata = derive_limits(AMIRA, drops={})                                                   # no data: assume -100%
    assert nodata["company_caps"]["JNJ"] <= a["company_caps"]["JNJ"]



@pytest.mark.parametrize("change", [{"max_loss_pct": 0}, {"horizon_years": 1}], ids=["loss-0pct", "horizon-1y"])
def test_zero_company_cap_is_a_fail_not_a_crash(change):
    """A 0% company cap (loss limit 0%, or no stocks allowed by the horizon) used to divide by zero in G4."""
    from dh.agents import guardian
    from dh.agents.profiler import derive_limits
    from dh.agents.scenarios import ROBERT

    p = {**ROBERT, **change}
    lim = derive_limits(p)
    assert lim["company_caps"]["TSLA"] == 0.0
    s = {"weights": {"TSLA": 0.10, "JNJ": 0.05, "XBB.TO": 0.85}, "stats": {}}
    g4 = next(c for c in guardian.check_strategy(s, lim, p, {}) if c["rule"] == "G4")
    assert g4["status"] == "fail" and "TSLA 10.0% vs 0.0%" in g4["detail"]
