"""Observable pipeline activity shared by the client and jury views; never model reasoning."""
from __future__ import annotations

from contextlib import contextmanager
from html import escape

import streamlit as st

from interface.ui import components as ui
from interface.ui import flow

STAGES = ["Profiler", "Market data", "Portfolio", "Guardian", "Critic", "Explainer", "Trace store"]


def event_html(step: dict) -> str:
    head = escape(f"{step['agent']} → {step['to']}")
    stamp = escape(step.get("timestamp", ""))
    return (f'<div class="af-event"><div class="af-event-head">{head}'
            f'<span class="af-event-time">{stamp}</span></div>'
            f'<p>{escape(step.get("summary", ""))}</p></div>')


def _short(text: str, n: int = 160) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


@contextmanager
def live_run():
    """Yield a callback for Trace.step; failures keep completed events visible."""
    with st.status("Analysis running · checking your profile and market history…", expanded=True) as status:
        st.caption("Live activity · each entry appears after a real hand-off completes. Longer steps may take a moment.")
        graph = st.empty()
        graph.markdown(flow.svg([]), unsafe_allow_html=True)
        feed = st.empty()
        events = []

        def on_step(step):
            events.append(step)
            graph.markdown(flow.svg(events, caption=_short(step.get("summary", ""))), unsafe_allow_html=True)
            feed.markdown("".join(event_html(s) for s in events), unsafe_allow_html=True)
            status.update(label=f"{step['agent']} completed a hand-off · {len(events)} recorded")

        try:
            yield on_step
        except BaseException:
            status.update(label="Analysis interrupted · completed steps are shown below", state="error", expanded=True)
            raise
        else:
            graph.markdown(flow.svg(events, finished=True), unsafe_allow_html=True)
            status.update(label=f"Analysis complete · {len(events)} hand-offs recorded", state="complete", expanded=False)


def summary(res: dict) -> None:
    steps = res["trace"].steps
    e = res.get("explanation") or {}
    stored = res.get("stored") or {}
    source = {"bedrock": "Live Bedrock", "cache (explainer)": "Saved Bedrock answer", "template": "Offline template"}
    a, b, c = st.columns(3)
    a.metric("Recorded hand-offs", len(steps))
    b.metric("Explanation", source.get(e.get("source"), "Not generated"))
    c.metric("Evidence storage", {"s3": "Amazon S3", "local": "Local fallback", "none": "Not saved"}.get(
        stored.get("stored"), "Not saved"))


def render_record(res: dict, profile: dict, *, download_key: str = "activity_download") -> None:
    st.subheader("Your analysis, in motion")
    st.caption("Completed run · recorded actions, checks and sources. Times are UTC. No internal model reasoning.")
    summary(res)
    st.markdown(flow.svg(res["trace"].steps, finished=True), unsafe_allow_html=True)
    with st.expander("Profile used for this run"):
        st.json(profile, expanded=False)
    for i, step in enumerate(res["trace"].steps):
        st.markdown(event_html(step), unsafe_allow_html=True)
        if step.get("checks") or step.get("sources") or step.get("output") is not None:
            with st.expander(f"Evidence · {i + 1} · {step['agent']}"):
                if step.get("checks"):
                    st.dataframe(step["checks"], hide_index=True, width="stretch")
                if step.get("sources"):
                    st.write("Sources", step["sources"])
                if step.get("output") is not None:
                    st.json(step["output"], expanded=False)
    stored = res.get("stored") or {}
    if stored.get("stored") == "s3":
        st.success("Evidence saved to Amazon S3.")
    elif stored.get("stored") == "local":
        st.info("Evidence saved locally. Amazon S3 was not used for this run.")
    else:
        st.warning("The analysis completed, but its evidence has not been saved.")
    st.download_button("Download run hand-offs · JSON", res["trace"].to_json(),
                       file_name="alphaforge-activity.json", mime="application/json", key=download_key)


def render() -> None:
    from interface.core import services
    st.markdown('<div class="af-eyebrow">Analysis workspace / Activity</div>', unsafe_allow_html=True)
    if st.session_state.get("res"):
        render_record(st.session_state.res, st.session_state.get("profile", {}))
    else:
        st.title("See what happens behind your analysis")
        ui.notice("Run an analysis from Your profile. Its live hand-offs appear while it runs, and the full record stays here.")
    st.divider()
    st.subheader("Market data available to the engine")
    try:
        universe = services.loaded_universe()
        st.caption(f"{len(universe)} loaded products · this list reflects the enabled dataset, including any ingested additions. "
                   "Availability does not guarantee inclusion in a strategy; your profile and the engine's rules decide.")
        query = st.text_input("Find a product", placeholder="Ticker, name or asset class")
        if query:
            universe = universe[universe.astype(str).apply(
                lambda c: c.str.contains(query, case=False, regex=False)).any(axis=1)]
        st.dataframe(universe, hide_index=True, width="stretch")
    except (services.UserError, services.InternalError) as e:
        ui.notice(str(e), "warn")
