"""Real trace observers must preserve results and remain isolated per run."""
import sys
from pathlib import Path

from dh.agents import pipeline
from dh.agents.scenarios import DROPS_DEMO, ROBERT
from dh.agents.trace import Trace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_completed_steps_stream_in_order_and_cannot_be_mutated_by_display():
    events = []

    def display(step):
        events.append(step)
        step["output"]["risk_level"] = -100

    result = pipeline.run(ROBERT, propose=False, drops=DROPS_DEMO, on_step=display)
    assert [s["agent"] for s in events] == ["Profiler"]
    assert result["limits"]["risk_level"] > 0
    assert result["trace"].steps[0]["output"]["risk_level"] > 0
    assert pipeline.run(ROBERT, propose=False, drops=DROPS_DEMO)["trace"].on_step is None


def test_failed_display_keeps_the_evidence_and_financial_result():
    def broken(step):
        raise RuntimeError("browser display failed")

    expected = pipeline.run(ROBERT, propose=False, drops=DROPS_DEMO)
    actual = pipeline.run(ROBERT, propose=False, drops=DROPS_DEMO, on_step=broken)
    assert actual["verdict"] == expected["verdict"]
    assert actual["limits"] == expected["limits"]
    assert len(actual["trace"].steps) == len(expected["trace"].steps)


def test_activity_escapes_client_and_engine_text():
    from interface.ui.activity import event_html
    step = Trace().step("<script>", "Client", '<img src=x onerror="x">')
    html = event_html(step)
    assert "<script>" not in html and "<img" not in html and "&lt;script&gt;" in html


def test_client_theme_and_activity_navigation():
    from streamlit.testing.v1 import AppTest
    app = Path(__file__).resolve().parents[1] / "interface" / "app.py"
    at = AppTest.from_file(str(app), default_timeout=60).run()
    assert not at.exception
    at.sidebar.toggle(key="dark_mode").set_value(True).run()
    assert not at.exception
    assert any("color-scheme: dark" in m.value for m in at.markdown)
    at.sidebar.radio(key="section").set_value("Activity").run()
    assert not at.exception
    assert any("behind your analysis" in title.value for title in at.title)
    at.sidebar.toggle(key="dark_mode").set_value(False).run()
    assert at.session_state.section == "Activity"
    assert any("color-scheme: light" in m.value for m in at.markdown)
