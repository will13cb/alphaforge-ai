"""Appearance navigation and reviewed speech flow through the actual Streamlit app."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from interface.core import voice

APP = str(Path(__file__).resolve().parents[1] / "interface" / "app.py")


def test_appearance_and_large_text_preserve_form_answers():
    app = AppTest.from_file(APP).run()
    next(b for b in app.button if b.label == "Start the questions").click().run()
    app.text_input(key="f_age").set_value("59").run()
    app.toggle(key="dark_mode").set_value(True).run()
    app.toggle(key="large_text").set_value(True).run()
    assert not app.exception
    assert app.text_input(key="f_age").value == "59"
    css = " ".join(x.value for x in app.markdown)
    assert "--bg:#0E0D13" in css and "font-size:19px" in css
    app.toggle(key="dark_mode").set_value(False).run()
    assert not app.exception and app.text_input(key="f_age").value == "59"


def test_voice_transcript_requires_review_and_separate_submit(monkeypatch):
    monkeypatch.setenv("AF_VOICE_ENABLED", "1")
    app = AppTest.from_file(APP).run()
    app.toggle(key="voice_mode").set_value(True).run()
    app.session_state["welcome_voice_review"] = "I'm 59 with 400000 dollars."
    app.run()
    assert app.text_area(key="welcome_text").value == ""
    app.button(key="welcome_voice_use").click().run()
    assert not app.exception
    assert app.text_area(key="welcome_text").value == "I'm 59 with 400000 dollars."
    assert app.session_state["section"] == "Welcome"  # never automatically submits


def test_read_aloud_failure_keeps_text_and_navigation(monkeypatch):
    monkeypatch.setenv("AF_VOICE_ENABLED", "1")
    def fail(*args):
        raise voice.VoiceError("Read aloud is unavailable.")
    monkeypatch.setattr(voice, "speak", fail)
    app = AppTest.from_file(APP).run()
    app.toggle(key="voice_mode").set_value(True).run()
    app.button(key="welcome_intro_read").click().run()
    assert not app.exception and any("unavailable" in w.value for w in app.warning)
    assert app.text_area(key="welcome_text") is not None


def test_reviewed_voice_question_uses_existing_analyst(monkeypatch):
    from interface.core import services
    monkeypatch.setenv("AF_VOICE_ENABLED", "1")
    calls = []
    def ask(question, res, profile, history):
        calls.append(question)
        return dict(text="A checked explanation.", answer="A checked explanation.", source="mock", tool_calls=[])
    monkeypatch.setattr(services, "ask_analyst", ask)
    app = AppTest.from_file(APP).run()
    app.toggle(key="voice_mode").set_value(True).run()
    app.session_state["res"] = {"strategies": [{}]}
    app.session_state["profile"] = {}
    app.radio(key="section").set_value("Assistant").run()
    app.session_state["chat_voice_review"] = "What is volatility?"
    app.run()
    app.button(key="chat_voice_use").click().run()
    assert not calls  # copying a reviewed transcript never sends it
    next(b for b in app.button if b.label == "Send reviewed question").click().run()
    assert not app.exception and calls == ["What is volatility?"]
    assert app.text_area(key="voice_question").value == ""
    app.run()
    assert calls == ["What is volatility?"]  # a rerun must not duplicate the turn


def test_french_recording_language_does_not_change_english_playback(monkeypatch):
    monkeypatch.setenv("AF_VOICE_ENABLED", "1")
    calls = []
    def narrate(text, language):
        calls.append((text, language))
        return b"audio", "audio/mp3"
    monkeypatch.setattr(voice, "narrate", narrate)
    app = AppTest.from_file(APP).run()
    app.toggle(key="voice_mode").set_value(True).run()
    app.selectbox(key="voice_language").set_value("Français (Canada)").run()
    assert not calls
    app.button(key="welcome_intro_read").click().run()
    assert not app.exception
    assert len(calls) == 1 and calls[0][1] == "en-CA"
    assert "Invest within your own limits" in calls[0][0]  # the actual visible introduction
    assert "Answer a few questions" in calls[0][0]
    assert app.get("audio")[0].proto.autoplay is True
    app.toggle(key="large_text").set_value(True).run()
    assert len(calls) == 1  # form/display reruns do not regenerate speech
    assert app.get("audio")[0].proto.autoplay is False
    app.button(key="welcome_intro_read").click().run()
    assert len(calls) == 1  # replay uses session audio


def test_ready_transcript_appears_without_manual_status_checks(monkeypatch):
    monkeypatch.setenv("AF_VOICE_ENABLED", "1")
    monkeypatch.setattr(voice, "poll", lambda ticket: ("done", "My horizon is 10 years."))
    app = AppTest.from_file(APP).run()
    app.toggle(key="voice_mode").set_value(True).run()
    app.session_state["welcome_voice_job"] = {"job": "mock-job"}
    app.run()
    assert not app.exception
    assert app.text_area(key="welcome_voice_review").value == "My horizon is 10 years."
    assert app.text_area(key="welcome_text").value == ""  # review still required
    assert not any(b.label == "Check transcript" for b in app.button)
