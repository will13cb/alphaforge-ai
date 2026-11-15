"""Market data agent on synthetic returns (no starter CSVs needed)."""
import json

import numpy as np
import pandas as pd
import pytest

from dh import metrics
from dh.agents import guardian, market
from dh.agents.profiler import derive_limits
from dh.agents.scenarios import SCENARIOS


@pytest.fixture
def rets():
    idx = pd.bdate_range("2021-11-15", "2026-11-12")
    rng = np.random.default_rng(0)
    base = rng.normal(0.0004, 0.01, len(idx))
    return pd.DataFrame({
        "STOCK": base + rng.normal(0, 0.005, len(idx)),
        "TWIN": base + rng.normal(0, 0.005, len(idx)),   # highly correlated with STOCK
        "BOND": rng.normal(0.0001, 0.003, len(idx)),
    }, index=idx)


def test_summary_uses_dh_metrics(rets):
    s = market.asset_summary(rets=rets)
    assert list(s.index) == ["STOCK", "TWIN", "BOND"]
    assert s.loc["BOND", "ann_vol"] == pytest.approx(metrics.ann_vol(rets["BOND"]))
    assert s.loc["STOCK", "max_drawdown"] == pytest.approx(metrics.max_drawdown(rets["STOCK"]))
    assert s.loc["BOND", "ann_vol"] < s.loc["STOCK", "ann_vol"]
    assert s.loc["STOCK", "cvar_95"] > 0                     # a loss, reported as a positive number
    r22 = rets.loc["2022", "STOCK"]
    assert s.loc["STOCK", "return_2022"] == pytest.approx((1 + r22).prod() - 1)


def test_strategy_stats_match_portfolio(rets):
    w = {"STOCK": 0.4, "BOND": 0.6}
    st = market.strategy_stats(w, rets=rets)
    port = metrics.portfolio_returns(rets, w)
    assert st["max_drawdown"] == pytest.approx(metrics.max_drawdown(port))
    assert st["ann_vol"] < market.strategy_stats({"STOCK": 1.0}, rets=rets)["ann_vol"]


def test_stats_plug_into_guardian(rets):
    """strategy_stats output is the format Guardian G7/G8 read."""
    sc = next(s for s in SCENARIOS if s.get("strategy"))
    limits = derive_limits(sc["profile"])
    strat = dict(sc["strategy"], stats=market.strategy_stats({"STOCK": 0.4, "BOND": 0.6}, rets=rets))
    rules = {c["rule"] for c in guardian.check_strategy(strat, limits, sc["profile"], holdings={})}
    assert {"G7", "G8"} <= rules


def test_correlations_flag_twins(rets):
    c = market.correlations(rets=rets)
    top = c["top_pairs"][0]
    assert {top["a"], top["b"]} == {"STOCK", "TWIN"} and top["correlation"] > 0.7
    assert c["pearson"]["STOCK"]["STOCK"] == 1.0 and c["pearson"]["STOCK"]["TWIN"] > 0.7   # {ticker: {ticker: corr}}


def test_market_facts_json_and_describe(rets):
    facts = market.market_facts(rets=rets, include_macro=False)
    json.dumps(facts)                                        # goes into the trace store as is
    assert {a["ticker"] for a in facts["assets"]} == {"STOCK", "TWIN", "BOND"}
    assert facts["sources"] and facts["assumptions"] and facts["limits"]
    assert all(q["usable"] for q in facts["quality"].values())
    assert "STOCK/TWIN" in market.describe(facts) or "TWIN/STOCK" in market.describe(facts)


def test_quality_alerts_in_english(rets):
    frozen = rets.copy()
    frozen.iloc[100:110, 0] = 0.0                            # 10 days of a frozen price
    alerts = market.data_quality(rets=frozen)["STOCK"]["alerts"]
    assert any("consecutive zero returns" in a for a in alerts)


def test_tool_catalog():
    assert {"cvar_historic", "efficient_frontier", "goal_probability"} <= set(market.tools()["nom"])


def test_annualisation_uses_observed_rows_per_year():
    """Decision #12: 5 years on the weekday calendar (~261 rows/yr) at 10%/yr must give 10%, not ~9.6%."""
    import numpy as np
    import pandas as pd
    from dh import metrics

    idx = pd.bdate_range("2021-11-12", "2026-11-12")
    years = (idx[-1] - idx[0]).days / 365.25
    daily = 1.10 ** (years / (len(idx) - 1)) - 1
    r = pd.Series(daily, index=idx)
    assert metrics.periods_per_year(r) == pytest.approx(261, abs=1)
    assert metrics.ann_return(r) == pytest.approx(0.10, abs=1e-4)
    assert metrics.ann_return(r, periods=252) < 0.097  # the old fixed-252 bias
    assert metrics.periods_per_year(np.array([0.01, 0.02])) == metrics.TRADING_DAYS  # no dates: fallback


def test_goal_outlook_deterministic_and_risk_only_more_prudent(rets):
    kw = dict(capital=100_000, horizon_years=3, monthly_contribution=500, target_amount=120_000, n_scenarios=300, rets=rets)
    a = market.goal_outlook({"STOCK": 0.6, "BOND": 0.4}, **kw)
    assert a == market.goal_outlook({"STOCK": 0.6, "BOND": 0.4}, **kw)  # fixed seed: same inputs, same numbers
    assert a["total_invested"] == pytest.approx(100_000 + 500 * 36, rel=0.03)
    for k in ("replay", "risk_only"):
        o = a[k]
        assert 0 <= o["prob_loss"] <= 1 and 0 <= o["prob_target"] <= 1
        assert o["final_p5"] <= o["final_p50"] <= o["final_p95"]
    # no ZST.TO in synthetic data: risk_only uses 0% drift, so it is more prudent than the positive-drift replay
    assert a["risk_only"]["final_p50"] < a["replay"]["final_p50"]
    assert market.goal_outlook({"BOND": 1.0}, capital=1000, horizon_years=1, rets=rets, n_scenarios=100)["replay"]["prob_target"] is None


def test_agent_tools_json_and_errors(rets, monkeypatch):
    """Decision #14: tools the Strands agents call return compact JSON and readable errors, never raise."""
    monkeypatch.setattr(market, "_TOOL_RETS", rets)
    unknown = market.portfolio_stats({"XSP": 0.5, "STOCK": 0.5})
    assert "XSP" in unknown["error"] and "STOCK" in unknown["available"]
    assert "error" in market.portfolio_stats({"STOCK": -1.0, "BOND": 2.0})
    assert "error" in market.stress_test({"STOCK": 1.0}, "2023-01-01", "2022-01-01")
    assert "error" in market.correlation_between(["STOCK"])
    ps = market.portfolio_stats({"STOCK": 3, "BOND": 2})
    assert ps["weights"] == {"STOCK": 0.6, "BOND": 0.4}
    assert ps["max_drawdown"] == round(market.strategy_stats({"STOCK": 0.6, "BOND": 0.4}, rets=rets)["max_drawdown"], 4)
    assert market.correlation_between(["STOCK", "TWIN", "BOND"])["pairs"][0]["a"] in {"STOCK", "TWIN"}
    st = market.stress_test({"STOCK": 1.0})
    assert st["deepest_drop"] <= 0
    g = market.goal_check({"STOCK": 0.5, "BOND": 0.5}, capital=10_000, horizon_years=2, target_amount=11_000)
    assert 0 <= g["risk_only"]["prob_loss"] <= 1
    for f in market.AGENT_TOOLS:
        assert f.__doc__ and "Returns:" in f.__doc__
    json.dumps([ps, st, g, unknown])


def test_chart_data_matches_trace_numbers(rets):
    """Decision #16: chart data comes from the same functions as the trace, and every chart builds."""
    from dh.agents import market_charts as mc
    strategies = {"A": {"STOCK": 0.6, "BOND": 0.4}, "B": {"BOND": 1.0}}
    g = mc.growth_data(strategies, rets=rets)
    a = g[g.strategy == "A"]
    assert a["drawdown"].min() == pytest.approx(market.strategy_stats(strategies["A"], rets=rets)["max_drawdown"])
    o = mc.outcome_data(strategies["A"], capital=10_000, horizon_years=2, target_amount=11_000, rets=rets)
    ref = market.goal_outlook(strategies["A"], capital=10_000, horizon_years=2, target_amount=11_000, rets=rets)
    assert o.set_index("key").loc["risk_only", "p50"] == ref["risk_only"]["final_p50"]
    c = mc.correlation_data(rets=rets)
    assert len(c) == 9 and c["correlation"].between(-1, 1.0000001).all()
    rr = mc.risk_return_data(strategies, rets=rets, frontier_points=5)
    assert set(rr.kind) == {"asset", "frontier", "strategy"}
    y = mc.year_2022_data(rets=rets)
    assert y["return_2022"].is_monotonic_increasing
    for chart in (mc.growth_chart(g), mc.outcome_chart(o), mc.correlation_chart(c), mc.risk_return_chart(rr),
                  mc.year_2022_chart(y, highlight=["STOCK"])):
        assert chart.to_dict()  # valid Vega-Lite spec


def test_country_of_listing():
    """C2 geography input: from the exchange, or from the ticker when the CSVs are absent."""
    assert market.country_of("XIU.TO") == "Canada"
    assert market.country_of("SPY", "NYSE Arca") == "United States"
    assert market.country_of("BTC-USD") == "Global (crypto)"
    assert market.country_of("AAPL", "TSX") == "Canada"   # exchange wins over the ticker rule
    c = market.countries(["RY.TO", "QQQ", "ETH-USD"])
    assert c == {"RY.TO": "Canada", "QQQ": "United States", "ETH-USD": "Global (crypto)"}


def test_fast_frame_validation_same_result_and_errors():
    """goal_outlook speed-up: float tables are validated in one pass, same output, same errors."""
    from dh import quant_toolkit as qt
    rng = np.random.default_rng(3)
    a = pd.DataFrame(rng.normal(0, 0.01, (50, 40)))
    mixed = a.astype(object)  # forces the column-by-column path
    pd.testing.assert_frame_equal(qt._as_frame(a), qt._as_frame(mixed).astype(float))
    for bad in (pd.DataFrame({"x": [0.01, -1.5, 0.02]}), pd.DataFrame({"x": [5.0, 3.0, 2.0, 0.01]})):
        with pytest.raises(ValueError, match="returns\\['x'\\]"):
            qt._as_frame(bad, min_obs=1)


def test_required_return(rets):
    """Asked by Will (#17): the yearly return a goal needs, a pure calculation (no data needed for the rate itself)."""
    import json
    r = market.required_return(400_000, 4, 450_000, rets=rets.assign(**{"ZST.TO": 0.0001}))
    assert r["required"] == pytest.approx((450 / 400) ** 0.25 - 1, abs=1e-4)          # no contributions: closed form
    w = market.required_return(20_000, 15, 200_000, monthly_contribution=500, rets=rets.assign(**{"ZST.TO": 0.0001}))
    fv = market._future_value(w["required"], 20_000, 500, 180)
    assert fv == pytest.approx(200_000, rel=1e-3) and w["total_invested"] == 20_000 + 500 * 180
    low = market.required_return(10_000, 5, 9_000, rets=rets.assign(**{"ZST.TO": 0.0001}))
    assert low["required"] <= 0 and "without any return" in low["reading"]
    assert market.required_return(1_000, 2, 10_000_000)["required"] is None
    assert "error" in market.required_return(1_000, 0.1, 2_000) and "error" in market.required_return(1_000, 5, None)
    assert market.required_return in market.AGENT_TOOLS
    json.dumps(r)
