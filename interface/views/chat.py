"""The assistant: a conversation about the person's own results.

Each turn goes through services.ask_analyst → analyst.ask with the conversation so far. Questions are queued as
"pending" turns first, so a question typed while another is being answered is not lost: turns are answered in order.
The thinking indicator lives in a `finally`, so it always disappears, also when the answer fails.
"""

from __future__ import annotations

from dh.data import period_label

import altair as alt
import pandas as pd
import streamlit as st

from interface.core import services
from interface.ui import components as ui
from interface.ui import theme

S = st.session_state
SUGGESTIONS = ["Explain my results", "What if I put 10% in Tesla?", "What is volatility?",
               "And with a 10-year horizon?", "How would my strategy have done in 2022?"]


def answered(chat: list[dict]) -> list[dict]:
    """The turns the assistant may lean on: answered without error."""
    return [t for t in chat if t.get("status") == "done" and t.get("answer")]


def chart_for(turn: dict):
    """A small chart when a what-if compared 'as asked' with 'fits your limits' (numbers from the tool result)."""
    for c in turn.get("tool_calls", []):
        r = c.get("result") or {}
        a, f = r.get("as_asked"), r.get("fits")
        if a and f and a.get("max_drawdown") is not None and f.get("max_drawdown") is not None:
            df = pd.DataFrame({"version": ["As asked", "Fits your limits"],
                               "drop": [100 * a["max_drawdown"], 100 * f["max_drawdown"]],
                               "limit": [-100 * (a.get("loss_limit") or 0)] * 2})
            base = alt.Chart(df).encode(y=alt.Y("version:N", title=None, sort=None,
                                                 scale=alt.Scale(paddingInner=0.35)))
            bars = base.mark_bar().encode(
                x=alt.X("drop:Q", title=f"Worst {period_label()} drop (%)"),
                color=alt.Color("version:N", legend=None, scale=alt.Scale(range=[theme.ERABLE, theme.ANTARCTIQUE])),
                tooltip=["version", alt.Tooltip("drop:Q", format=".1f")])
            if a.get("loss_limit"):
                bars = bars + base.mark_tick(color=theme.INK, thickness=2, size=30).encode(x="limit:Q")
            return bars.properties(height=110)
    return None


def show_answer(t: dict) -> None:
    if t.get("status") == "error":
        ui.notice(t["error"], "bad")
        return
    st.markdown(t["text"])
    ch = chart_for(t)
    if ch is not None:
        st.altair_chart(ch, width="stretch", height=130)
        st.caption("Dark mark: your loss limit.")
    if t.get("cut"):
        st.caption("Your question was long, so only its beginning was read.")
    src = "Claude on Amazon Bedrock" if t.get("source", "").startswith("bedrock") else \
        "saved answer from Claude on Amazon Bedrock" if t.get("source", "").startswith("cache") else "offline assistant"
    calls = t.get("tool_calls", [])
    st.caption(f"{src} · " + (f"{len(calls)} check{'s' if len(calls) != 1 else ''} run, every number verified by code"
                              if calls else "no number to verify"))
    if calls:
        with st.expander("How this was checked"):
            from dh.agents import analyst
            st.markdown("\n".join(f"- {analyst.short(c)}" for c in calls))
            if t.get("note"):
                st.caption(t["note"])


def answer(t: dict, history: list[dict]) -> None:
    """Fill a pending turn in place. Never raises; the indicator is always cleared."""
    try:
        with ui.thinking():
            a = services.ask_analyst(t["question"], S.res, S.profile, history)
        t.update(a, status="done")
    except (services.UserError, services.InternalError) as e:
        t.update(status="error", error=str(e))
    except Exception as e:  # noqa: BLE001 — last resort: never a traceback on screen
        services.logger().exception("chat")
        t.update(status="error", error="Something went wrong on our side. Please try again.")


def render() -> None:
    m = services.mode()
    head, new = st.columns([4, 1.4])
    head.subheader("Ask the assistant")
    if new.button("New conversation", width="stretch", disabled=not S.get("chat")):
        S.chat = []
        st.rerun()
    ui.notice(f"<b>{ui.esc(m['label'])}.</b> {ui.esc(m['help'])}", "info" if m["live"] else "warn", safe=True)
    if not S.get("res") or not S.res.get("strategies"):
        ui.notice("Run the analysis first: the assistant answers questions about your own results.", "info")
        if st.button("Go to your profile", type="primary"):
            S.goto = "Your profile"
            st.rerun()
        return
    chat = S.setdefault("chat", [])
    if not chat:
        st.markdown('<p class="af-muted">Ask in your own words, for example:</p>', unsafe_allow_html=True)
        cols = st.columns(2)
        for i, sug in enumerate(SUGGESTIONS):
            if cols[i % 2].button(sug, key=f"sug_{i}", width="stretch"):
                chat.append({"question": sug, "status": "pending"})
                st.rerun()
    for i, t in enumerate(chat):
        with st.chat_message("user"):
            st.markdown(ui.esc(t["question"]))
        with st.chat_message("assistant"):
            if t.get("status") == "pending":
                answer(t, answered(chat[:i]))
            show_answer(t)
    q = st.chat_input("Type your question and press Enter")
    if q is not None:
        if not q.strip():
            st.toast("Please type a question.")
        else:
            chat.append({"question": q.strip(), "status": "pending"})
            st.rerun()
