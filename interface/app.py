"""AlphaForge AI, the guided interface. Run: make ui   (needs the starter CSVs in data/raw/: make data)

Four sections: Welcome · Your profile (step by step) · Your results · Assistant. The engine is the same as
app/app.py (pipeline, Explainer, Analyst); this app only asks, checks what was typed, and shows. See README.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from dh import bootstrap  # noqa: E402
from dh.data import period_label  # noqa: E402
from dh.personas import DISCLAIMER  # noqa: E402
from interface.core import services, voice  # noqa: E402
from interface.ui import activity
from interface.ui import components as ui  # noqa: E402
from interface.ui import theme, voice as voice_ui  # noqa: E402
from interface.views import chat, holdings_input, profile, results  # noqa: E402

st.set_page_config(page_title="AlphaForge AI", page_icon=":material/account_balance:", layout="centered")
S = st.session_state
st.markdown(theme.css(theme.mode(S), S.get("large_text", False)), unsafe_allow_html=True)  # before any widget: the switch applies at once
SECTIONS = ["Welcome", "Your profile", "Your results", "Activity", "Assistant"]


def welcome() -> None:
    st.markdown('<div class="af-eyebrow">AlphaForge AI &middot; Simulation</div>', unsafe_allow_html=True)
    title = "See how to invest, within limits you can explain"
    introduction = ("Answer a few questions about your situation. We work out **how much risk you can carry**, propose "
                "**up to three simulated ways to invest** that respect it, and explain every number in plain words. "
                "Then you can ask questions.")
    st.title(title)
    st.markdown(introduction)
    voice_ui.read_aloud(title + ". " + introduction, "welcome_intro", label="Listen to this introduction")
    for col, (t, b) in zip(st.columns(3), [
            ("1 · A few questions", "About 5 minutes. Only what is needed, with help on each question."),
            ("2 · Your limits and strategies", f"Computed by rules and {period_label()} market data, not guessed."),
            ("3 · Questions and what-ifs", "“What if I put 10% in Tesla?” The answer re-runs every check.")]):
        with col:
            ui.card(t, b)
    ui.notice("<b>This is a simulation for learning.</b> It is not financial advice and makes no transaction.", "warn",
              safe=True)
    ok, msg = services.data_ready()
    if not ok:
        ui.notice(msg, "bad")
    st.subheader("How would you like to start?")
    t_words, t_steps, t_held = st.tabs(["In your own words", "Step-by-step questions", "I already have a portfolio"])
    with t_held:
        holdings_input.render()
    with t_words:  # free text → the Extractor (Strands agent; offline: rule parser) fills the form, you check it
        st.markdown('<p class="af-muted">Describe your situation in a few sentences. We fill in what we can and '
                    'ask only what is missing. Nothing is invented: a number is kept only if you wrote it.</p>',
                    unsafe_allow_html=True)
        voice_ui.dictation("welcome_voice", "welcome_text")
        text = st.text_area("Your situation", key="welcome_text", height=130, label_visibility="collapsed",
                            placeholder="e.g. I'm 59 and retiring in about 4 years. I have $400,000 saved and 12 months "
                                        "of expenses set aside. I can't lose more than 15%. I'd like 25% in Tesla.")
        if st.button("Continue with my text", type="primary", width="stretch", disabled=not (text or "").strip()):
            try:
                with ui.thinking("Reading your text…"):
                    ex = services.extract_text(text)
                profile.prefill(ex["profile"], where=0)
                if ex["profile"].get("existing_positions"):   # "I have 10k in XIU": the portfolio tab gets it too
                    S.existing_positions = dict(ex["profile"]["existing_positions"])
                S.free_text_notes = ex
                S.goto = "Your profile"
                st.rerun()
            except (services.UserError, services.InternalError) as e:
                ui.error(str(e))
    with t_steps:
        st.markdown('<p class="af-muted">About 5 minutes, one topic at a time, with help on each question.</p>',
                    unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        if b1.button("Start the questions", type="primary", width="stretch"):
            S.goto = "Your profile"
            st.rerun()
        if b2.button("Try with an example client", width="stretch"):
            profile.prefill(services.demo_clients()["robert"][1])
            S.goto = "Your profile"
            st.rerun()


def sidebar() -> str:
    if "goto" in S:                      # a button asked to change section: set it before the menu is drawn
        S.section = S.pop("goto")
    S.setdefault("section", "Welcome")
    with st.sidebar:
        st.markdown('<div class="af-brand"><span class="mark"></span>AlphaForge AI</div>', unsafe_allow_html=True)
        sec = st.radio("Go to", SECTIONS, key="section", label_visibility="collapsed")
        if S.get("res"):
            st.caption("Analysis ready")
        st.divider()
        st.toggle("Dark mode", key="dark_mode", help="Switch between the light and the dark display.")
        with st.expander("Accessibility"):
            st.toggle("Larger text", key="large_text")
            if voice.enabled():
                st.toggle("Voice assistance", key="voice_mode",
                          help="Record messages and listen to text with AWS speech services. Always optional.")
                if S.get("voice_mode"):
                    st.selectbox("Recording language", list(voice.LANGUAGES), key="voice_language")
                    st.caption("Recording can be in English or French. Listen reads the displayed English text. Microphone access is requested only when you record.")
            else:
                st.caption("Voice assistance is not enabled on this deployment. Typing remains available.")
        m = services.mode()
        st.caption(f"Assistant: {m['label']}")
        st.caption(DISCLAIMER)
    return sec


SHORT = ["Start", "Profile", "Results", "Activity", "Assistant"]


def mobile_nav(sec: str) -> None:
    """Sections as a row of tabs at the top, shown on a phone only (CSS hides it on wider screens, where the
    sidebar is open). It moves the same `section` as the sidebar menu."""
    with st.container(key="af_mnav"):
        pick = st.segmented_control("Section", SHORT, default=SHORT[SECTIONS.index(sec)], key=f"mnav_{sec}",
                                    label_visibility="collapsed")
    if pick and pick != SHORT[SECTIONS.index(sec)]:
        S.goto = SECTIONS[SHORT.index(pick)]
        st.rerun()


def scroll_to_top_on_change(sec: str) -> None:
    """A new section or a new step opens at its top. Streamlit keeps the scroll position across reruns, so on a phone
    "Run the analysis" or "Continue" landed in the middle of the next page. Runs only when the place changes."""
    where = f"{sec}|{S.get('step')}"
    if S.get("_where") == where:
        return
    S._where = where
    components.html(f"""<script>/* {where} */
      const d = window.parent.document;
      for (const q of ['[data-testid="stMain"]', '[data-testid="stAppScrollToBottomContainer"]', '.stMain'])
        d.querySelectorAll(q).forEach(e => e.scrollTo(0, 0));
      window.parent.scrollTo(0, 0);</script>""", height=0)


def main() -> None:
    if not bootstrap.data_present() and os.getenv("AF_AUTO_DATA") == "1":  # hosted copy: build data/raw/ once
        with st.spinner("First start: downloading the market data with the organizers' script (1-2 minutes)…"):
            bootstrap.ensure_data()
    sec = sidebar()
    mobile_nav(sec)
    try:
        {"Welcome": welcome, "Your profile": profile.render, "Your results": results.render,
         "Assistant": chat.render, "Activity": activity.render}[sec]()
    except Exception:  # noqa: BLE001 — last boundary (st.rerun is a BaseException, not caught here)
        services.logger().exception("page %s", sec)
        ui.notice("Something went wrong while showing this page. Your answers are kept; please try again, or go "
                  "back to the previous section.", "bad")
    st.markdown(f'<p class="af-muted" style="margin-top:2rem">{ui.esc(DISCLAIMER)}</p>', unsafe_allow_html=True)
    scroll_to_top_on_change(sec)


main()

