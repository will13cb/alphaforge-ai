"""Holdings are visible on comparison cards without opening the evidence tab."""
from streamlit.testing.v1 import AppTest


def test_strategy_cards_show_all_weights_and_cad_budget_amounts():
    app = AppTest.from_string("""
from interface.views.results import card
card(dict(name="Broad core", split=dict(growth=.15, defensive=.85), stats={},
          weights={"SPY": .075, "XIU.TO": .075, "XBB.TO": .425, "ZST.TO": .425}),
     1, 2, capital=400000)
card(dict(name="Income", split=dict(growth=.05, defensive=.95), stats={},
          weights={"XBB.TO": .95, "RY.TO": .05}), 2, 2, capital=400000)
""").run()
    assert not app.exception
    assert len(app.table) == 2
    first, second = [table.value for table in app.table]
    assert list(first.index) == ["Canadian bond fund (XBB.TO)", "Short-term bond fund (ZST.TO)", "U.S. stock fund (SPY)", "Canadian stock fund (XIU.TO)", "Total"]
    assert first.loc["Canadian bond fund (XBB.TO)", "Share"] == "42.5%"
    assert first.loc["U.S. stock fund (SPY)", "Amount (CAD)"] == "30,000 $"
    assert first.loc["Total", "Share"] == "100.0%"
    assert first.loc["Total", "Amount (CAD)"] == "400,000 $"
    assert second.loc["RY.TO", "Share"] == "5.0%"
    assert second.loc["RY.TO", "Amount (CAD)"] == "20,000 $"
    assert not app.expander  # allocations are always visible


def test_weights_remain_visible_without_a_budget():
    app = AppTest.from_string("""
from interface.views.results import card
card(dict(name="Bond mix", split=dict(growth=0, defensive=1), stats={},
          weights={"XBB.TO": 1}), 1, 1)
""").run()
    assert not app.exception
    assert app.table[0].value.loc["Canadian bond fund (XBB.TO)", "Share"] == "100.0%"
    assert "Amount (CAD)" not in app.table[0].value.columns


def test_card_uses_plain_labels_and_keeps_internal_rule_prose_out():
    app = AppTest.from_string("""
from interface.views.results import card
card(dict(name="Broad core: most growth your limits allow", split=dict(growth=.15, defensive=.85),
          stats={}, weights={"RY.TO": 1}, pros=["Example benefit"],
          split_range=dict(set_by="horizon", set_by_text="decision #22 technical rule", data_ceiling=.35)),
     1, 2, capital=1000, names={"RY.TO": "Royal Bank of Canada"})
""").run()
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "How your money is split" in text
    assert "decision #22" not in text and "loss test alone" not in text
    assert app.table[0].value.index[0] == "Royal Bank of Canada (RY.TO)"
    assert app.expander[0].label == "Benefits and things to know"


def test_detailed_model_checks_are_inside_explicit_technical_expander():
    app = AppTest.from_string("""
from interface.views import results
from interface.core import services
from dh.agents.trace import Trace
services.charts = lambda res: {}
services.loaded_universe = lambda: __import__('pandas').DataFrame({"ticker":["RY.TO"], "name":["Royal Bank of Canada"]})
results.S.profile = {"capital": 400000}
results.details({"strategies":[dict(key="core", name="Broad core", weights={"RY.TO":1},
    checks=[dict(check="C1", status="pass", reason="Internal company cap check")])], "trace": Trace()})
""").run()
    assert not app.exception
    technical = next(e for e in app.expander if e.label == "How this option was calculated (technical)")
    assert any("C1" in m.value for m in technical.markdown)
    assert app.table[0].value.loc["Royal Bank of Canada (RY.TO)", "Amount (CAD)"] == "400,000 $"
