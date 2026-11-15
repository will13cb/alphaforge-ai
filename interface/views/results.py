"""Your results: the essentials first (limits, strategies, the explanation), then details for those who want them.
Every number is read from the engine's result; nothing is computed here."""

from __future__ import annotations

from dh.data import period_label

import re

import pandas as pd
import streamlit as st

from interface.core import services
from interface.ui import components as ui

S = st.session_state
VERDICT = {"pass": ("Approved by the checks", "good"), "warn": ("Approved, with points to know", "warn"),
           "fail": ("Not approved by the checks", "bad")}
STATUS = {"pass": "✔", "warn": "⚠", "fail": "✘"}


def pct(x, nd: int = 0) -> str:
    return "–" if x is None else f"{100 * x:.{nd}f}%"


def money(x) -> str:
    return "–" if x is None else f"{x:,.0f} $"


def unique(lines: list[str]) -> list[str]:
    """The engine may state a disclosure twice (with and without its check id): show it once."""
    out, seen = [], set()
    for x in lines:
        k = re.sub(r"^[A-Z]\d+[a-z]?:\s*", "", x).rstrip(". ").lower()
        if k not in seen:
            seen.add(k)
            out.append(re.sub(r"^[A-Z]\d+[a-z]?:\s*", "", x))
    return out


def essentials(res: dict, profile: dict) -> None:
    lim, strategies = res["limits"], res.get("strategies", [])
    name = profile.get("name") or "you"
    st.subheader(f"Your limits, {name}" if name != "You" else "Your limits")
    c = st.columns(3)
    ui.metric(c[0], pct(lim.get("loss_limit")), "the largest drop we plan for"
              + (f" (about {money(lim.get('loss_limit_cad'))})" if lim.get("loss_limit_cad") else ""))
    ui.metric(c[1], pct(lim.get("min_defensive")), "at least, kept in safer investments")
    ui.metric(c[2], pct(lim.get("horizon_max_growth")), "at most in stocks, given your horizon")
    st.write("")
    with st.expander("Why these limits?"):
        st.markdown("\n".join(f"{i}. {r}" for i, r in enumerate(lim.get("reasons", []), 1)) or "–")
        caps = services.caps_shown(res, profile)
        if caps:
            st.markdown("**At most in one company** (counted through the funds too): "
                        + ", ".join(f"{t} {v}" for t, v in caps.items()))

    st.subheader(f"{len(strategies)} way{'s' if len(strategies) != 1 else ''} to invest within these limits")
    st.markdown(f'<p class="af-muted">Simulated on {period_label()} market data, from the most growth your limits allow '
                'to the most prudent. Past ups and downs, not a forecast.</p>',
                unsafe_allow_html=True)
    for s in strategies:
        stt = s["stats"]
        with st.container(border=True):
            st.markdown(f"#### {s['name']}")
            st.markdown(f"**{pct(s['split']['growth'])} stocks · {pct(s['split']['defensive'])} safer investments**")
            r = s.get("split_range") or {}
            if r.get("set_by_text"):  # which constraint set the split (decision #33), as in app/app.py
                st.markdown(f'<p class="af-muted">Set by {r["set_by_text"]}'
                            + (f'; the worst-drop test alone would allow {pct(r["data_ceiling"])}.'
                               if r.get("set_by") != "worst_drop" and r.get("data_ceiling") is not None else ".")
                            + "</p>", unsafe_allow_html=True)
            m = st.columns(3)
            ui.metric(m[0], pct(stt.get("max_drawdown"), 1), f"worst drop, {period_label()}")
            ui.metric(m[1], pct(stt.get("return_2022"), 1), "result in 2022, a bad year")
            ui.metric(m[2], pct(stt.get("prob_loss")), "chance of ending below what you put in*")
            cons = unique(s.get("cons", []))
            if s.get("pros") or cons:
                st.markdown("\n".join([f"- ➕ {x}" for x in s.get("pros", [])] + [f"- ➖ {x}" for x in cons]))
            said = " ".join(cons).lower()
            bad = [c for c in s.get("checks", []) if c["status"] != "pass" and c["reason"].lower().rstrip(".") not in said]
            for c in bad[:3]:
                ui.notice(f"{STATUS[c['status']]} {c['reason'][:1].upper()}{c['reason'][1:]}",
                          "bad" if c["status"] == "fail" else "warn")
    if strategies:
        st.caption("\\* Without assuming past average returns repeat: only the past swings are replayed.")


def request(res: dict) -> None:
    c = res.get("request_comparison")
    if not c:
        return
    st.subheader("The investment you asked for")
    if c.get("not_assessable"):
        ui.notice("We have no market data for " + ", ".join(c["not_assessable"])
                  + ", so we can't measure its risk. It is left out.", "warn")
    a, f = c.get("as_asked"), c.get("fits")
    if a:
        cols = st.columns(2 if f else 1)
        with cols[0]:
            ui.card("As you asked", "")
            ui.metric(st, pct(a.get("max_drawdown"), 1), f"worst drop, about {money(a.get('drawdown_cad'))}")
            if a.get("fails"):
                ui.notice(f"{len(a['fails'])} of your limits would be broken.", "bad")
        if f:
            with cols[1]:
                ui.card("A version that fits your limits", "")
                ui.metric(st, pct(f.get("max_drawdown"), 1), f"worst drop, about {money(f.get('drawdown_cad'))}")
                ui.notice("Within your limits.", "good")
    if c.get("summary"):
        st.markdown(c["summary"])
    st.caption("The choice stays yours: this only shows what each version would have done.")


def explanation(res: dict) -> None:
    e = res.get("explanation") or {}
    if not e.get("text"):
        return
    st.subheader("In plain words")
    st.markdown(e["text"])
    src = {"bedrock": "Claude on Amazon Bedrock (live)", "cache (explainer)": "Claude on Amazon Bedrock (saved answer)",
           "template": "a fixed template (no AI model)"}.get(e.get("source"), e.get("source", ""))
    lab, tone = VERDICT.get(e.get("verdict"), ("", "info"))
    st.caption(f"Written by {src}. Every number in it was checked by code against the results." + (f" {lab}." if lab else ""))


def details(res: dict) -> None:
    st.subheader("Details")
    st.markdown('<p class="af-muted">For those who want to see how it was computed.</p>', unsafe_allow_html=True)
    ch = services.charts(res)
    with st.expander(f"How the strategies would have moved, {period_label()}"):
        if "growth" in ch:
            st.altair_chart(ch["growth"], width="stretch")
        else:
            st.caption("Chart unavailable.")
    for s in res.get("strategies", []):
        with st.expander(f"{s['name']}: what it holds and every check"):
            st.table(pd.DataFrame({"share": [pct(w, 1) for w in s["weights"].values()]}, index=list(s["weights"])))
            if ("split", s["key"]) in ch:
                st.altair_chart(ch[("split", s["key"])], width="stretch")
            if ("outcome", s["key"]) in ch:
                st.altair_chart(ch[("outcome", s["key"])], width="stretch")
            st.markdown("**Checks**")
            st.markdown("\n".join(f"- {STATUS[c['status']]} **{c['check']}** {c['reason']}" for c in s.get("checks", [])))
            g = s.get("guardian", {})
            if g:
                st.markdown(f"**Final rules (Guardian):** {VERDICT.get(g.get('verdict'), ('–',))[0]}")
            if s.get("adjustments"):
                st.markdown("**Why it holds this**\n" + "\n".join(f"- {x}" for x in s["adjustments"]))
    for s in res.get("dropped", []):
        ui.notice(f"“{s['name']}” was removed: it broke one of your limits.", "warn")
    with st.expander("Full record of every step (for review)"):
        st.caption("Each agent's hand-off: inputs, numbers, verdicts.")
        for i, step in enumerate(res["trace"].steps, 1):
            st.markdown(f"{i}. **{step.get('agent', '')} → {step.get('to', '')}**: {step.get('summary', '')}")
        st.download_button("Download the record (JSON)", res["trace"].to_json(), file_name="alphaforge-record.json",
                           mime="application/json")


def render() -> None:
    res, profile = S.get("res"), S.get("profile")
    if not res:
        ui.notice("No results yet. Answer the questions in “Your profile” and run the analysis.", "info")
        if st.button("Go to your profile", type="primary"):
            S.goto = "Your profile"
            st.rerun()
        return
    lab, tone = VERDICT.get(res.get("verdict"), ("", "info"))
    if res["limits"].get("missing"):
        ui.notice("Some answers are missing, so nothing could be proposed.", "bad")
        return
    if not res.get("strategies"):
        ui.notice("No strategy fits all your limits. The details below say which limit blocks.", "bad")
    else:
        ui.notice(f"<b>{ui.esc(lab)}.</b> Below: your limits, the strategies that respect them, and why.", tone, safe=True)
    essentials(res, profile)
    request(res)
    explanation(res)
    if res.get("strategies") and st.button("Ask the assistant about these results →", type="primary"):
        S.goto = "Assistant"
        st.rerun()
    st.divider()
    details(res)
