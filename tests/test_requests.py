"""Blocks G (request side by side) and H (selection, pros/cons): offline, synthetic returns from test_portfolio."""
import pytest
from test_portfolio import fewer_scenarios, rets  # noqa: F401  (shared synthetic data and the fast-path fixture)

from dh.agents import guardian, pipeline
from dh.agents import requests as rq
from dh.agents.scenarios import AMIRA, MATEO, ROBERT

BASE = {"ZST.TO": 0.45, "XBB.TO": 0.40, "XIU.TO": 0.075, "SPY": 0.075}   # 15% growth, 85% defensive


def test_overlay_takes_room_from_growth_first():
    small = rq.overlay(BASE, {"TSLA": 0.10})                 # fits in the 15% growth part: bonds untouched
    assert small["ZST.TO"] == pytest.approx(0.45) and small["TSLA"] == pytest.approx(0.10)
    big = rq.overlay(BASE, {"TSLA": 0.25})                   # 25% > 15%: the rest comes out of the defensive part
    assert big["TSLA"] == pytest.approx(0.25) and "XIU.TO" not in big
    assert sum(big.values()) == pytest.approx(1) and sum(small.values()) == pytest.approx(1)


def test_overlay_growth_never_touches_the_defensive_part():
    w = rq.overlay_growth(BASE, {"TSLA": 0.03})
    assert w["ZST.TO"] == pytest.approx(0.45) and w["XBB.TO"] == pytest.approx(0.40)
    assert w["TSLA"] == pytest.approx(0.03) and sum(w.values()) == pytest.approx(1)
    capped = rq.overlay_growth(BASE, {"TSLA": 0.30})         # more than the growth room: capped at it
    assert capped["TSLA"] == pytest.approx(0.15)


def run(profile, rets):
    return pipeline.run(profile, rets=rets, holdings={})


def test_robert_tsla_side_by_side(rets):
    res = run(dict(ROBERT, requested_positions={"TSLA": 0.25}), rets)
    c = res["request_comparison"]
    asked, fits = c["as_asked"], c["fits"]
    assert asked["verdict"] == "fail" and {"C1", "G4", "G9"} <= {f["id"] for f in asked["fails"]}
    assert asked["real_weight"]["TSLA"] == pytest.approx(0.25)
    assert fits["verdict"] != "fail" and not fits["fails"]
    cap = res["limits"]["company_caps"]["TSLA"]
    assert fits["real_weight"]["TSLA"] == pytest.approx(cap, abs=1e-3)
    assert fits["growth"] <= res["limits"]["horizon_max_growth"] + 1e-3      # the horizon cap still holds
    assert "fits up to" in c["why"]["TSLA"] and "TSLA" in c["summary"]
    assert asked["drawdown_cad"] > fits["drawdown_cad"]


def test_excluded_or_unknown_requests(rets):
    c = run(dict(MATEO, requested_positions={"XOM": 0.10}), rets)["request_comparison"]
    assert "fits" not in c and {"F6", "G3"} <= {f["id"] for f in c["as_asked"]["fails"]}
    u = run(dict(ROBERT, requested_positions={"ZEQT": 0.10}), rets)["request_comparison"]
    assert u["not_assessable"] == ["ZEQT"] and "as_asked" not in u
    assert run(AMIRA, rets)["request_comparison"] is None


def test_pros_cons_only_quote_traceable_numbers(rets):
    res = run(dict(ROBERT, requested_positions={"TSLA": 0.25}), rets)
    for s in res["strategies"]:
        assert s["pros"] or s["cons"]
        known = guardian._known_numbers(s, res["limits"], ROBERT)
        for line in s["pros"] + s["cons"]:
            for m in guardian.PCT.findall(line):
                assert any(abs(abs(float(m)) - abs(k)) <= 0.5 for k in known), (m, line)


def test_selection_drops_a_cf_fail(rets, monkeypatch):
    real = rq.ck.run

    def one_fails(strategy, profile, limits, rets=None, holdings=None):
        out = real(strategy, profile, limits, rets=rets, holdings=holdings)
        if strategy["weights"].get("QQQ", 0) > 0:      # pretend every strategy holding QQQ breaks C3b
            out = [dict(c, status="fail") if c["check"] == "C3b" else c for c in out]
        return out

    monkeypatch.setattr("dh.agents.portfolio.ck.run", one_fails)
    res = run(AMIRA, rets)
    assert res["dropped"], "the fake C3b fail must drop at least one strategy"
    assert all("QQQ" not in s["weights"] for s in res["strategies"])
    assert all(any(c["check"] == "C3b" and c["status"] == "fail" for c in d["checks"]) for d in res["dropped"])


def test_g12_knows_the_side_by_side_numbers(rets):
    res = run(dict(ROBERT, requested_positions={"TSLA": 0.25}), rets)
    asked = res["request_comparison"]["as_asked"]
    known = guardian._known_numbers(res["strategies"][0], res["limits"], ROBERT)
    assert any(abs(abs(asked["max_drawdown"]) * 100 - abs(k)) < 0.5 for k in known)  # G12 compares magnitudes (signs: #34)


def test_request_for_a_stand_in_fund_is_measured_and_labelled(rets):
    """'10% in XSP' (no data of its own) is measured with SPY, and the comparison says so (#42)."""
    c = run(dict(ROBERT, requested_positions={"XSP": 0.10}), rets)["request_comparison"]
    assert c["request"] == {"SPY": 0.10} and not c["not_assessable"]
    assert c["stand_ins"] and "XSP.TO" in c["stand_ins"][0] and "stand-in" in c["summary"]
