"""Regression checks for issues exposed by the release integration review."""
import json

import pytest

from dh.agents import analyst, checks, critic, grounding
from dh.agents.scenarios import ROBERT
from dh.agents.trace import Trace
from dh import tracestore
from interface.core import services


@pytest.fixture
def cited_stats():
    return [{"call_id": "t1", "tool": "asset_facts", "args": {"tickers": ["TSLA"]},
             "result": {"ticker": "TSLA", "max_drawdown": -.2, "ann_vol": .3}}]


@pytest.mark.parametrize("text", ["TSLA gained 20%.", "TSLA had a maximum drawdown of 30%.",
                                  "TSLA had volatility of 20%.", "TSLA had maximum drawdown +20%."])
def test_metric_and_direction_cannot_be_swapped(text, cited_stats):
    status = analyst.validate({"answer": text, "evidence": ["t1"]}, cited_stats, {"tsla": "TSLA"})[0]
    assert status.startswith("replaced: metric mismatch")
    objection = {"strategy": "core", "claim": text, "evidence": ["t1"]}
    assert critic.validate([objection], cited_stats, [{"key": "core"}])[0]["status"].startswith("dropped: metric mismatch")


@pytest.mark.parametrize("text", ["TSLA had maximum drawdown -20%.", "TSLA's worst drop was 20%.",
                                  "TSLA had volatility of 30%."])
def test_valid_metric_claims_survive(text, cited_stats):
    assert analyst.validate({"answer": text, "evidence": ["t1"]}, cited_stats, {"tsla": "TSLA"})[0] == "valid"


def test_gain_requires_positive_return_evidence():
    assert not grounding.problems("TSLA gained 20%.", [{"ann_return": .2}])
    assert grounding.problems("TSLA gained 20%.", [{"ann_return": -.2, "ann_vol": .2}])
    assert not grounding.problems("Volatilité de 30,0 %.", [{"ann_vol": .3}])


def test_unknown_equity_etf_does_not_get_a_verified_holding_count():
    row = checks.c5_concentration({"QQQ": 1}, {})
    assert row["status"] == "warn" and row["value"] is None
    assert "QQQ" in row["reason"] and "not fully assessed" in row["reason"]


def test_missing_chart_data_never_terminates_the_page(monkeypatch):
    from dh.agents import market_charts
    def missing(*a, **kw):
        raise SystemExit("prices missing")
    monkeypatch.setattr(market_charts, "growth_data", missing)
    assert services.charts({"strategies": []}) == {}


def test_followup_evidence_is_saved_and_linked_to_original_run(monkeypatch, tmp_path):
    monkeypatch.setattr(tracestore, "LOCAL_DIR", tmp_path)
    tr = Trace()
    tr.step("Profiler", "Portfolio", "limits derived")
    res = {"strategies": [{"name": "Broad core"}], "trace": tr, "limits": {}, "verdict": "pass"}
    first = tracestore.save_run(res, ROBERT, bucket="")
    answer = {"answer": "A fixed explanation", "status": "valid", "source": "mock", "tool_calls": [], "evidence": []}
    monkeypatch.setattr(analyst, "ask", lambda *a, **kw: answer)
    services.ask_analyst("Explain my results", res, ROBERT)
    saved = next(json.loads(p.read_text()) for p in tmp_path.rglob("*.json") if first["run_id"] not in p.name)
    assert saved["parent_run_id"] == first["run_id"]
    assert saved["followups"][0]["answer"] == answer["answer"]
    assert saved["trace"][-1]["agent"] == "Analyst"
    assert "tool_calls" in saved["trace"][-1]["output"]


def test_critic_cannot_accept_a_revision_with_a_blocking_portfolio_check(monkeypatch):
    from dh.agents import guardian, portfolio
    original = {"key": "core", "name": "Original", "weights": {"SPY": .2, "XBB.TO": .8},
                "split": {"growth": .2}, "stats": {"max_drawdown": -.05}}
    revised = {**original, "weights": {"SPY": .1, "XBB.TO": .9},
               "checks": [{"check": "C4", "status": "fail", "reason": "insufficient asset classes"}]}
    res = {"strategies": [original], "limits": {"loss_limit": .15}, "trace": Trace()}
    monkeypatch.setattr(critic, "review", lambda *a, **kw: {
        "objections": [{"id": "K1", "strategy": "core", "claim": "Shift.", "status": "valid",
                        "action": {"type": "shift", "pct": .1}}],
        "tool_calls": [], "source": "mock", "note": ""})
    monkeypatch.setattr(portfolio, "revise", lambda *a, **kw: (revised, "recomputed"))
    monkeypatch.setattr(guardian, "check_strategy", lambda *a, **kw: [{"rule": "G7", "status": "pass"}])
    result = critic.add_to_trace(res, ROBERT, holdings={})
    assert res["strategies"][0] is original
    assert "C4" in result["objections"][0]["status"]
