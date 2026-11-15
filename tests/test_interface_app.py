"""The guided interface, end to end with Streamlit's AppTest (offline: mock LLM, starter data if present)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from interface.core import services  # noqa: E402

APP = str(ROOT / "interface" / "app.py")
needs_data = pytest.mark.skipif(not services.data_ready()[0], reason="starter CSVs not in data/raw (make data)")


def start():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    return at


def btn(at, label):
    return next(b for b in at.button if b.label == label)


def errors(at):
    return [m.value for m in at.markdown if 'class="af-err"' in m.value]


def go(at, section):
    at.sidebar.radio[0].set_value(section).run()
    assert not at.exception


def test_welcome_and_navigation_without_results():
    at = start()
    assert any("simulation for learning" in m.value for m in at.markdown)
    go(at, "Your results")
    assert any("No results yet" in m.value for m in at.markdown)
    go(at, "Assistant")
    assert any("Run the analysis first" in m.value for m in at.markdown) and not at.chat_input


def test_step_blocks_with_messages_then_back_keeps_answers():
    at = start()
    btn(at, "Start the questions").click().run()
    assert at.session_state.step == 0 and not errors(at)            # no red before trying
    btn(at, "Continue →").click().run()
    assert at.session_state.step == 0 and len(errors(at)) >= 4       # 3 fields + the summary line
    at.text_input(key="f_age").set_value("abc").run()
    assert any("whole number" in e for e in errors(at))
    at.text_input(key="f_age").set_value("45").run()
    at.radio(key="f_income_stability").set_value("stable").run()
    at.text_input(key="f_emergency_fund_months").set_value("6").run()
    assert not errors(at)                                            # errors disappear as soon as fixed
    btn(at, "Continue →").click().run()
    assert at.session_state.step == 1
    btn(at, "← Back").click().run()
    assert at.session_state.step == 0 and at.text_input(key="f_age").value == "45"


def test_conditional_question_and_reset():
    at = start()
    btn(at, "Start the questions").click().run()
    at.session_state.step = 1
    at.run()
    assert not [t for t in at.text_input if t.key == "f_target_amount"]
    at.radio(key="f_has_target").set_value("yes").run()
    assert [t for t in at.text_input if t.key == "f_target_amount"]
    btn(at, "Start over").click().run()
    btn(at, "Erase all?").click().run()
    assert at.session_state.step == 0 and not any(at.session_state.answers.values())


@needs_data
def test_full_flow_results_and_conversation():
    at = start()
    btn(at, "Try with an example client").click().run()
    assert at.session_state.step == 5 and any("Check your answers" in s.value for s in at.subheader)
    btn(at, "Run the analysis").click().run()
    assert not at.exception and at.session_state.section == "Your results"
    md = " ".join(m.value for m in at.markdown)
    assert "Your limits" in " ".join(s.value for s in at.subheader) and "Traceback" not in md
    assert not [m for m in at.markdown if "role=\"status\"" in m.value]          # indicator cleared
    go(at, "Assistant")
    assert any("Offline: limited answers" in m.value for m in at.markdown)
    at.chat_input[0].set_value("What if I put 10% in Tesla?").run()
    at.chat_input[0].set_value("and with 5%?").run()                  # context kept: still Tesla
    chat = at.session_state.chat
    assert [t["status"] for t in chat] == ["done", "done"]
    assert chat[1]["tool_calls"][0]["args"] == {"ticker": "TSLA", "weight": 0.05}
    assert len(at.chat_message) == 4 and not [m for m in at.markdown if "role=\"status\"" in m.value]
    at.chat_input[0].set_value("blablabla").run()                     # unclear: says so, no number invented
    assert "not sure I understood" in at.session_state.chat[-1]["text"]
    at.chat_input[0].set_value("What is volatility? " * 60).run()     # very long question: cut and said
    assert at.session_state.chat[-1]["cut"]
    btn(at, "New conversation").click().run()
    assert at.session_state.chat == []


@needs_data
def test_chat_failure_is_a_message_and_rapid_questions_queue(monkeypatch):
    at = start()
    btn(at, "Try with an example client").click().run()
    btn(at, "Run the analysis").click().run()
    go(at, "Assistant")
    at.session_state.chat = [{"question": "What is volatility?", "status": "pending"},
                             {"question": "What is an ETF?", "status": "pending"}]   # typed in a row
    at.run()
    assert [t["status"] for t in at.session_state.chat] == ["done", "done"]
    at.session_state.res = {"strategies": [{}], "limits": {}}      # broken result → the analyst fails inside
    at.chat_input[0].set_value("What if I put 10% in Tesla?").run()
    t = at.session_state.chat[-1]
    assert t["status"] == "error" and "reference" in t["error"] and not at.exception
    assert not [m for m in at.markdown if "role=\"status\"" in m.value]


def test_welcome_text_goes_through_the_extractor_to_the_form():
    """Welcome → "In your own words": the text is read by the Extractor and lands on the form, prefilled."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "interface" / "app.py"), default_timeout=120).run()
    at.text_area(key="welcome_text").set_value("I'm 59, retiring in about 4 years. I have $400,000 saved and 12 months "
                                               "of expenses set aside. I can't lose more than 15%.").run()
    btn(at, "Continue with my text").click().run()
    assert not at.exception, at.exception
    assert at.session_state["section"] == "Your profile"
    assert at.session_state["free_text_notes"]["profile"]["age"] == 59
