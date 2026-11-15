"""Your results: the essentials first (limits, strategies, the explanation), then details for those who want them.
Weights and metrics come from the engine; displayed CAD amounts are capital times weight."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from dh.agents.profiler import SCALE_NOTE
from dh.data import period_label
from interface.core import services
from interface.ui import components as ui
from interface.ui import flow
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


FUND_LABELS = {
    "ZST.TO": "Short-term bond fund", "XBB.TO": "Canadian bond fund",
    "XIU.TO": "Canadian stock fund", "SPY": "U.S. stock fund",
    "QQQ": "Nasdaq stock fund", "GLD": "Gold fund",
}


def investment_names() -> dict[str, str]:
    try:
        frame = services.loaded_universe()
        return dict(zip(frame["ticker"], frame["name"]))
    except (services.UserError, services.InternalError, KeyError):
        return {}  # saved results must remain readable without market-data files


def allocation_table(weights: dict, capital: float | None = None, names: dict | None = None) -> None:
    names = names or {}
    rows = []
    for ticker, weight in sorted(weights.items(), key=lambda item: (-item[1], item[0])):
        name = FUND_LABELS.get(ticker) or names.get(ticker)
        row = {"Investment": f"{name} ({ticker})" if name else ticker, "Share": pct(weight, 1)}
        if capital is not None:
            row["Amount (CAD)"] = money(float(capital) * weight)
        rows.append(row)
    total = {"Investment": "Total", "Share": pct(sum(weights.values()), 1)}
    if capital is not None:
        total["Amount (CAD)"] = money(float(capital) * sum(weights.values()))
    st.table(pd.DataFrame([*rows, total]).set_index("Investment"))


def essentials(res: dict, profile: dict) -> None:
    lim, strategies = res["limits"], res.get("strategies", [])
    name = profile.get("name") or "you"
    st.subheader(f"Your limits, {name}" if name != "You" else "Your limits")
    c = st.columns(3)
    ui.metric(c[0], pct(lim.get("loss_limit")), "loss limit used for your options"
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
        kyc = services.kyc_lines(lim)
        if kyc:
            st.markdown("**Cross-check: your three quick choices**\n" + "\n".join(f"- {ui.esc(x)}" for x in kyc),
                        unsafe_allow_html=True)

    st.subheader(f"{len(strategies)} way{'s' if len(strategies) != 1 else ''} to invest within these limits")
    st.markdown('<p class="af-muted">Compare how your money is split and how each option performed in the past. '
                'Bond funds can also lose value. Past performance does not predict future results.</p>',
                unsafe_allow_html=True)
    if strategies:
        # Side by side, one card per option, the same rows in the same order so they read across (on a phone,
        # Streamlit stacks the columns). Long text (pros, cons, checks) sits in an expander so the cards line up.
        st.markdown(CARD_CSS, unsafe_allow_html=True)
        names = investment_names()
        cols = st.columns(len(strategies), gap="small")
        for i, (col, s) in enumerate(zip(cols, strategies), 1):
            with col, st.container(border=True, key=f"af_card_{i}"):
                card(s, i, len(strategies), capital=profile.get("capital"), names=names)
        st.caption("\\* Without assuming past average returns repeat: only the past swings are replayed.")


CARD_CSS = """<style>
.block-container { max-width: 1240px; }
[class*="st-key-af_card_"] { border: 1px solid var(--line) !important; background: var(--panel); border-radius: 14px; }
.af-opt { font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; color: var(--mut); margin-bottom: .2rem; }
.af-opt-name { font-size: 1.15rem; font-weight: 600; line-height: 1.25; margin-bottom: .7rem; min-height: 2.9rem; }
.af-split { display: flex; height: 12px; border-radius: 999px; overflow: hidden; background: var(--line); }
.af-split .g { background: var(--acc); } .af-split .d { background: var(--c2); }
.af-split-l { display: flex; justify-content: space-between; font-size: .85rem; margin: .35rem 0 .8rem 0; }
.af-split-l b { font-size: 1.05rem; }
.af-row { display: flex; justify-content: space-between; align-items: baseline; gap: .6rem; padding: .45rem 0;
          border-top: 1px solid var(--line); }
.af-row .k { color: var(--mut); font-size: .88rem; line-height: 1.3; } .af-row .v { font-weight: 600; font-size: 1.1rem;
          white-space: nowrap; }
.af-setby { color: var(--mut); font-size: .82rem; line-height: 1.4; margin-top: .6rem; }
</style>"""


def card(s: dict, i: int, n: int, capital: float | None = None, names: dict | None = None) -> None:
    """One option: what it holds (bar), three numbers to compare, what set the split, then pros/cons on demand."""
    stt, g = s["stats"], s["split"]["growth"]
    gp = round(100 * g)
    tag = " · most growth" if i == 1 and n > 1 else " · least in stocks" if i == n and n > 1 else ""
    st.markdown(
        f'<div class="af-opt">Option {i} of {n}{tag}</div><div class="af-opt-name">{ui.esc(s["name"].split(":", 1)[0])}</div>'
        f'<div class="af-split" role="img" aria-label="{gp}% stocks, {100 - gp}% safer investments">'
        f'<div class="g" style="width:{gp}%"></div><div class="d" style="width:{100 - gp}%"></div></div>'
        f'<div class="af-split-l"><span><b>{gp}%</b> stocks</span><span><b>{100 - gp}%</b> safer</span></div>'
        + "".join(f'<div class="af-row"><span class="k">{ui.esc(k)}</span><span class="v">{ui.esc(v)}</span></div>'
                  for k, v in [(f"Worst drop, {period_label()}", pct(stt.get("max_drawdown"), 1)),
                               ("Result in 2022, a bad year", pct(stt.get("return_2022"), 1)),
                               ("Chance of ending below what you put in*", pct(stt.get("prob_loss")))]),
        unsafe_allow_html=True)
    weights = s.get("weights") or {}
    if weights:
        st.markdown("**How your money is split**")
        allocation_table(weights, capital, names)
    r = s.get("split_range") or {}
    reason = {
        "horizon": "Your investment timeframe limits how much can go into stocks.",
        "level": "This option puts less in stocks than the first option.",
        "worst_drop": "The loss checks limit how much can go into stocks.",
    }.get(r.get("set_by"))
    if reason:
        st.caption(reason)
    pros, cons = s.get("pros", []), unique(s.get("cons", []))
    said = " ".join(cons).lower()
    bad = [c for c in s.get("checks", []) if c["status"] != "pass" and c["reason"].lower().rstrip(".") not in said]
    if pros or cons or bad:
        with st.expander("Benefits and things to know"):
            if pros:
                st.markdown("**Benefits**\n" + "\n".join(f"- {x}" for x in pros))
            if cons:
                st.markdown("**Things to know**\n" + "\n".join(f"- {x}" for x in cons))
            for c in bad[:3]:
                ui.notice(f"{STATUS[c['status']]}: {c['reason'][:1].upper()}{c['reason'][1:]}",
                          "bad" if c["status"] == "fail" else "warn")


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
    if e.get("source") == "fixed_rate":
        st.caption("Calculated from the sourced bond terms and stated purchase-price assumptions. No AI model invents the rate.")
    else:
        st.caption(f"Written by {src}. Every number in it was checked by code against the results." + (f" {lab}." if lab else ""))


def details(res: dict) -> None:
    st.subheader("More about your options")
    st.caption("Explore past performance. The calculation details are available below if you want to review them.")
    ch = services.charts(res)
    with st.expander(f"How the strategies would have moved, {period_label()}"):
        if "growth" in ch:
            ui.chart(ch["growth"])
        else:
            st.caption("Chart unavailable.")
    names = investment_names()
    for s in res.get("strategies", []):
        with st.expander(f"{s['name'].split(':', 1)[0]} — details"):
            st.markdown("**How your money is split**")
            allocation_table(s["weights"], (S.get("profile") or {}).get("capital"), names)
            with st.expander("How this option was calculated (technical)"):
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
    if res.get("fixed_income_scenario"):
        from interface.ui.fixed_income import render_plan
        st.title("Your bond portfolio")
        render_plan(res["fixed_income_scenario"])
        explanation(res)
        with st.expander("Analysis record"):
            st.json(res["trace"].steps, expanded=False)
        return
    lab, tone = VERDICT.get(res.get("verdict"), ("", "info"))
    if res["limits"].get("missing"):
        ui.notice("Some answers are missing, so nothing could be proposed.", "bad")
        return
    if not res.get("strategies"):
        ui.notice("No strategy fits all your limits. The details below say which limit blocks.", "bad")
    else:
        ui.notice("These options fit the limits checked. Review the points to know before choosing.", tone)
    st.title("Your investment overview")
    st.markdown(flow.svg(res["trace"].steps, finished=True), unsafe_allow_html=True)  # the agent graph, always shown
    if st.button("See how this analysis was built →"):
        S.goto = "Activity"
        st.rerun()
    overview, summary, evidence = st.tabs(["Your options", "In plain words", "Details"])
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

