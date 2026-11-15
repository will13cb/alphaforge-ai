"""Explainer (Strands agent on Bedrock): offline tests only. The agent is faked; the Guardian checks are real."""
import json

import pytest

from dh.agents import explainer
from dh.agents.profiler import derive_limits
from dh.agents.scenarios import AMIRA, ROBERT
from dh.agents.trace import Trace
from dh.personas import DISCLAIMER

ROBERT_TSLA = {**ROBERT, "requested_positions": {"TSLA": 0.25}}

STRATS = [  # contract §2 shape, numbers made up (they only exercise the checks)
    dict(key="core", name="Broad core", weights={"ZST.TO": 0.25, "XBB.TO": 0.25, "XIU.TO": 0.25, "SPY": 0.25},
         split={"growth": 0.5, "defensive": 0.5},
         split_range={"floor": None, "ceiling": 0.5, "liquidity_floor": 0.2, "conflict": False, "conflict_message": None},
         stats={"max_drawdown": -0.123, "return_2022": -0.081, "stress_2022": -0.095, "ann_vol": 0.074,
                "ann_return": 0.061, "prob_loss": 0.18},
         outlook={"risk_only": {"prob_loss": 0.18, "prob_target": None}}, adjustments=["holds: broad ETFs"]),
    dict(key="income", name="Income / dividends", weights={"XBB.TO": 0.36, "AGG": 0.27, "ZST.TO": 0.27, "RY.TO": 0.1},
         split={"growth": 0.1, "defensive": 0.9},
         split_range={"floor": None, "ceiling": 0.1, "liquidity_floor": 0.2, "conflict": False, "conflict_message": None},
         stats={"max_drawdown": -0.121, "return_2022": -0.11, "ann_vol": 0.05, "prob_loss": 0.22},
         outlook=None, adjustments=[]),
]


def as_ids(text, f):
    """What a compliant agent writes: every number replaced by its id from NUMBERS."""
    _, table = explainer.placeholders(f)
    rev = {v: k for k, v in table.items()}
    return explainer.ANY_NUM.sub(lambda m: "{" + rev[m.group(0)] + "}", text) if rev else text


@pytest.fixture(autouse=True)
def no_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(explainer, "DEMO_CACHE", tmp_path / "demo")
    monkeypatch.setattr(explainer, "LOCAL_CACHE", tmp_path / "local")


def test_template_passes_g11_to_g13_and_names_the_refusal():
    lim = derive_limits(ROBERT_TSLA)
    e = explainer.explain(STRATS, lim, ROBERT_TSLA, provider="mock")
    assert e["source"] == "template" and e["verdict"] == "pass", e["checks"]
    assert DISCLAIMER in e["text"] and "TSLA" in e["text"]


def test_facts_are_stable_and_carry_reasons():
    lim = derive_limits(ROBERT_TSLA)
    f1, f2 = explainer.facts(STRATS, lim, ROBERT_TSLA), explainer.facts(STRATS, lim, ROBERT_TSLA)
    assert explainer.facts_hash(f1) == explainer.facts_hash(f2)
    assert f1["requests_not_included"][0]["ticker"] == "TSLA" and f1["limits"]["reasons"]
    json.dumps(f1)  # JSON-ready for the agent


def test_agent_text_used_when_it_passes(monkeypatch):
    lim = derive_limits(ROBERT_TSLA)
    f = explainer.facts(STRATS, lim, ROBERT_TSLA)
    good = as_ids(explainer.template(f).replace("here is", "this is"), f)
    monkeypatch.setattr(explainer, "_run_agent", lambda *a: (good, 2))
    monkeypatch.setenv("BEDROCK_EXPLAINER_MODEL_ID", "test-model")
    e = explainer.explain(STRATS, lim, ROBERT_TSLA, provider="bedrock")
    assert e["source"] == "bedrock" and e["check_calls"] == 2 and e["verdict"] == "pass"
    # second call: served from the local cache, no agent run
    monkeypatch.setattr(explainer, "_run_agent", lambda *a: pytest.fail("agent called despite cache"))
    assert explainer.explain(STRATS, lim, ROBERT_TSLA, provider="bedrock")["source"].startswith("cache")


def test_agent_text_with_invented_number_is_replaced(monkeypatch):
    lim = derive_limits(ROBERT_TSLA)
    bad = f"TSLA is refused. This strategy should earn about 13.4% a year. {DISCLAIMER}"
    monkeypatch.setattr(explainer, "_run_agent", lambda *a: (bad, 1))
    e = explainer.explain(STRATS, lim, ROBERT_TSLA, provider="bedrock")
    assert e["source"] == "template" and "G12" in e["note"] and e["verdict"] == "pass"


def test_agent_failure_falls_back_to_template(monkeypatch):
    def boom(*a):
        raise RuntimeError("expired token")
    monkeypatch.setattr(explainer, "_run_agent", boom)
    e = explainer.explain(STRATS, derive_limits(AMIRA), AMIRA, provider="bedrock")
    assert e["source"] == "template" and "expired token" in e["note"]


def test_demo_cache_replays_offline(monkeypatch):
    lim = derive_limits(ROBERT_TSLA)
    f = explainer.facts(STRATS, lim, ROBERT_TSLA)
    text = explainer.template(f)
    monkeypatch.setattr(explainer, "_run_agent", lambda *a: (as_ids(text, f), 1))
    monkeypatch.setenv("BEDROCK_EXPLAINER_MODEL_ID", "test-model")
    e = explainer.explain(STRATS, lim, ROBERT_TSLA, provider="bedrock")
    explainer.save_demo(e)
    monkeypatch.setattr(explainer, "LOCAL_CACHE", explainer.LOCAL_CACHE.parent / "gone")
    offline = explainer.explain(STRATS, lim, ROBERT_TSLA, provider="mock")
    assert offline["source"] == "cache (demo)" and offline["text"] == text


def test_add_to_trace_appends_explainer_and_guardian():
    lim = derive_limits(ROBERT_TSLA)
    res = {"limits": lim, "strategies": STRATS, "trace": Trace()}
    explainer.add_to_trace(res, ROBERT_TSLA, provider="mock")
    assert [s["agent"] for s in res["trace"].steps] == ["Explainer", "Guardian"]
    assert res["explanation"]["verdict"] == "pass"


def test_typed_number_rejected_even_if_real(monkeypatch):
    """Strict G12: the agent must write ids; a typed number is rejected even when it equals a computed value."""
    lim = derive_limits(ROBERT_TSLA)
    f = explainer.facts(STRATS, lim, ROBERT_TSLA)
    raw = as_ids(explainer.template(f), f).replace("{", "", 0)
    real = f["strategies"][0]["worst_drop"]                       # "-12.3%", a true number
    typed = raw.replace(as_ids(real, f), real, 1)
    monkeypatch.setattr(explainer, "_run_agent", lambda *a: (typed, 1))
    e = explainer.explain(STRATS, lim, ROBERT_TSLA, provider="bedrock")
    assert e["source"] == "template" and "typed numbers" in e["note"]


def test_unknown_id_rejected(monkeypatch):
    lim = derive_limits(ROBERT_TSLA)
    f = explainer.facts(STRATS, lim, ROBERT_TSLA)
    raw = as_ids(explainer.template(f), f) + " It also fell {n999}."
    monkeypatch.setattr(explainer, "_run_agent", lambda *a: (raw, 1))
    e = explainer.explain(STRATS, lim, ROBERT_TSLA, provider="bedrock")
    assert e["source"] == "template" and "n999" in e["note"]


def test_exact_g12_catches_near_misses():
    """A number 0.3 pt from a real one used to pass (±0.5); now only exact facts pass."""
    lim = derive_limits(ROBERT_TSLA)
    f = explainer.facts(STRATS, lim, ROBERT_TSLA)
    text = explainer.template(f)
    assert explainer.check(text, STRATS, lim, ROBERT_TSLA, f)[1]["status"] == "pass"
    near = text.replace("-12.3%", "-12.0%", 1)                   # real value -12.3%
    assert explainer.check(near, STRATS, lim, ROBERT_TSLA, f)[1]["status"] == "fail"


@pytest.mark.parametrize("typed", ["12.3 percent", "12.3 per cent", "12.3 pct", "60,000 dollars", "CAD 60,000",
                                   "$60,000", "60,000 $", "−12.3 %"])
def test_typed_numbers_in_any_form_are_caught(typed):
    """However a % or $ amount is written, the agent can't type it: only ids pass."""
    lim = derive_limits(ROBERT_TSLA)
    f = explainer.facts(STRATS, lim, ROBERT_TSLA)
    _, table = explainer.placeholders(f)
    assert explainer.strict_problems(f"The worst drop was {typed}.", table)


@pytest.mark.parametrize("typed", ["was 59 years old", "over 4 years", "in 2022", "three strategies at 0.9",
                                   "about eight percent", "half a percent", "a quarter of a dollar"])
def test_any_typed_number_is_caught(typed):
    """No digit at all, and no spelled-out % or $ amount: every number must come through an id."""
    lim = derive_limits(ROBERT_TSLA)
    _, table = explainer.placeholders(explainer.facts(STRATS, lim, ROBERT_TSLA))
    if any(ch.isdigit() for ch in typed) or "percent" in typed or "dollar" in typed:
        assert explainer.strict_problems(f"Robert {typed}.", table)


def test_words_without_amounts_are_fine():
    lim = derive_limits(ROBERT_TSLA)
    _, table = explainer.placeholders(explainer.facts(STRATS, lim, ROBERT_TSLA))
    assert not explainer.strict_problems("Robert, both strategies stay within your limit {n1}. **Your request**", table)
