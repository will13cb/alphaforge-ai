"""Optional listening and reviewed dictation. No unsolicited playback or submission."""
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


@st.fragment(run_every="2s")
def _transcript_status(prefix: str) -> None:
    ticket = st.session_state.get(prefix + "_job")
    if not ticket:
        return
    try:
        state, text = voice.poll(ticket)
        if state == "done":
            st.session_state[prefix + "_review"] = text
            st.session_state.pop(prefix + "_job", None)
            st.rerun()
    except voice.VoiceError as error:
        st.session_state[prefix + "_error"] = str(error)
        st.session_state.pop(prefix + "_job", None)
        st.rerun()
    st.info("Transcribing… Your text will appear here automatically.")
    if st.button("Discard recording", key=prefix + "_cancel") and discard_recording(prefix):
        st.rerun()


def dictation(prefix: str, target: str, max_chars: int = 3000) -> None:
    """Render before target widget; using a transcript never submits a profile or question."""
    if not active():
        return
    with st.expander("Record instead of typing"):
        st.caption("Record up to 60 seconds, then transcribe. Check names, amounts and percentages before using the text.")
        with st.expander("How your recording is handled"):
            st.caption("Transcribe recording sends audio to Amazon Transcribe through temporary S3 storage. "
                       "Audio and transcripts are deleted after retrieval or discard. Abandoned recordings "
                       "need the storage lifecycle to remove them; a running batch job may finish after discard.")
        ticket = st.session_state.get(prefix + "_job")
        audio = st.audio_input("Record your message", sample_rate=16000, key=prefix + "_audio", disabled=bool(ticket))
        if st.button("Transcribe recording", key=prefix + "_start", disabled=audio is None or bool(ticket)):
            try:
                st.session_state.pop(prefix + "_error", None)
                st.session_state[prefix + "_job"] = voice.start(audio.getvalue(), language())
                st.rerun()
            except voice.VoiceError as e:
                st.warning(str(e))
        if ticket:
            _transcript_status(prefix)
        error = st.session_state.get(prefix + "_error")
        if error:
            st.warning(error)
        review_key = prefix + "_review"
        if review_key in st.session_state:
            text = st.text_area("Review and edit transcript", key=review_key)
            if len(text) > max_chars:
                st.warning(f"Please shorten the transcript to {max_chars} characters before using it.")
            if st.button("Use this transcript", key=prefix + "_use", disabled=not text.strip() or len(text) > max_chars):
                st.session_state[target] = text.strip()
                st.success("Transcript copied below. Review it, then use the normal submit button.")


def read_aloud(text: str, key: str, language_code: str = "en-CA", label: str = "Listen") -> None:
    """Read displayed text, independently of the microphone language selector."""
    if not active() or not text:
        return
    fingerprint = hashlib.sha256(("neural-v2" + text + language_code).encode()).hexdigest()
    cache_key = key + "_speech"
    requested = st.button(label, key=key + "_read", icon=":material/volume_up:")
    cached = st.session_state.get(cache_key)
    if requested:
        try:
            if not cached or cached[0] != fingerprint:
                with st.spinner("Preparing natural voice…"):
                    audio, mime = voice.narrate(text, language_code)
                cached = (fingerprint, audio, mime)
                st.session_state[cache_key] = cached
        except voice.VoiceError as error:
            st.warning(str(error))
    if cached and cached[0] == fingerprint:
        # Autoplay only follows this explicit Listen click. Navigation, form edits
        # and reruns never restart speech. Native controls provide pause/seek/replay.
        st.audio(cached[1], format=cached[2], autoplay=requested)
        st.caption("Pause or replay with the player. If your browser blocks playback, press Play.")
