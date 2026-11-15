"""Your results: the essentials first (limits, strategies, the explanation), then details for those who want them.
Every number is read from the engine's result; nothing is computed here."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from dh.agents.profiler import SCALE_NOTE
from dh.data import period_label
from interface.core import services
from interface.ui import components as ui
from interface.ui.explanation import format_explanation
from interface.ui import voice as voice_ui

S = st.session_state
VERDICT = {"pass": ("Approved by the checks", "good"), "warn": ("Approved, with points to know", "warn"),
           "fail": ("Not approved by the checks", "bad")}
STATUS = {"pass": "Passed", "warn": "To know", "fail": "Not met"}


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
    ui.metric(c[0], pct(lim.get("loss_limit")), "loss threshold used in the simulations"
              + (f" (about {money(lim.get('loss_limit_cad'))})" if lim.get("loss_limit_cad") else ""))
    ui.metric(c[1], pct(lim.get("min_defensive")), "at least, kept in safer investments")
    ui.metric(c[2], pct(lim.get("horizon_max_growth")), "at most in stocks, given your horizon")
    st.write("")
    with st.expander("Why these limits?"):
        st.caption(SCALE_NOTE)
        st.markdown("\n".join(f"{i}. {r}" for i, r in
                              enumerate(lim.get("reasons_plain") or lim.get("reasons", []), 1)) or "–")
        caps = services.caps_shown(res, profile)
        if caps:
            st.markdown("**Largest share of the portfolio any one company may take** (counted through the funds too): "
                        + ", ".join(f"{t} {v}" for t, v in caps.items()))

    st.subheader(f"{len(strategies)} way{'s' if len(strategies) != 1 else ''} to invest within these limits")
    st.markdown(f'<p class="af-muted">Simulated on {period_label()} market data, from the most growth your limits allow '
                'to the least in stocks. Less in stocks did not always mean smaller past drops: compare them. Past ups and downs, not a forecast.</p>',
                unsafe_allow_html=True)
    for s in strategies:
        stt = s["stats"]
        with st.container(border=True):
            st.markdown(f"#### {s['name']}")
            st.markdown(f"**{pct(s['split']['growth'])} stocks · {pct(s['split']['defensive'])} safer investments**")
            r = s.get("split_range") or {}
            if r.get("set_by_text"):  # which constraint set the split (decision #33), as in app/app.py
                st.markdown(f'<p class="af-muted">Set by {r["set_by_text"]}'
                            + (f'; the loss test alone would allow {pct(r["data_ceiling"])}.'
                               if r.get("set_by") != "worst_drop" and r.get("data_ceiling") is not None else ".")
                            + "</p>", unsafe_allow_html=True)
            m = st.columns(3)
            ui.metric(m[0], pct(stt.get("max_drawdown"), 1), f"worst drop, {period_label()}")
            ui.metric(m[1], pct(stt.get("return_2022"), 1), "result in 2022, a bad year")
            ui.metric(m[2], pct(stt.get("prob_loss")), "chance of ending below what you put in*")
            cons = unique(s.get("cons", []))
            if s.get("pros") or cons:
                st.markdown("\n".join([f"- **For:** {x}" for x in s.get("pros", [])] + [f"- **Against:** {x}" for x in cons]))
            said = " ".join(cons).lower()
            bad = [c for c in s.get("checks", []) if c["status"] != "pass" and c["reason"].lower().rstrip(".") not in said]
            for c in bad[:3]:
                ui.notice(f"{STATUS[c['status']]}: {c['reason'][:1].upper()}{c['reason'][1:]}",
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
    for lab in c.get("stand_ins") or []:
        ui.notice(f"Not in our data: {lab}.", "info")
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
                ui.notice("Within the checked limits." if f.get("verdict") != "fail" else "This adjusted version still breaks a checked limit; see the evidence.",
                          "good" if f.get("verdict") != "fail" else "bad")
    if c.get("summary"):
        st.markdown(c["summary"])
    st.caption("The choice stays yours: this only shows what each version would have done.")


def existing(res: dict) -> None:
    """Branch portefeuille_existant: the portfolio the person already owns, reviewed, then rebuilt."""
    r = res.get("existing_review")
    if not r:
        return
    st.subheader("The portfolio you already have")
    if r.get("error"):
        ui.notice(r["summary"], "warn")
        return
    if r.get("not_assessable"):
        ui.notice("We have no market data for " + ", ".join(r["not_assessable"])
                  + ", so it is left out of the numbers below.", "warn")
    for si in r.get("stand_ins") or []:
        h = (si.get("hedge_effect") or {}).get("max_drawdown")
        ui.notice(f"{si['ticker']} is not in our data: measured with {si['measured_with']} ({si['closeness']})"
                  + (", with its currency hedge simulated" if si["hedged"] else "")
                  + (f": worst drop {pct(h['hedged'], 1)} hedged vs {pct(h['unhedged'], 1)} without the hedge" if h else "")
                  + (f". Checked against {si['ticker']}'s own prices ({si['checked_against_real']['window']}): real worst "
                     f"drop {pct(si['checked_against_real']['real_worst_drop'], 1)}, stand-in "
                     f"{pct(si['checked_against_real']['stand_in_worst_drop'], 1)}" if si.get("checked_against_real") else "")
                  + ".", "info")
    if r.get("stand_ins"):
        st.caption("Stand-in limits: " + r.get("limits_of_stand_ins", ""))
    c, t = r.get("current"), r.get("target")
    if not c:
        return
    cols = st.columns(2 if t else 1)
    with cols[0]:
        ui.card("Today", "")
        ui.metric(st, pct(c.get("max_drawdown"), 1), f"worst drop, about {money(c.get('drawdown_cad'))}")
        ui.notice(f"{len(c['fails'])} of your limits broken." if c.get("fails") else "Within your limits.",
                  "bad" if c.get("fails") else "good")
    if t:
        with cols[1]:
            ui.card(f"Rebuilt: {t['name']}", "")
            ui.metric(st, pct(t.get("max_drawdown"), 1), f"worst drop, about {money(t.get('drawdown_cad'))}")
            ui.notice(f"{len(t['fails'])} of your limits broken." if t.get("fails") else "Within your limits.",
                      "bad" if t.get("fails") else "good")
    st.markdown("**What we see**\n" + "\n".join(f"- {ui.esc(x)}" for x in r.get("critique", [])),
                unsafe_allow_html=True)
    objections = [o for o in (r.get("critic") or {}).get("objections", []) if o["status"] == "disclosed"]
    if objections:
        st.markdown("**The Critic's points** (each checked with a tool; " + ui.esc((r.get("critic") or {}).get("source", ""))
                    + ")\n" + "\n".join(f"- {ui.esc(o.get('claim', ''))}" for o in objections), unsafe_allow_html=True)
    if r.get("moves"):
        st.markdown("**From today to the rebuilt version (simulation, nothing is bought or sold)**")
        df = pd.DataFrame(r["moves"])
        df["held"] = df["held"].map(lambda h: ", ".join(h) if h else "")
        st.dataframe(df[["ticker", "held", "now_cad", "target_cad", "change_cad", "action"]].rename(columns={
            "ticker": "Holding", "held": "You hold it as", "now_cad": "Today ($)", "target_cad": "Rebuilt ($)",
            "change_cad": "Change ($)", "action": "Action"}), hide_index=True, width="stretch")
        for m in r["moves"]:
            if m.get("note"):
                st.caption(f"{m['ticker']}: {m['note']}.")
    st.caption("The choice stays yours: this only shows what each version would have done.")


def explanation(res: dict) -> None:
    e = res.get("explanation") or {}
    if not e.get("text"):
        return
    st.header("Your investment summary")
    st.markdown(format_explanation(e["text"], res.get("strategies")))
    voice_ui.read_aloud(e["text"], "results_explanation")
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
            ui.chart(ch["growth"])
        else:
            st.caption("Chart unavailable.")
    for s in res.get("strategies", []):
        with st.expander(f"{s['name']}: what it holds and every check"):
            st.table(pd.DataFrame({"share": [pct(w, 1) for w in s["weights"].values()]}, index=list(s["weights"])))
            if ("split", s["key"]) in ch:
                ui.chart(ch[("split", s["key"])])
            if ("outcome", s["key"]) in ch:
                ui.chart(ch[("outcome", s["key"])])
            st.markdown("**Checks**")
            st.markdown("\n".join(f"- <span class=\"af-st {c['status']}\">{STATUS[c['status']]}</span> **{ui.esc(c['check'])}** "
                                  f"{ui.esc(c['reason'])}" for c in s.get("checks", [])), unsafe_allow_html=True)
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
    st.title("Your investment overview")
    if st.button("See how this analysis was built →"):
        S.goto = "Activity"
        st.rerun()
    overview, summary, evidence = st.tabs(["Strategies & limits", "Plain-language summary", "Checks & holdings"])
    with overview:
        essentials(res, profile)
        request(res)
        existing(res)
    with summary:
        explanation(res)
    with evidence:
        details(res)
    if res.get("strategies") and st.button("Ask the assistant about these results →", type="primary"):
        S.goto = "Assistant"
        st.rerun()

