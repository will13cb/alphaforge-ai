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

from .i18n_engine_fr import SENTENCES, WORDS
from .i18n_fr import EXACT, PHRASES

LANGS = {"fr": "Français", "en": "English"}
STATE_KEY = "af_lang"
_PHRASE_RE = re.compile("|".join(re.escape(k) for k in sorted(PHRASES, key=len, reverse=True))) if PHRASES else None
_EXACT_STRIPPED = {k.strip(): v for k, v in EXACT.items()}
_SENTENCES = [(re.compile(p), r) for p, r in SENTENCES]
_INLINE_FIELDS = {"name", "ticker", "weight", "share", "value", "date", "text", "status", "rule", "detail", "asset_class"}
_ALL_WORDS = {**{k: v for k, v in EXACT.items() if k not in _INLINE_FIELDS}, **WORDS, **PHRASES}
_WORDS_RE = re.compile("|".join(
    (r"\b" if k[:1].isalnum() else "") + re.escape(k) + (r"\b" if k[-1:].isalnum() else "")
    for k in sorted(_ALL_WORDS, key=len, reverse=True)))
_TAG = re.compile(r"(<[^>]+>)")
_SKIP = ("<style", "<script", "<svg", "@import")
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
    if any(k in s for k in _SKIP):
        return s
    return "".join(part if part.startswith("<") else _fr_text(part) for part in _TAG.split(s))


def _fr_text(t: str) -> str:
    """French for text outside HTML tags: engine sentences, then known phrases and words, then French number style."""
    if not t.strip():
        return t
    if "`" in t:
        return "".join(part if part.startswith("`") else _fr_text(part)
                       for part in re.split(r"(`[^`]*`)", t))
    core = t.strip()
    if core in _EXACT_STRIPPED:
        return t.replace(core, french_numbers(_EXACT_STRIPPED[core]), 1)
    t = re.sub(r"\bOption (\d+) of (\d+)", r"Option \1 sur \2", t)
    t = re.sub(r"\b(\d+) ways? to invest within these limits", r"\1 façons d’investir selon vos limites", t)
    for rx, rep in _SENTENCES:
        t = rx.sub(rep, t)
    t = _WORDS_RE.sub(lambda m: _ALL_WORDS[m.group(0)], t)
    return french_numbers(t)


def tr_words(t: str) -> str:
    """French wording for engine text, numbers left exactly as written (for texts the Guardian checks, G12)."""
    if not isinstance(t, str) or not t.strip():
        return t
    for rx, rep in _SENTENCES:
        t = rx.sub(rep, t)
    return _WORDS_RE.sub(lambda m: _ALL_WORDS[m.group(0)], t)


def french_numbers(t: str) -> str:
    """60,000 → 60 000; 15.7 → 15,7; 15% → 15 % (narrow no-break spaces). Text only, never inside HTML tags."""
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "\u202f", t)
    t = re.sub(r"(?<=\d)\.(?=\d)", ",", t)
    return re.sub(r"(?<=\d)%", "\u202f%", t)


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


def _is_label(value, options: list) -> bool:
    if isinstance(value, (list, tuple)):
        return any(_is_label(v, options) for v in value)
    return isinstance(value, str) and value not in options


def _to_option(value, options: list, ff):
    """The option behind a choice that came back as its displayed label.

    Recent Streamlit sends a choice back as the label it showed. After a language switch that label is in the other
    language, matches nothing and is returned as plain text ("Accueil" for "Welcome"), which crashed the pages that
    look the choice up. Any other value is returned as it is."""
    if not _is_label(value, options):
        return value
    labels = {}
    for o in options:
        try:
            base = ff(o) if ff else str(o)
        except Exception:  # noqa: BLE001 — a format function that cannot show this option
            continue
        for code in LANGS:
            labels.setdefault(tr(base, to=code) if isinstance(base, str) else str(base), o)
    if isinstance(value, (list, tuple)):
        return type(value)(labels.get(v, v) if isinstance(v, str) and v not in options else v for v in value)
    return labels.get(value, value)


def _wrap_widget(name, fn):
    @functools.wraps(fn)
    def w(self, *args, **kwargs):
        if "key" not in kwargs and name not in NO_KEY:
            kwargs["key"] = _stable_key(name, args, kwargs)
        options = ff = None
        if name in CHOICE:
            ff = kwargs.get("format_func")
            try:
                options = list(kwargs["options"] if "options" in kwargs else args[1])
            except Exception:  # noqa: BLE001 — options given in a form we do not read: the widget handles them
                options = None
            if options:
                try:
                    import streamlit as st
                    key, now = kwargs.get("key"), lang()
                    drawn = st.session_state.setdefault("_af_choice_lang", {})    # {widget key: language last drawn in}
                    if key in st.session_state:
                        cur = st.session_state[key]
                        # Writing the choice back makes the browser redraw it with this language's label; without
                        # it the browser keeps the other language's label, shows nothing selected and sends that
                        # label back as the answer.
                        if drawn.get(key, now) != now or _is_label(cur, options):
                            st.session_state[key] = _to_option(cur, options, ff)
                    drawn[key] = now
                except Exception:  # noqa: BLE001 — outside a run, or a key that cannot be written: fixed on return
                    pass
            kwargs["format_func"] = (lambda v, ff=ff: tr(ff(v))) if ff else (lambda v: tr(str(v)))
        if args:
            args = (tr(args[0]),) + args[1:]
        for k in TEXT_KWARGS:
            if k in kwargs:
                kwargs[k] = tr(kwargs[k])
        out = fn(self, *args, **kwargs)
        return _to_option(out, options, ff) if options else out
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


def chart_spec(spec: dict) -> dict:
    """French chart labels/locale in a display copy; field names and numeric data stay intact."""
    if lang() != "fr":
        return spec
    def text(value):
        if isinstance(value, str):
            return tr(value)
        if isinstance(value, list):
            return [text(v) for v in value]
        if isinstance(value, dict):
            return {k: text(v) if k in ("text", "subtitle") else v for k, v in value.items()}
        return value
    def records(rows):
        return [{k: tr(v) if isinstance(v, str) else v for k, v in row.items()}
                if isinstance(row, dict) else row for row in rows]
    def walk(value):
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k in ("title", "subtitle", "text"):
                    out[k] = text(v)
                elif k == "datasets" and isinstance(v, dict):
                    out[k] = {name: records(rows) for name, rows in v.items()}
                elif k == "values" and isinstance(v, list):
                    out[k] = records(v)
                elif k in ("sort", "domain") and isinstance(v, list):
                    out[k] = [tr(x) if isinstance(x, str) else x for x in v]
                else:
                    out[k] = walk(v)
            return out
        return [walk(v) for v in value] if isinstance(value, list) else value
    out = walk(spec)
    out.setdefault("config", {})["locale"] = {
        "number": {"decimal": ",", "thousands": "\u202f", "grouping": [3], "currency": ["", " $"], "percent": "\u202f%"},
        "time": {"dateTime": "%A, le %e %B %Y, %X", "date": "%d/%m/%Y", "time": "%H:%M:%S", "periods": ["AM", "PM"],
                 "days": ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"],
                 "shortDays": ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."],
                 "months": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
                 "shortMonths": ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juill.", "août", "sept.", "oct.", "nov.", "déc."]}}
    return out


def _table_text(value):
    """Translate displayed headings/cells without changing the caller's data or numbers."""
    if lang() != "fr":
        return value
    import pandas as pd
    if isinstance(value, pd.DataFrame):
        shown = value.copy().map(lambda v: tr(v) if isinstance(v, str) else v)
        shown.columns = [tr(c) for c in shown.columns]
        shown.index = [tr(v) if isinstance(v, str) else v for v in shown.index]
        return shown
    if isinstance(value, list) and value and all(isinstance(row, dict) for row in value):
        return _table_text(pd.DataFrame(value))
    if isinstance(value, pd.Series):
        shown = value.copy().map(lambda v: tr(v) if isinstance(v, str) else v)
        shown.name = tr(shown.name)
        return shown
    return value


def _wrap_table(fn):
    @functools.wraps(fn)
    def w(self, *args, **kwargs):
        if args:
            args = (_table_text(args[0]),) + args[1:]
        if "data" in kwargs:
            kwargs["data"] = _table_text(kwargs["data"])
        return fn(self, *args, **kwargs)
    return w


def _wrap_metric(fn):
    @functools.wraps(fn)
    def w(self, *args, **kwargs):
        args = tuple(tr(v) if i < 3 else v for i, v in enumerate(args))
        for key in ("label", "value", "delta", "help"):
            if key in kwargs:
                kwargs[key] = tr(kwargs[key])
        return fn(self, *args, **kwargs)
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
    for name in ("table", "dataframe"):
        if hasattr(DG, name):
            setattr(DG, name, _wrap_table(getattr(DG, name)))
    DG.metric = _wrap_metric(DG.metric)
    DG._af_i18n = True
    main = getattr(st, "_main", None)
    if main is not None:  # st.button etc. are bound methods of the main container, captured at import time
        for name in (*TEXT_FIRST, *WIDGETS, "tabs", "write", "table", "dataframe", "metric"):
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
    return lang()

