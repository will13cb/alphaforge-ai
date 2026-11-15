"""Français ⇄ English for the two Streamlit apps (decision #49).

    from dh import i18n
    i18n.install()              # once, after `import streamlit as st`
    i18n.language_selector()    # in the sidebar: Français / English (default from AF_LANG, else French)

`install` wraps Streamlit's display and widget methods so every label, button, tab, option, help text and message
goes through `tr`. Text the engine or the agents generate (the Profiler's reasons, check details, the cached Claude
answers, the trace) is not rewritten: only whole UI strings (EXACT) and distinctive UI phrases (PHRASES) are
translated, so nothing ends up half French, half English. Widgets get a key computed from their English arguments,
so switching language never resets what the client entered.
"""

from __future__ import annotations

import functools
import hashlib
import os
import re
import types

from .i18n_fr import EXACT, PHRASES

LANGS = {"fr": "Français", "en": "English"}
STATE_KEY = "af_lang"
_PHRASE_RE = re.compile("|".join(re.escape(k) for k in sorted(PHRASES, key=len, reverse=True))) if PHRASES else None
_EXACT_STRIPPED = {k.strip(): v for k, v in EXACT.items()}
_WRAPPED = re.compile(r"^(<(?:p|div|span)[^>]*>)([^<]+)(</(?:p|div|span)>)$", re.S)


def default_lang() -> str:
    lang = os.getenv("AF_LANG", "fr").lower()[:2]
    return lang if lang in LANGS else "fr"


def lang() -> str:
    try:
        import streamlit as st
        return st.session_state.get(STATE_KEY, default_lang())
    except Exception:  # noqa: BLE001 — outside a Streamlit run
        return default_lang()


def tr(s, to: str | None = None):
    """The text in the current language (French: exact UI string, else known UI phrases inside it)."""
    if not isinstance(s, str) or (to or lang()) != "fr" or not s.strip():
        return s
    hit = EXACT.get(s)
    if hit is not None:
        return hit
    core = s.strip()
    if core in _EXACT_STRIPPED:
        return s.replace(core, _EXACT_STRIPPED[core])
    m = _WRAPPED.match(core)  # '<p class="af-muted">Known sentence</p>': translate the sentence inside
    if m and m.group(2).strip() in _EXACT_STRIPPED:
        return s.replace(m.group(2), _EXACT_STRIPPED[m.group(2).strip()])
    return _PHRASE_RE.sub(lambda m: PHRASES[m.group(0)], s) if _PHRASE_RE else s


# ---- wrapping Streamlit ------------------------------------------------------------------------------------

TEXT_FIRST = ("title", "header", "subheader", "caption", "markdown", "text", "info", "warning", "error", "success",
              "toast", "spinner", "expander", "popover", "status", "chat_input")
WIDGETS = ("button", "form_submit_button", "download_button", "link_button", "checkbox", "toggle", "text_input",
           "text_area", "number_input", "slider", "select_slider", "radio", "selectbox", "multiselect",
           "segmented_control", "pills", "audio_input", "date_input", "time_input", "color_picker", "file_uploader")
CHOICE = ("radio", "selectbox", "multiselect", "segmented_control", "pills", "select_slider")
NO_KEY = ("link_button",)              # not a stateful widget
TEXT_KWARGS = ("label", "help", "placeholder", "body", "text", "caption")


def _stable_key(name: str, args: tuple, kwargs: dict) -> str:
    plain = [repr(a) for a in args if not callable(a)]
    plain += [f"{k}={v!r}" for k, v in sorted(kwargs.items()) if not callable(v) and k not in ("on_change", "on_click")]
    return f"af_{name}_" + hashlib.sha1("|".join(plain).encode()).hexdigest()[:12]


def _wrap_text_first(fn):
    @functools.wraps(fn)
    def w(self, *args, **kwargs):
        if args:
            args = (tr(args[0]),) + args[1:]
        for k in TEXT_KWARGS:
            if k in kwargs:
                kwargs[k] = tr(kwargs[k])
        return fn(self, *args, **kwargs)
    return w


def _wrap_widget(name, fn):
    @functools.wraps(fn)
    def w(self, *args, **kwargs):
        if "key" not in kwargs and name not in NO_KEY:
            kwargs["key"] = _stable_key(name, args, kwargs)
        if name in CHOICE:
            ff = kwargs.get("format_func")
            kwargs["format_func"] = (lambda v, ff=ff: tr(ff(v))) if ff else (lambda v: tr(str(v)))
        if args:
            args = (tr(args[0]),) + args[1:]
        for k in TEXT_KWARGS:
            if k in kwargs:
                kwargs[k] = tr(kwargs[k])
        return fn(self, *args, **kwargs)
    return w


def _wrap_tabs(fn):
    @functools.wraps(fn)
    def w(self, tabs, *args, **kwargs):
        return fn(self, [tr(t) for t in tabs], *args, **kwargs)
    return w


def _wrap_write(fn):
    @functools.wraps(fn)
    def w(self, *args, **kwargs):
        return fn(self, *[tr(a) for a in args], **kwargs)
    return w


def install() -> None:
    """Wrap Streamlit once per process (idempotent)."""
    import streamlit as st
    from streamlit.delta_generator import DeltaGenerator as DG

    if getattr(DG, "_af_i18n", False):
        return
    for name in TEXT_FIRST:
        if hasattr(DG, name):
            setattr(DG, name, _wrap_text_first(getattr(DG, name)))
    for name in WIDGETS:
        if hasattr(DG, name):
            setattr(DG, name, _wrap_widget(name, getattr(DG, name)))
    if hasattr(DG, "tabs"):
        DG.tabs = _wrap_tabs(DG.tabs)
    if hasattr(DG, "write"):
        DG.write = _wrap_write(DG.write)
    DG._af_i18n = True
    main = getattr(st, "_main", None)
    if main is not None:  # st.button etc. are bound methods of the main container, captured at import time
        for name in (*TEXT_FIRST, *WIDGETS, "tabs", "write"):
            cur = getattr(st, name, None)
            if isinstance(cur, types.MethodType) and cur.__self__ is main:
                setattr(st, name, getattr(main, name))


def language_selector(where=None) -> str:
    """Français / English switch (sidebar by default). Returns the chosen language code."""
    import streamlit as st

    box = where if where is not None else st.sidebar
    if STATE_KEY not in st.session_state:
        st.session_state[STATE_KEY] = default_lang()
    box.radio("Langue · Language", list(LANGS), format_func=LANGS.get, key=STATE_KEY, horizontal=True)
    if lang() == "fr":
        box.caption("Interface en français. Les textes produits par le moteur et les agents (raisons, contrôles, "
                    "explications enregistrées de Claude) restent en anglais.")
    return lang()
