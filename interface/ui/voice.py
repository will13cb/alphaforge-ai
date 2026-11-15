"""Accessible, explicit record → transcribe → review → use flow; no autoplay or auto-submit."""
from __future__ import annotations

import hashlib

import streamlit as st

from interface.core import voice


def active() -> bool:
    return voice.enabled() and st.session_state.get("voice_mode", False)


def language() -> str:
    return voice.LANGUAGES[st.session_state.get("voice_language", "English (Canada)")]


def discard_recording(prefix: str) -> bool:
    ticket = st.session_state.get(prefix + "_job")
    if ticket and not voice.cancel(ticket):
        st.warning("Temporary recording cleanup failed. Try cancel again or ask the app owner to clear voice/ storage.")
        return False
    st.session_state.pop(prefix + "_job", None)
    return True


def dictation(prefix: str, target: str, max_chars: int = 3000) -> None:
    """Render before target widget; using a transcript never submits a profile or question."""
    if not active():
        return
    with st.expander("Record instead of typing"):
        st.caption("Record up to 60 seconds. Only “Transcribe recording” sends audio to Amazon Transcribe via "
                   "temporary S3 storage. Review names, amounts and percentages before using the transcript. "
                   "Temporary audio and transcripts are deleted after retrieval or discarding; an abandoned "
                   "recording may remain until the storage lifecycle removes it. AWS batch processing cannot be stopped once running; a discarded job may finish and its output needs lifecycle cleanup.")
        ticket = st.session_state.get(prefix + "_job")
        audio = st.audio_input("Record your message", sample_rate=16000, key=prefix + "_audio", disabled=bool(ticket))
        if st.button("Transcribe recording", key=prefix + "_start", disabled=audio is None or bool(ticket)):
            try:
                st.session_state[prefix + "_job"] = voice.start(audio.getvalue(), language())
                st.rerun()
            except voice.VoiceError as e:
                st.warning(str(e))
        if ticket:
            st.info("Your recording is being transcribed. Check when ready; this usually takes a little time.")
            check, cancel = st.columns(2)
            if check.button("Check transcript", key=prefix + "_poll"):
                try:
                    state, text = voice.poll(ticket)
                    if state == "done":
                        st.session_state[prefix + "_review"] = text
                        st.session_state.pop(prefix + "_job", None)
                        st.rerun()
                    st.info("Still processing. Please check again in a few seconds.")
                except voice.VoiceError as e:
                    st.warning(str(e))
            if cancel.button("Discard recording", key=prefix + "_cancel") and discard_recording(prefix):
                st.rerun()
        review_key = prefix + "_review"
        if review_key in st.session_state:
            text = st.text_area("Review and edit transcript", key=review_key)
            if len(text) > max_chars:
                st.warning(f"Please shorten the transcript to {max_chars} characters before using it.")
            if st.button("Use this transcript", key=prefix + "_use", disabled=not text.strip() or len(text) > max_chars):
                st.session_state[target] = text.strip()
                st.success("Transcript copied below. Review it, then use the normal submit button.")


def read_aloud(text: str, key: str) -> None:
    if not active() or not text:
        return
    parts = []
    # Chunk without silently dropping the remainder of a long explanation.
    clean = voice.plain_text(text)
    while clean:
        end = min(len(clean), voice.MAX_SPEECH)
        if end < len(clean):
            end = clean.rfind(" ", 0, end) or end
        parts.append(clean[:end])
        clean = clean[end:].lstrip()
    lang = language()
    fingerprint = hashlib.sha256((text + lang).encode()).hexdigest()
    cache_key = key + "_speech"
    selected = st.selectbox("Passage to read", range(len(parts)), format_func=lambda i: f"Part {i + 1} of {len(parts)}",
                            key=key + "_part") if len(parts) > 1 else 0
    if st.button("Read aloud", key=key + "_read"):
        try:
            with st.spinner("Preparing audio…"):
                audio = voice.speak(parts[selected], lang)
            # One passage per control, kept only in this browser session; never a shared cache.
            st.session_state[cache_key] = (fingerprint, selected, audio)
        except voice.VoiceError as e:
            st.warning(str(e))
    cached = st.session_state.get(cache_key)
    if cached and cached[:2] == (fingerprint, selected):
        st.audio(cached[2], format="audio/mp3")
        st.caption("Press Play to listen. Use the audio controls to pause or replay. Full text remains above.")
