"""Critic (Strands agent, #30): offline. The agent is faked; tools, validation, recalculation and Guardian are real."""
import pytest

from dh.agents import critic, guardian, portfolio
from dh.agents.pipeline import run
from dh.agents.profiler import derive_limits
from dh.agents.rules import DEFENSIVE
from dh.agents.scenarios import AMIRA, MATEO, ROBERT
from test_portfolio import fewer_scenarios, rets  # noqa: F401  (fixtures)


@pytest.fixture(autouse=True)
def no_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(critic, "DEMO_CACHE", tmp_path / "demo")
    monkeypatch.setattr(critic, "LOCAL_CACHE", tmp_path / "local")


def _calls(result):
    return [{"call_id": "t1", "tool": "correlation_between", "args": {}, "result": result}]


def test_validate_drops_unbacked_numbers_and_keeps_backed_ones():
    calls = _calls({"pairs": [{"a": "QQQ", "b": "SPY", "correlation": 0.912}], "note": "worst drop -31.4%"})
    strats = [{"key": "growth"}]
    raw = [{"strategy": "growth", "claim": "QQQ and SPY correlate 0.91; worst drop 31.4%.", "evidence": ["t1"]},
           {"strategy": "growth", "claim": "This will earn 13.4% a year.", "evidence": ["t1"]},
           {"strategy": "growth", "claim": "Same bet.", "evidence": ["t9"]},
           {"strategy": "nope", "claim": "x", "evidence": ["t1"]}]
    st = [o["status"] for o in critic.validate(raw, calls, strats)]
    assert st[0] == "valid" and "13.4%" in st[1] and "no tool call" in st[2] and "unknown strategy" in st[3]



def test_validate_accepts_facts_numbers_durations_and_weight_sums():
    """Audit: Robert's TSLA objection was dropped for quoting his own request (25%) and loss limit (15%), K2 for
    "12 months", Amira's for QQQ + SPY = 61.5%. Those come from FACTS / code, so they back a claim; inventions don't."""
    calls = _calls({"assets": [{"ticker": "TSLA", "max_drawdown": -0.709}]})
    f = {"client": {"requested_positions": {"TSLA": 0.25}, "max_loss_pct": 15},
         "limits": {"loss_limit": 0.15},
         "strategies": [{"key": "growth", "weights": {"QQQ": 0.30, "SPY": 0.315, "XBB.TO": 0.385},
                         "split": {"growth": 0.615}, "stats": {"worst_12m": -0.062}}]}
    strats = [{"key": "growth"}]
    raw = [{"strategy": "growth", "evidence": ["t1"],
            "claim": "He asked for 25% in TSLA; its worst drop was -70.9%, beyond his 15% loss limit."},
           {"strategy": "growth", "evidence": ["t1"], "claim": "Worst 12 months -6.2% over a 4-year horizon."},
           {"strategy": "growth", "evidence": ["t1"], "claim": "QQQ and SPY together make up 61.5% of the money."}]
    raw.insert(0, {"strategy": "growth", "evidence": ["t1"], "claim": "It holds 47.3% in one bet."})  # invented
    st = [o["status"] for o in critic.validate(raw, calls, strats, f)]
    assert "47.3%" in st[0] and st[1:] == ["valid"] * 3
    assert "25%" in critic.validate(raw[1:2], calls, strats)[0]["status"]   # without FACTS: as before, dropped


def test_correlation_rounded_onto_a_threshold_is_written_exactly():
    """0.948 written "0.95" reads like a breach of C6 (blocks at 0.95): code writes 0.948 back. 0.912 → 0.91 stays."""
    calls = _calls({"pairs": [{"a": "QQQ", "b": "SPY", "correlation": 0.948}, {"a": "A", "b": "B", "correlation": 0.912}],
                    "checks": [{"check": "C6", "value": 0.948, "limit": 0.95}]})  # the limit is in the results too
    raw = [{"strategy": "growth", "evidence": ["t1"], "claim": "QQQ and SPY correlate 0.95; A and B 0.91."}]
    o = critic.validate(raw, calls, [{"key": "growth"}])[0]
    assert o["status"] == "valid" and "0.948" in o["claim"] and "0.91." in o["claim"]


def test_levels_are_named_by_what_they_hold_not_by_risk():
    """A level with less in stocks is not always safer in the data (Robert: -9.5% vs -8.6%): no "prudent" label."""
    labels = [label for _, label, _ in portfolio.LEVELS]
    assert labels == ["most growth your limits allow", "less in stocks", "least in stocks"]
    assert not any("prudent" in x for x in labels)

def test_at_most_three_objections_and_tool_budget():
    calls = _calls({"x": 1})
    raw = [{"strategy": "g", "claim": "fine", "evidence": ["t1"]}] * 5
    v = critic.validate(raw, calls, [{"key": "g"}])
    assert sum(o["status"] == "valid" for o in v) == 3
    rec = critic.Recorder(budget=2)
    for _ in range(2):
        assert "call_id" in rec.call(lambda: {"ok": 1}, "f", {})
    assert "budget" in rec.call(lambda: {"ok": 1}, "f", {})["error"]


def _growth(profile, rets):
    lim = derive_limits(profile)
    ss = portfolio.propose(profile, lim, rets=rets, holdings={})
    return lim, ss, max(ss, key=lambda s: s["split"]["growth"])


def test_fixes_only_tighten_and_rerun_the_whole_calculation(rets):
    lim, _, s = _growth(MATEO, rets)
    new, note = portfolio.revise(s, {"type": "shift", "pct": 0.10}, MATEO, lim, rets=rets, holdings={})
    assert new is not None and "rerun" in note
    assert new["split"]["growth"] <= s["split"]["growth"] - 0.10 + 1e-9         # the split search found a new ceiling
    assert new["split_range"]["ceiling"] <= s["split_range"]["ceiling"] - 0.10 + 1e-9
    assert set(new["weights"]) <= set(s["weights"]) and new["stats"] != s["stats"]
    for bad in ({"type": "shift", "pct": 0.5}, {"type": "trim", "ticker": "XBB.TO", "to": 0.0},
                {"type": "merge", "a": "XIU.TO", "b": "ZST.TO"}, {"type": "buy", "ticker": "TSLA"}):
        assert portfolio.revise(s, bad, MATEO, lim, rets=rets, holdings={})[0] is None


def test_merge_changes_the_basket_and_recomputes(rets):
    lim, ss, _ = _growth(AMIRA, rets)
    s, a, b = next((s, a, b) for s in ss for a in s["baskets"]["growth"] for b in s["baskets"]["growth"]
                   if a < b and a in s["weights"] and b in s["weights"])  # two growth lines still held
    new, _ = portfolio.revise(s, {"type": "merge", "a": a, "b": b}, AMIRA, lim, rets=rets, holdings={})
    assert new is not None and not {a, b} <= set(new["weights"])
    assert any(x.startswith("Critic:") for x in new["adjustments"])


def _fake_agent(objection_for):
    def run_agent(f, rec, tools):
        t = {x.__name__: x for x in tools}
        r = rec.call(t["strategy_checks"], "strategy_checks", {"strategy": f["strategies"][0]["key"]})
        return [objection_for(f, r["call_id"])]
    return run_agent


def test_agent_fix_applied_and_rechecked_by_the_guardian(rets, monkeypatch):
    monkeypatch.setattr(critic, "_run_agent", _fake_agent(lambda f, cid: {
        "strategy": f["strategies"][0]["key"], "claim": "Too close to the limit.", "evidence": [cid],
        "action": {"type": "shift", "pct": 0.05}}))
    res = run(MATEO, holdings={}, rets=rets, critic=False)
    before = {s["key"]: s["split"]["growth"] for s in res["strategies"]}
    c = critic.add_to_trace(res, MATEO, provider="bedrock", rets=rets, holdings={})
    o = c["objections"][0]
    assert c["source"] == "bedrock" and o["status"].startswith("revised"), o
    s = next(x for x in res["strategies"] if x["key"] == o["strategy"])
    assert s["split"]["growth"] < before[o["strategy"]] and s["guardian"]["verdict"] != "fail"
    agents = [st["agent"] for st in res["trace"].steps]
    assert agents[-3:] == ["Critic", "Portfolio", "Guardian"]


def test_fix_that_fails_the_guardian_keeps_the_original(rets, monkeypatch):
    monkeypatch.setattr(critic, "_run_agent", _fake_agent(lambda f, cid: {
        "strategy": f["strategies"][0]["key"], "claim": "Shift.", "evidence": [cid], "action": {"type": "shift", "pct": 0.05}}))
    res = run(MATEO, holdings={}, rets=rets, critic=False)
    orig = [dict(s["weights"]) for s in res["strategies"]]
    monkeypatch.setattr(guardian, "check_strategy", lambda *a, **k: [{"rule": "G7", "status": "fail", "text": "", "detail": "x"}])
    o = critic.add_to_trace(res, MATEO, provider="bedrock", rets=rets, holdings={})["objections"][0]
    assert o["status"].startswith("kept, justified") and [s["weights"] for s in res["strategies"]] == orig
    assert "Shift." in res["strategies"][0]["cons"]


def test_agent_failure_falls_back_to_mock(rets, monkeypatch):
    def boom(*a):
        raise RuntimeError("expired token")
    monkeypatch.setattr(critic, "_run_agent", boom)
    res = run(AMIRA, holdings={}, rets=rets, critic=False)
    c = critic.add_to_trace(res, AMIRA, provider="bedrock", rets=rets, holdings={})
    assert c["source"] == "mock" and "expired token" in c["note"] and c["tool_calls"]


@pytest.mark.parametrize("p", [AMIRA, MATEO, ROBERT], ids=["amira", "mateo", "robert"])
def test_mock_critic_in_the_pipeline(p, rets):
    res = run(p, holdings={}, rets=rets)
    assert "Critic" in [st["agent"] for st in res["trace"].steps]
    c = res["critic"]
    assert len([o for o in c["objections"] if not o["status"].startswith("dropped")]) <= critic.MAX_OBJECTIONS
    assert all(not o["status"].startswith("dropped") for o in c["objections"]), c["objections"]  # mock is always backed
    lim = res["limits"]
    for s in res["strategies"]:
        assert s["guardian"]["verdict"] != "fail" and abs(s["stats"]["max_drawdown"]) <= lim["loss_limit"] + 1e-9
        assert sum(v for t, v in s["weights"].items() if t in DEFENSIVE) >= lim["min_defensive"] - 1e-9


def test_risk_contributions_tool_and_metric(rets):
    from dh.metrics import risk_contributions
    w = {"NVDA": 0.1, "XBB.TO": 0.6, "ZST.TO": 0.3}
    rc = risk_contributions(rets, w)
    assert abs(sum(rc["shares"].values()) - 1) < 1e-9 and rc["shares"]["NVDA"] > w["NVDA"]  # stock: more risk than money
    tools = {t.__name__: t for t in critic.make_tools([], {"company_caps": {}, "reasons": []}, {})}
    with critic._tool_returns(rets):
        out = tools["risk_contributions"](weights=w)
        top = max(out["holdings"], key=lambda h: h["ratio"])
        assert top["ticker"] == "NVDA" and top["ratio"] > 1 and out["ann_vol"] > 0
        assert "error" in tools["risk_contributions"](weights={"XSP": 1.0})
