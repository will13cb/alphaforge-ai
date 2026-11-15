"""Existing portfolio (branch portefeuille_existant): stand-ins, review, rebuild, Critic, Explainer, Analyst.
Offline, on synthetic returns."""
import numpy as np
import pandas as pd
import pytest
from test_portfolio import fewer_scenarios, rets  # noqa: F401  (shared synthetic data and the fast-path fixture)

from dh import standins
from dh.agents import analyst, existing, explainer, pipeline
from dh.agents.scenarios import ROBERT

HELD = {"tsla": 60_000, "XIU.TO ": 30_000, "xsp": 10_000, "ZEQT.TO": 5_000}   # messy on purpose; ZEQT has no stand-in


def test_clean_positions():
    p = existing.clean_positions({" spy": 100, "SPY": 50, "XBB.TO": 0, "BAD": "x", "xsp": 10}, {"SPY"})
    assert p == {"SPY": 150.0, "XSP.TO": 10.0}


def test_moves_add_up_to_the_same_total():
    m = existing.moves({"TSLA": 60.0, "XIU.TO": 40.0}, {"XIU.TO": 0.5, "XBB.TO": 0.5}, 100.0)
    assert sum(r["change_cad"] for r in m) == pytest.approx(0)
    assert {r["ticker"]: r["action"] for r in m} == {"TSLA": "remove", "XBB.TO": "add", "XIU.TO": "add"}


def test_stand_in_only_when_the_source_has_data():
    assert standins.stand_in("XSP.TO", {"SPY"})["hedged"] is True
    assert standins.stand_in("XSP.TO", {"QQQ"}) is None          # source missing: no stand-in
    assert standins.stand_in("SPY", {"SPY"}) is None             # has its own data: no stand-in
    assert standins.stand_in("ZEQT.TO", {"SPY"}) is None         # own mix of funds: never mapped


def test_hedge_removes_the_currency_move_and_adds_the_rate_gap():
    idx = pd.bdate_range("2022-01-03", periods=3)
    r_cad = pd.Series([0.0, 0.02, -0.01], idx)
    fx = pd.Series([0.0, 0.02, 0.0], idx)                         # USD up 2% on day 2: all of SPY's CAD gain
    gap = pd.Series([0.0, 0.001, 0.001], idx)
    hr, how = standins.hedged_returns(r_cad, fx, gap)
    assert hr.iloc[1] == pytest.approx(0.001) and hr.iloc[2] == pytest.approx((1 - 0.01) * 1.001 - 1)
    assert "rate gap" in how


def _fx(rets):
    rng = np.random.default_rng(3)
    return pd.Series(rng.normal(0, 0.004, len(rets)), rets.index)


def test_review_measures_xsp_with_a_hedged_spy(rets):
    lim = pipeline.run(ROBERT, rets=rets, holdings={}, critic=False)
    p = dict(ROBERT, existing_positions={"XSP.TO": 10_000, "SPY": 10_000})
    r = existing.review(p, lim["limits"], lim["strategies"], rets=rets, holdings={}, fx_rets=_fx(rets),
                        gap=pd.Series(0.0, rets.index))
    si = r["stand_ins"][0]
    assert si["ticker"] == "XSP.TO" and si["measured_with"] == "SPY" and "hedge_effect" in si
    assert r["held_as"] == {"SPY": ["XSP.TO", "SPY"]} and r["current"]["weights"] == {"SPY": 1.0}
    assert any("same index" in line for line in r["critique"])   # XSP + SPY = one bet held twice
    assert not r["not_assessable"]


def test_robert_existing_portfolio_reviewed_and_rebuilt(rets):
    res = pipeline.run(dict(ROBERT, existing_positions=HELD), rets=rets, holdings={})
    r = res["existing_review"]
    assert r["not_assessable"] == ["ZEQT.TO"]
    assert [s["ticker"] for s in r["stand_ins"]] == ["XSP.TO"]
    assert r["assessed_cad"] == pytest.approx(100_000)
    assert r["current"]["verdict"] == "fail"                      # 60% in one stock for a 4-year horizon
    assert any("TSLA" in line for line in r["critique"])
    assert r["target"]["verdict"] != "fail" and r["target"]["name"] == res["strategies"][0]["name"]
    assert res["limits"]["existing_review"]["current"]["max_drawdown"] == r["current"]["max_drawdown"]
    assert "checks" not in res["limits"]["existing_review"]["current"]      # public view only
    assert "Critic" in [s["agent"] for s in res["trace"].steps]
    assert all(o["action"]["type"] == "disclose" for o in r["critic"]["objections"])
    assert res["strategies"]                                      # the proposals are untouched


def test_no_existing_portfolio_changes_nothing(rets):
    res = pipeline.run(ROBERT, rets=rets, holdings={})
    assert "existing_review" not in res and "existing_review" not in res["limits"]


def test_only_unknown_tickers(rets):
    res = pipeline.run(dict(ROBERT, existing_positions={"ZEQT.TO": 5_000}), rets=rets, holdings={})
    r = res["existing_review"]
    assert r["not_assessable"] == ["ZEQT.TO"] and "current" not in r


def test_explainer_quotes_the_review_and_passes_g12(rets):
    profile = dict(ROBERT, existing_positions=HELD)
    res = pipeline.run(profile, rets=rets, holdings={})
    e = explainer.add_to_trace(res, profile, provider="mock")
    assert "portfolio you already have" in e["text"].lower()
    assert "XSP.TO" in e["text"]
    assert all(c["status"] != "fail" for c in e["checks"])


def test_analyst_answers_about_the_existing_portfolio(rets):
    profile = dict(ROBERT, existing_positions=HELD)
    res = pipeline.run(profile, rets=rets, holdings={})
    a = analyst.ask("What do you think of my current portfolio?", res, profile, provider="mock", rets=rets, holdings={})
    assert a["status"] == "valid" and any(c["tool"] == "existing_portfolio" for c in a["tool_calls"])
    b = analyst.ask("What if I add 10,000 $ of XSP to my current portfolio?", res, profile, provider="mock",
                    rets=rets, holdings={})
    assert b["status"] == "valid" and any(c["tool"] == "what_if_existing" for c in b["tool_calls"])


def test_results_page_shows_the_review(rets):
    """The results page draws the review (today vs rebuilt, critique, moves) without an exception."""
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    profile = dict(ROBERT, existing_positions=HELD)
    res = pipeline.run(profile, rets=rets, holdings={})
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "interface" / "app.py"), default_timeout=120).run()
    at.session_state.res, at.session_state.profile, at.session_state.section = res, profile, "Your results"
    at.run()
    assert not at.exception
    assert "The portfolio you already have" in [h.value for h in at.subheader]


def test_example_portfolio_uses_only_holdings_we_have_data_for():
    from dh.agents.rules import UNIVERSE
    from interface.views.holdings_input import EXAMPLE
    assert set(EXAMPLE) <= UNIVERSE and "ZEQT.TO" not in EXAMPLE


def test_free_text_reads_holdings_already_owned():
    from dh.agents import extractor
    ex = extractor.extract("I'm 59, retiring in 4 years. I have 10k in XIU and 20,000 $ in XSP. Put 25% in Tesla.",
                           provider="mock")
    assert ex["profile"]["existing_positions"] == {"XIU.TO": 10_000, "XSP.TO": 20_000}
    assert ex["profile"]["requested_positions"] == {"TSLA": 0.25} and "capital" not in ex["profile"]
    fr = extractor.existing_from_text("J'ai 10 000 $ dans XSP et 5 k$ dans RY.")
    assert fr == {"XSP.TO": 10_000, "RY.TO": 5_000}


def test_fees_and_look_through_in_the_review(rets):
    res = pipeline.run(dict(ROBERT, existing_positions={"XIU.TO": 50_000, "XSP.TO": 50_000}), rets=rets, holdings={})
    r = res["existing_review"]
    assert set(r["fees"]["today"]["by_ticker"]) == {"XIU.TO", "XSP.TO"}             # XSP's own fee, not SPY's
    assert r["fees"]["today"]["total_cad"] > 0 and "rebuilt" in r["fees"]
    assert r["look_through"]["not_opened"] == ["SPY", "XIU.TO"]                       # holdings={} in the test
    assert any("not opened" in line for line in r["critique"])
