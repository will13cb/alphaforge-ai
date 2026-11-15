"""Readable output must keep numbers intact and pass the existing financial checks."""
import re

import pytest
from test_portfolio import fewer_scenarios, rets  # noqa: F401

from dh.agents import analyst, pipeline
from dh.agents.scenarios import ROBERT
from interface.ui.answer_format import readable_markdown


PROSE = (
    "I didn't pick one mix for you. Your run produced three strategies, and the choice is yours. "
    "The first is 'Growth tilt', with 55% in growth assets. It holds QQQ 24.5%, ZST.TO (cash-like) 22.5%, "
    "GLD (gold) 22.5%, SPY 15.5%, NVDA 6%, MSFT 6% and GOOGL 3%, and its worst past drop was -17.45%. "
    "'Broad core' has 45% in growth assets with a worst drop of -13.89%, and 'Income / dividends' has "
    "34.5% with a worst drop of -10.28%. All three stayed within your 40% loss limit (12,000 $)."
)


def test_legacy_paragraphs_keep_every_word_and_number():
    rendered = readable_markdown(PROSE)
    assert "\n\n" in rendered
    assert rendered.split() == PROSE.split()
    assert re.findall(r"-?\d[\d.,]*%?", rendered) == re.findall(r"-?\d[\d.,]*%?", PROSE)
    assert "ZST.TO" in rendered and "-17.45%" in rendered and "12,000 $" in rendered


@pytest.mark.parametrize("text", [
    "**Your allocation**\n\n| Holding | Share |\n|---|---|\n| GLD | 22.5% |",
    "**As asked**\n\n- GLD: 22.5%\n- SPY: 15.5%",
    "A short answer with 15.5% and 12,000 $.",
    "## Summary\n" + PROSE,
])
def test_existing_markdown_is_not_rewritten(text):
    assert readable_markdown(text) == text


def test_french_numbers_and_tickers_survive():
    text = "La répartition reste votre choix. " + (
        "La pire baisse de XIU.TO est de -13,7 %, soit 12 000 $. " * 8)
    assert readable_markdown(text).split() == text.split()


def test_offline_results_show_holdings_and_still_pass_validation(rets, monkeypatch, tmp_path):
    monkeypatch.setattr(analyst, "DEMO_CACHE", tmp_path / "demo")
    monkeypatch.setattr(analyst, "LOCAL_CACHE", tmp_path / "local")
    result = pipeline.run(ROBERT, rets=rets, holdings={}, critic=False)
    answer = analyst.ask("Explain my results", result, ROBERT, provider="mock", rets=rets, holdings={})
    assert answer["status"] == "valid"
    assert "| Strategy |" in answer["answer"] and "— holdings**" in answer["answer"]
    for ticker in result["strategies"][0]["weights"]:
        assert f"- **{ticker}:**" in answer["answer"]
    clean = analyst.strip_disclaimer(answer["answer"])
    assert analyst.validate({"answer": clean, "evidence": answer["evidence"]}, answer["tool_calls"],
                            analyst.entity_names(result["strategies"]))[0] == "valid"


def test_fallback_help_is_short_and_scannable(rets, monkeypatch, tmp_path):
    monkeypatch.setattr(analyst, "DEMO_CACHE", tmp_path / "demo")
    monkeypatch.setattr(analyst, "LOCAL_CACHE", tmp_path / "local")
    result = pipeline.run(ROBERT, rets=rets, holdings={}, critic=False)
    answer = analyst.ask("blablabla", result, ROBERT, provider="mock", rets=rets, holdings={})
    assert "not sure I understood" in answer["answer"]
    assert "\n\n" in answer["answer"] and "\n- **" in answer["answer"]
    assert "percentage" in answer["answer"] and not answer["tool_calls"]
