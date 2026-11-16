"""Analyst (app follow-ups): offline, deterministic analyst + the code-enforced checks on a model's answer."""
import json

import pytest
from test_portfolio import fewer_scenarios, rets  # noqa: F401  (shared synthetic data and the fast-path fixture)

from dh.agents import analyst, critic, pipeline
from dh.agents.scenarios import AMIRA, ROBERT
from dh.personas import DISCLAIMER


@pytest.fixture(autouse=True)
def _isolated_caches(tmp_path, monkeypatch):
    """Tests never read or write the real demo/local caches."""
    monkeypatch.setattr(analyst, "DEMO_CACHE", tmp_path / "demo")
    monkeypatch.setattr(analyst, "LOCAL_CACHE", tmp_path / "local")


@pytest.fixture(scope="module")
def robert_run(rets):
    return pipeline.run(ROBERT, rets=rets, holdings={}, critic=False)


def ask(q, res, profile, rets):
    return analyst.ask(q, res, profile, provider="mock", rets=rets, holdings={})


def test_position_what_if_reruns_the_pipeline(robert_run, rets):
    a = ask("What if I put 25% in TSLA?", robert_run, ROBERT, rets)
    assert a["status"] == "valid" and a["source"] == "mock"
    assert [c["tool"] for c in a["tool_calls"]] == ["what_if_position"]
    r = a["tool_calls"][0]["result"]
    assert r["as_asked"]["verdict"] == "fail" and "G9" in r["as_asked"]["fails"]
    assert "25% in TSLA" in a["answer"] and a["answer"].endswith(DISCLAIMER)
    json.dumps(a, default=str)


def test_unknown_asset_and_unclear_question(robert_run, rets):
    assert "no data for ZEQT" in ask("What if I add 10% ZEQT?", robert_run, ROBERT, rets)["answer"]   # no stand-in (#42)
    help_ = ask("Is gold nice?", robert_run, ROBERT, rets)
    assert help_["status"] == "valid" and not help_["tool_calls"]


def test_profile_what_if(robert_run, rets):
    a = ask("What if my horizon were 10 years?", robert_run, ROBERT, rets)
    r = a["tool_calls"][0]["result"]
    assert a["status"] == "valid" and r["field"] == "horizon_years"
    assert r["after"]["defensive_floor"] < r["before"]["defensive_floor"]     # longer horizon → more room for stocks
    assert ask("Why so few stocks?", robert_run, ROBERT, rets)["tool_calls"][0]["tool"] == "limit_reason"


def test_code_enforces_the_answer():
    calls = [{"call_id": "t1", "tool": "what_if_position", "args": {}, "result": {"max_drawdown": -0.137, "drawdown_cad": 54731}}]
    assert analyst.validate({"answer": "Worst drop -13.7%, about 54,731 $.", "evidence": ["t1"]}, calls)[0] == "valid"
    assert analyst.validate({"answer": "Worst drop -19%.", "evidence": ["t1"]}, calls)[0].startswith("replaced: unbacked")
    assert analyst.validate({"answer": "Worst drop -13.7%.", "evidence": ["t9"]}, calls)[0].startswith("replaced: cites")
    assert analyst.validate({"answer": "It will return a lot.", "evidence": ["t1"]}, calls)[0] == "replaced: advice or forecast wording"


def test_bad_model_answer_is_replaced_and_said(robert_run, rets, monkeypatch):
    monkeypatch.setattr(analyst, "_run_agent", lambda q, f, rec, tools, history=None: {"answer": "TSLA gives 42% a year.", "evidence": []})
    a = analyst.ask("What if I put 25% in TSLA?", robert_run, ROBERT, provider="bedrock", rets=rets, holdings={})
    assert a["status"] == "valid" and a["source"].startswith("mock (bedrock answer replaced")
    assert "42%" not in a["answer"] and "unbacked" in a["note"]
    assert not list((analyst.LOCAL_CACHE).glob("*.json"))                     # an invalid answer is never cached


def test_trace_and_budget(rets):
    res = pipeline.run(AMIRA, rets=rets, holdings={}, critic=False)
    n = len(res["trace"].steps)
    analyst.add_to_trace(res, AMIRA, "What if I put 30% in NVDA?", provider="mock", rets=rets, holdings={})
    assert len(res["trace"].steps) == n + 2 and res["followups"][0]["question"].startswith("What if")
    rec = critic.Recorder(1)
    rec.call(lambda: {"x": 1}, "a", {})
    assert "budget" in rec.call(lambda: {"x": 2}, "b", {})["error"]


# ---- improvements: names, several requests, more questions, French, stricter checks ----------------------------

def test_names_several_positions_and_language():
    p = analyst.parse
    assert p("What if I put 10% in Tesla?", ROBERT)["positions"] == {"TSLA": 0.10}
    assert p("Et si je mettais 5 % dans la Banque Royale et 5 % en bitcoin ?", ROBERT)["positions"] == {"RY.TO": 0.05, "BTC-USD": 0.05}
    both = p("Et si je mettais 10 % dans NVDA et que mon horizon était de 8 ans ?", ROBERT)
    assert both["positions"] == {"NVDA": 0.10} and both["changes"] == {"horizon_years": 8.0} and both["lang"] == "fr"
    assert p("What if I could lose 25%?", ROBERT)["positions"] == {}                     # a loss % is not a position
    assert p("Quel rendement me faut-il pour avoir 450 000 $ ?", ROBERT)["target"] == 450_000
    assert p("Et si je versais 500 $ par mois ?", ROBERT)["changes"] == {"monthly_contribution": 500}


def test_combined_question_is_checked_together(robert_run, rets):
    a = ask("Et si je mettais 10 % dans NVDA et que mon horizon était de 8 ans ?", robert_run, ROBERT, rets)
    assert [c["tool"] for c in a["tool_calls"]] == ["what_if_profile", "what_if_position"]
    assert a["tool_calls"][1]["args"]["profile_changes"] == {"horizon_years": 8.0}
    assert a["status"] == "valid" and "Simulation seulement" in a["answer"] and "horizon de 8 ans" in a["answer"]


@pytest.mark.parametrize("q, tool", [("Quel rendement me faut-il pour avoir 450 000 $ ?", "required_return"),
                                     ("How risky is Shopify?", "asset_facts"),
                                     ("SPY et QQQ, c'est le même pari ?", "correlation_between"),
                                     ("How would my strategy have done in 2022?", "stress_test"),
                                     ("Should I buy Tesla?", "asset_facts")])
def test_more_question_types(robert_run, rets, q, tool):
    a = ask(q, robert_run, ROBERT, rets)
    assert a["status"] == "valid" and [c["tool"] for c in a["tool_calls"]] == [tool], a["note"]
    if "buy" in q:
        assert "don't say buy or sell" in a["answer"]


def test_advice_filter_in_both_languages():
    calls = [{"call_id": "t1", "tool": "asset_facts", "args": {}, "result": {"x": 1}}]
    for text in ("Vous devriez acheter NVDA.", "Achetez maintenant.", "Ça va rapporter gros.", "You should buy NVDA.",
                 "It will go up.", "Rendement garanti."):
        assert analyst.validate({"answer": text, "evidence": ["t1"]}, calls)[0] == "replaced: advice or forecast wording", text


def test_counts_years_attribution_and_french_numbers():
    res_ = {"fails": ["C1", "D1", "D2", "F2", "G4", "G6", "G7", "G9", "G17"], "max_drawdown": -0.265, "drawdown_cad": 106121,
            "start": "2022-01-03", "strategies": [{"key": "core", "growth": 0.15}, {"key": "income", "growth": 0.46}]}
    calls = [{"call_id": "t1", "tool": "what_if_position", "args": {"ticker": "TSLA", "weight": 0.25}, "result": res_}]
    v = lambda t: analyst.validate({"answer": t, "evidence": ["t1"]}, calls)[0]  # noqa: E731
    assert v("9 rules would fail.") == "valid"
    assert v("2 rules would fail.").startswith("replaced: count")
    assert v("In 2022 it fell 26.5%.") == "valid"
    assert v("In 1999 it fell 26.5%.").startswith("replaced: year")   # before any data window (2010 or 2021 start)
    assert v("La pire baisse aurait été de -26,5 %, soit 106 121 $.") == "valid"          # French formats
    assert v("Broad core: 15% in stocks.") == "valid"
    assert v("Broad core: 46% in stocks.").startswith("replaced: number(s) attributed")    # 46% is the income one


def test_conversation_context_and_new_abilities(robert_run, rets):
    """Follow-ups reuse what the client asked before; concepts come from the glossary; results from the run."""
    hist = []

    def turn(q):
        a = analyst.ask(q, robert_run, ROBERT, provider="mock", rets=rets, holdings={}, history=list(hist))
        hist.append({"question": q, "answer": a["answer"]})
        return a

    turn("What if I put 10% in Tesla?")
    a = turn("and with 5%?")
    assert a["status"] == "valid" and a["tool_calls"][0]["args"] == {"ticker": "TSLA", "weight": 0.05}
    a = turn("what about NVDA?")
    assert a["tool_calls"][0]["args"] == {"ticker": "NVDA", "weight": 0.05}
    a = turn("and with a 10-year horizon?")
    assert {c["tool"] for c in a["tool_calls"]} & {"what_if_position", "what_if_profile"}
    a = analyst.ask("What is volatility?", robert_run, ROBERT, provider="mock", rets=rets, holdings={})
    assert a["status"] == "valid" and not a["tool_calls"] and "up and down" in a["answer"]
    a = analyst.ask("Explain my results", robert_run, ROBERT, provider="mock", rets=rets, holdings={})
    assert a["status"] == "valid" and a["tool_calls"][0]["tool"] == "results_overview" and "|" in a["answer"]
    a = analyst.ask("blablabla", robert_run, ROBERT, provider="mock", rets=rets, holdings={})
    assert "not sure I understood" in a["answer"]


def test_text_not_phrased_as_a_question_is_answered_about_what_it_names(robert_run, rets, monkeypatch):
    """"Growth tilt", "volatility" or "Tesla" typed alone is a question about that subject, in the app's language;
    only a text that names nothing we know gets "not sure I understood"."""
    from dh import i18n
    ask = lambda q: analyst.ask(q, robert_run, ROBERT, provider="mock", rets=rets, holdings={})
    name = robert_run["strategies"][0]["name"]
    a = ask(name)
    assert a["status"] == "valid" and a["tool_calls"][0]["tool"] == "results_overview"
    assert "not sure I understood" not in a["answer"] and name in a["answer"] and "Your loss limit" in a["answer"]
    assert sum(s["name"] in a["answer"] for s in robert_run["strategies"]) == 1 or len(robert_run["strategies"]) == 1
    a = ask("volatility")
    assert a["status"] == "valid" and "up and down" in a["answer"]
    a = ask("Tesla")
    assert a["status"] == "valid" and a["tool_calls"][0]["tool"] == "asset_facts"
    monkeypatch.setenv("AF_LANG", "fr")                              # French app: same text, French answer
    assert analyst.language(name) == "fr" and analyst.language("What if I put 10% in Tesla?") == "en"
    a = ask(i18n.tr_words(name))
    assert a["status"] == "valid" and "Votre limite de perte" in a["answer"] and "compris" not in a["answer"]
    assert "Je ne suis pas sûr d'avoir compris" in ask("blablabla")["answer"]
