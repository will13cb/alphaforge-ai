"""Reusable pieces, so every screen looks and behaves the same. Text passed here is escaped unless marked safe."""

from __future__ import annotations

import html

from dh.i18n import tr
from contextlib import contextmanager

import streamlit as st

from interface.core.questions import Question
from interface.ui import theme


def esc(t) -> str:
    """Escaped for HTML, in the interface language (UI text only; engine text passes through, #49)."""
    return html.escape(str(tr(t) if t is not None else ""))


def label(q: Question) -> None:
    badge = f'<span class="af-badge req">{esc("required")}</span>' if q.required else f'<span class="af-badge">{esc("optional")}</span>'
    st.markdown(f'<div class="af-q">{esc(q.label)}{badge}</div>', unsafe_allow_html=True)


def example(text: str) -> None:
    if text:
        st.markdown(f'<div class="af-ex">{esc(text)}</div>', unsafe_allow_html=True)


def error(text: str | None) -> None:
    if text:
        st.markdown(f'<div class="af-err" role="alert">{esc(text)}</div>', unsafe_allow_html=True)


def field(q: Question, answers: dict, err: str | None, key_prefix: str = "f") -> None:
    """One question: label + badge, the input (with ⓘ help), the example in italics, the error in red underneath.
    Writes the raw answer back into `answers` (kept raw, so going back never loses anything)."""
    label(q)
    key, cur, hp = f"{key_prefix}_{q.id}", answers.get(q.id, q.default), q.help or None
    if q.kind in ("choice", "yesno"):
        opts = [o for o, _ in q.options]
        names = dict(q.options)
        idx = opts.index(cur) if cur in opts else None
        if q.kind == "yesno" or len(opts) <= 4:
            val = st.radio(q.label, opts, index=idx, format_func=names.get, key=key, help=hp,
                           label_visibility="collapsed", horizontal=q.kind == "yesno")
        else:
            val = st.selectbox(q.label, opts, index=idx, format_func=names.get, key=key, help=hp,
                               label_visibility="collapsed", placeholder="Choose one…")
        answers[q.id] = val
    elif q.kind == "choices":
        opts = [o for o, _ in q.options]
        val = st.multiselect(q.label, opts, default=[x for x in (cur or []) if x in opts],
                             format_func=dict(q.options).get, key=key, help=hp, label_visibility="collapsed",
                             placeholder="Choose any that apply (or leave empty)")
        answers[q.id] = list(val)
    elif q.kind == "position":
        name0, pct0 = cur if isinstance(cur, (list, tuple)) and len(cur) == 2 else ("", "")
        a, b = st.columns([3, 2])
        n = a.text_input("Company or fund", value=name0, key=key + "_n", help=hp)
        p = b.text_input("Share of your money, in %", value=pct0, key=key + "_p")
        answers[q.id] = (n, p)
    else:
        val = st.text_input(q.label, value="" if cur is None else str(cur), key=key, help=hp,
                            label_visibility="collapsed")
        answers[q.id] = val
    if q.kind not in ("choice", "yesno", "choices"):
        example(q.example)
    error(err)


def notice(text: str, tone: str = "info", safe: bool = False) -> None:
    """A short framed message. tone: info | good | warn | bad."""
    body = text if safe else esc(text)
    st.markdown(f'<div class="af-note {tone}">{body}</div>', unsafe_allow_html=True)


def card(title: str, body_md: str = "") -> None:
    st.markdown(f'<div class="af-card"><h4>{esc(title)}</h4><div class="af-muted">{esc(body_md)}</div></div>',
                unsafe_allow_html=True)


def metric(col, value: str, text: str) -> None:
    col.markdown(f'<div class="af-metric"><div class="v">{esc(value)}</div><div class="l">{esc(text)}</div></div>',
                 unsafe_allow_html=True)


def steps_bar(titles: list[str], current: int) -> None:
    out = []
    for i, t in enumerate(titles):
        cls = "on" if i == current else "done" if i < current else ""
        out.append(f'<span class="af-step {cls}">{i + 1}. {esc(t)}</span>')
    st.markdown(f'<div class="af-steps" aria-label="Steps">{"".join(out)}</div>', unsafe_allow_html=True)


@contextmanager
def thinking(text: str = "The assistant is checking your question…"):
    """An animated indicator while the engine works. Always cleared, even if the work fails (finally)."""
    box = st.empty()
    box.markdown(f'<div class="af-thinking" role="status" aria-live="polite"><span class="d"></span>'
                 f'<span class="d"></span><span class="d"></span>{esc(text)}</div>', unsafe_allow_html=True)
    try:
        yield box
    finally:
        box.empty()


def chart(ch, **kw) -> None:
    """An engine chart in the current display mode (light or dark): colours from theme.style_chart, no Streamlit
    theme on top so text stays readable on both backgrounds."""
    st.altair_chart(theme.style_chart(ch, theme.mode(st.session_state)), width="stretch", theme=None, **kw)
