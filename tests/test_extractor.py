"""Extractor: free text → profile facts. Offline (rule-based parser; the agent is faked)."""
import pytest

from dh.agents import extractor as x
from dh.agents.pipeline import run
from dh.agents.scenarios import DROPS_DEMO

ROBERT_TEXT = ("I'm 59, retiring in about four years. I have $400,000 saved and 12 months of expenses set aside. My job "
               "in a hospital is stable. I don't want to lose much, put 25% of my savings in Tesla. I can't lose more "
               "than 15%. If it dropped I'd hold. I'm an experienced investor, 20 years of experience. No crypto.")


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(x, "DEMO_CACHE", tmp_path / "demo")
    monkeypatch.setattr(x, "LOCAL_CACHE", tmp_path / "local")


def test_numbers_written_in_words_k_and_commas():
    assert {4, 400, 400_000, 30, 30_000, 25} <= x.numbers_in("four years, 400k or 400,000, thirty k, twenty-five")


def test_rules_read_robert_and_the_request_is_not_the_loss_limit():
    ex = x.extract(ROBERT_TEXT, provider="mock")
    p = ex["profile"]
    assert ex["source"] == "rules" and ex["missing"] == []
    assert (p["age"], p["horizon_years"], p["capital"], p["max_loss_pct"]) == (59, 4, 400_000, 15)
    assert p["requested_positions"] == {"TSLA": 0.25} and p["exclusions"] == ["crypto"]
    assert (p["objective"], p["loss_reaction"], p["knowledge_level"]) == ("retirement", "hold", "advanced")


def test_missing_essentials_become_questions():
    ex = x.extract("I want 30% in XSP.", provider="mock")
    assert ex["profile"]["requested_positions"] == {"XSP": 0.3}   # unknown ticker kept: the Profiler explains it
    assert set(ex["missing"]) == set(x.QUESTIONS) and len(ex["questions"]) == len(x.QUESTIONS)


def test_validate_drops_invented_numbers_and_bad_values():
    p, notes = x.validate({"age": 59, "capital": 500_000, "objective": "Retirement", "loss_reaction": "panic",
                           "requested_positions": {"tesla": 30}, "risk_level": 2}, "I'm 59 with 400k, 25% in Tesla")
    assert p == {"age": 59, "objective": "retirement"}
    assert any("capital" in n for n in notes) and any("loss_reaction" in n for n in notes)
    assert any("request" in n for n in notes) and any("risk_level" in n for n in notes)   # never sets a score


def test_agent_answer_is_checked_by_code(monkeypatch):
    monkeypatch.setattr(x, "_run_agent", lambda t: ({"age": 59, "horizon_years": 4, "capital": 450_000,
                                                     "requested_positions": {"TSLA": 0.25}}, 2))
    ex = x.extract(ROBERT_TEXT, provider="bedrock")
    assert ex["source"] == "bedrock" and ex["check_calls"] == 2
    assert "capital" not in ex["profile"] and ex["profile"]["requested_positions"] == {"TSLA": 0.25}
    assert x.extract(ROBERT_TEXT, provider="mock")["source"].startswith("cache")   # cached for the next run


def test_agent_failure_falls_back_to_rules(monkeypatch):
    def boom(t):
        raise RuntimeError("no credentials")
    monkeypatch.setattr(x, "_run_agent", boom)
    ex = x.extract(ROBERT_TEXT, provider="bedrock")
    assert ex["source"] == "rules" and "no credentials" in ex["note"] and ex["profile"]["age"] == 59


def test_extracted_profile_runs_the_pipeline_and_the_trace_starts_with_the_extractor():
    ex = x.extract(ROBERT_TEXT, provider="mock")
    res = run(ex["profile"], propose=False, drops=DROPS_DEMO)
    x.add_to_trace(res, ex)
    assert res["limits"]["risk_level"] == 2 and res["limits"]["request_checks"][0]["ticker"] == "TSLA"
    assert res["trace"].steps[0]["agent"] == "Extractor" and res["trace"].steps[1]["agent"] == "Profiler"
