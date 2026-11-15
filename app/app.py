"""Demo application (a deliverable, due Sun 23:59). Run: make app   (needs the starter CSVs in data/raw/: make data)

Thin on purpose: it runs the real pipeline (`pipeline.run` → `explainer.add_to_trace`) and SHOWS the result; follow-up
questions go to the Analyst (`analyst.ask`, decision #35), whose what-ifs re-run the pipeline. No number is
computed here; everything is read from the pipeline result, so the screen, the trace and the text agree (G12).
Offline (LLM_PROVIDER=mock, the default) the Explainer replays the committed Opus texts in cache/explainer/ when the
facts match, else the deterministic template; with LLM_PROVIDER=bedrock it calls Claude on Amazon Bedrock.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from dh import bootstrap, data, tracestore
from dh.agents import analyst, explainer, extractor, market_charts, pipeline, profiler
from dh.agents import checks as ck
from dh.agents import portfolio_charts as pc
from dh.agents.scenarios import DEMO_LABELS, DEMO_PROFILES
from dh.agents.trace import ICON
from dh.personas import DISCLAIMER, PERSONAS, describe

st.set_page_config(page_title="AlphaForge AI", page_icon=":material/account_balance:", layout="wide")
from dh import i18n  # noqa: E402  (Français / English, decision #49)
i18n.install()
i18n.language_selector()  # top of the sidebar, before anything can stop the page

# One look for both front ends: the interface's colour tokens, light/dark modes and styles (interface/ui/theme.py),
# plus what a wide, tabbed jury view needs. The mode follows the sidebar switch (session state `dark_mode`).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from interface.ui import theme  # noqa: E402
from interface.ui.activity import live_run, render_record  # noqa: E402
from interface.ui.explanation import format_explanation  # noqa: E402

MODE = theme.mode(st.session_state)

st.markdown(theme.css(MODE) + """
<style>
.block-container { max-width: 1320px; padding-top: 2.6rem; }
.af-h1 { font-size: 2.3rem; font-weight: 500; color: var(--ink); margin: 0 0 .5rem 0; line-height: 1.15;
         letter-spacing: -0.015em; font-family: """ + theme.palette(MODE)["heading"] + """; }
.af-flow { display: flex; flex-wrap: wrap; gap: 6px; margin: .3rem 0 1rem 0; }
.af-flow span { font-size: .8rem; padding: 3px 11px; border-radius: 999px; background: var(--panel);
                border: 1px solid var(--line); color: var(--mut); }
.af-flow span.ai { border-color: var(--acc); color: var(--ink); background: var(--sel_bg); }
div[data-testid="stMetric"] { background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
                              padding: .6rem .8rem; }
div[data-testid="stTabs"] button[role="tab"] p { font-size: 1rem; font-weight: 600; }
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p { color: var(--ink); }
div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] { background: var(--acc); }
div[data-testid="stVerticalBlockBorderWrapper"] { background: var(--panel); border-radius: 12px; }
div[data-testid="stMetricValue"] > div { font-size: 1.55rem; overflow: visible; }
div[data-testid="stMetricLabel"] p { white-space: normal; overflow: visible; font-size: .85rem; color: var(--mut); }
/* Verdict boxes: the mode's panel with a coloured edge (Streamlit's own pastel fills are unreadable in dark mode) */
div[data-testid="stAlertContainer"] { background: var(--panel) !important; border: 1px solid var(--line);
                                     border-left: 4px solid var(--mut); border-radius: 10px; }
div[data-testid="stAlertContainer"] * { color: var(--ink) !important; }
div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) { border-left-color: var(--good); }
div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) { border-left-color: var(--warn); }
div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) { border-left-color: var(--bad); }
</style>""", unsafe_allow_html=True)


def chart(ch, **kw):
    """An engine chart in the current mode (theme.style_chart): same data, the page's colours."""
    st.altair_chart(theme.style_chart(ch, MODE), theme=None, **kw)

VERDICT = {"pass": ("✔ approved", st.success), "warn": ("⚠ approved with disclosures", st.warning),
           "fail": ("✘ sent back", st.error)}
FOLLOW_UPS = ["What if I put 10% in Tesla?", "Et si mon horizon était de 8 ans ?",
              "Quel rendement me faut-il pour avoir 450 000 $ ?", "NVDA et QQQ, c'est le même pari ?",
              "How would my strategy have done in 2022?"]
SOURCE = {"bedrock": "Claude Opus 5.5 on Amazon Bedrock, live",
          "cache (explainer)": "Claude Opus 5.5 on Amazon Bedrock, replayed from the cache (no AWS call now)",
          "template": "deterministic template (no LLM)"}
PROFILE_FIELDS = [("age", "Age"), ("horizon_years", "Horizon (years)"), ("objective", "Objective"),
                  ("capital", "Capital (CAD)"), ("monthly_contribution", "Monthly contribution (CAD)"),
                  ("target_amount", "Target amount (CAD)"), ("max_loss_pct", "Largest loss accepted (%)"),
                  ("loss_reaction", "Reaction to a 20% drop"), ("emergency_fund_months", "Emergency fund (months)"),
                  ("income_stability", "Income"), ("withdrawal_share_3y", "Share needed within 3 years"),
                  ("knowledge_level", "Declared knowledge"), ("years_experience", "Years investing"),
                  ("products_held", "Products held"), ("interests", "Interests"), ("exclusions", "Exclusions"),
                  ("requested_positions", "Request")]


def unique(items: list[str]) -> list[str]:
    """Drop repeats that differ only by a check id ("C2: Canada 80%…" from the checks and "Canada 80%…" from the
    Critic's objection say the same thing)."""
    seen, out = set(), []
    for x in items:
        k = re.sub(r"^[A-Z]\d*b?:\s*", "", x).strip().rstrip(".").lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def pct(x, nd: int = 1) -> str:
    return "–" if x is None else f"{100 * x:.{nd}f}%"


def fmt(k: str, v) -> str:
    if v is None or v == [] or v == {}:
        return "–"
    if k == "requested_positions":
        return ", ".join(f"{t} {w:.0%}" for t, w in v.items())
    if k == "withdrawal_share_3y":
        return f"{v:.0%}"
    if isinstance(v, list):
        return ", ".join(str(x).replace("_", " ") for x in v)
    if isinstance(v, (int, float)) and k in ("capital", "monthly_contribution", "target_amount"):
        return f"{v:,.0f} $"
    return str(v).replace("_", " ")


def run_profile(profile_json: str, ex_json: str = "", answered: tuple = (), persona: str = "") -> tuple[dict, dict]:
    """Cached by the profile itself, so a free-text client with the same facts reuses the run. Each run is saved to
    Amazon S3 (`tracestore`, decision #25; local copy if S3 isn't reachable, never blocks the screen)."""
    cache = st.session_state.setdefault("analysis_runs", {})
    cache_key = (profile_json, ex_json, answered, persona)
    if cache_key in cache:
        st.caption("Saved session result · open Activity & evidence to inspect its recorded hand-offs. Re-run for live activity.")
        return cache[cache_key]
    profile = json.loads(profile_json)
    with live_run() as on_step:
        res = pipeline.run(profile, on_step=on_step)
        try:
            explainer.add_to_trace(res, profile)
            if ex_json:
                extractor.add_to_trace(res, json.loads(ex_json), list(answered))
            tracestore.save_run_safe(res, profile, persona=persona)
        finally:
            res["trace"].on_step = None
    cache[cache_key] = (profile, res)
    return profile, res


SAMPLE_TEXT = ("I'm 59 and I'm retiring in about 4 years. I have $400,000 saved and 12 months of expenses set aside; "
               "my job in a hospital is stable. I've been an experienced investor for 20 years of experience. I can't "
               "lose more than 15%, and if markets dropped I'd hold. Everyone talks about Tesla: put 25% of my "
               "savings in Tesla. No crypto.")
WIDGETS = {  # follow-up questions the client answers in the form (rules.ESSENTIAL_FIELDS)
    "age": lambda q: st.number_input(q, 18, 100, 40),
    "horizon_years": lambda q: st.number_input(q, 0.5, 60.0, 10.0, step=0.5),
    "objective": lambda q: st.selectbox(q, extractor.ENUMS["objective"], format_func=lambda v: v.replace("_", " ")),
    "loss_reaction": lambda q: st.selectbox(q, extractor.ENUMS["loss_reaction"], index=2,
                                            format_func=lambda v: v.replace("_", " ")),
    "max_loss_pct": lambda q: float(st.slider(q, 0, 60, 20, format="%d%%")),
    "emergency_fund_months": lambda q: st.number_input(q, 0.0, 120.0, 6.0, step=1.0),
    "income_stability": lambda q: st.selectbox(q, extractor.ENUMS["income_stability"]),
    "knowledge_level": lambda q: st.selectbox(q, extractor.ENUMS["knowledge_level"], index=2),
}


def free_text_client() -> tuple[str, str, tuple] | None:
    """Free text → Extractor → follow-up questions → (profile_json, ex_json, answered); None until complete."""
    st.subheader("Describe yourself in your own words")
    st.caption("The Extractor (a Strands agent on Amazon Bedrock; offline, a rule-based parser) only pulls out facts. "
               "Code checks every field and keeps a number only if you wrote it; anything missing is asked, never guessed.")
    text = st.text_area("Your situation and what you'd like", SAMPLE_TEXT, height=130)
    if st.button("Read my words", type="primary") or st.session_state.get("ex_text") != text and "ex" in st.session_state:
        with st.spinner("Extractor reading…"):
            st.session_state.ex, st.session_state.ex_text = extractor.extract(text), text
    ex = st.session_state.get("ex")
    if not ex:
        return None
    src = {"bedrock": "Strands agent on Amazon Bedrock", "rules": "rule-based parser (offline)"}.get(ex["source"], ex["source"])
    st.caption(f"Read by: **{src}**" + (f" · `{ex['model']}`" if ex["model"] else "")
               + (f" · {ex['check_calls']} self-check(s)" if ex["check_calls"] else "")
               + (f" · {ex['note']}" if ex["note"] and ex["source"] != "rules" else ""))
    shown = [(lab, fmt(k, ex["profile"].get(k))) for k, lab in PROFILE_FIELDS if k in ex["profile"]]
    st.table(pd.DataFrame(shown or [("–", "nothing found")], columns=["understood", "value"]).set_index("understood"))
    for n in ex["notes"]:
        st.caption(f"✘ dropped by the checks: {n}")
    answers = {}
    if ex["missing"]:
        with st.form("follow_up"):
            st.markdown(f"**{len(ex['missing'])} question(s) before any proposal** (KYC essentials, Guardian G1):")
            for q in ex["questions"]:
                answers[q["field"]] = WIDGETS[q["field"]](q["question"])
            if st.form_submit_button("Answer and run the agents"):
                st.session_state.answers = {ex["hash"]: answers}  # kept across reruns (clicks in the results)
        answers = st.session_state.get("answers", {}).get(ex["hash"])
        if answers is None:
            return None
    profile = {**ex["profile"], **answers}
    return json.dumps(profile, sort_keys=True), json.dumps(ex, sort_keys=True, default=str), tuple(answers)


@st.cache_data(show_spinner=False)
def growth_df(strategies: dict[str, dict[str, float]]) -> pd.DataFrame:
    return market_charts.growth_data(strategies)


# ---- data present? --------------------------------------------------------------------------------------
# Hosted copy (Streamlit Cloud, AF_AUTO_DATA=1): build data/raw/ with the organizers' script on the first start.
if not bootstrap.data_present() and os.getenv("AF_AUTO_DATA") == "1":
    with st.spinner("First start: downloading the market data with the organizers' script (1-2 minutes)…"):
        bootstrap.ensure_data()
try:
    data.prices()
except SystemExit as e:
    st.title("AlphaForge AI")
    st.error(f"Starter data not found ({e}).")
    st.markdown("Put the starter-pack CSVs in `data/raw/` first:\n\n```bash\nmake data\n```\n\n"
                "(copies them from `Datathon2026Infos/alphaforge_starter/` if they are there, else rebuilds them from "
                "Yahoo Finance, Bank of Canada and FRED). Then reload this page.")
    st.stop()

# ---- sidebar ---------------------------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="af-brand"><span class="mark"></span>AlphaForge AI</div>', unsafe_allow_html=True)
    st.caption("Fictional clients · simulation only")
    key = st.radio("Fictional client", [*DEMO_PROFILES, "free_text"],
                   format_func=lambda k: DEMO_LABELS.get(k, "Describe yourself (free text)"))
    pkey = key.split("_")[0]
    if pkey in PERSONAS:
        st.markdown(describe(pkey).replace("\n", "  \n"))
    if st.button("Re-run the agents"):
        st.session_state.pop("analysis_runs", None)
        st.session_state.pop("ex", None)
    st.divider()
    st.toggle("Dark mode", key="dark_mode", help="Switch between the light and the dark display.")
    st.caption(f"Extractor and Explainer: `{explainer.model_id()}` · LLM_PROVIDER `{os.getenv('LLM_PROVIDER', 'mock')}`")
    st.caption("Run traces: Amazon S3" if os.getenv("S3_BUCKET") else "Run traces: local copy (S3_BUCKET not set)")
    st.caption(DISCLAIMER)

if key == "free_text":
    args = free_text_client()
    if args is None:
        st.stop()
    st.divider()
    profile, res = run_profile(*args, persona="free_text")
    run_key = args[0]
else:
    run_key = json.dumps(DEMO_PROFILES[key], sort_keys=True)
    profile, res = run_profile(run_key, persona=key)
LABEL = data.period_label()
limits, strategies, e = res["limits"], res.get("strategies", []), res.get("explanation", {})

# ---- header ----------------------------------------------------------------------------------------------
st.markdown('<div class="af-eyebrow">AlphaForge AI · simulation</div>'
            '<div class="af-h1">An investment analyst that can say no</div>'
            '<div class="af-flow"><span>Profiler · rules</span><span>Market data</span><span>Portfolio · ≤ 3 risk levels'
            '</span><span>Guardian · G1–G18</span><span class="ai">Critic · Claude on Bedrock</span>'
            '<span class="ai">Explainer · Claude on Bedrock</span><span>Guardian · G11–G13</span>'
            '<span class="ai">Analyst · follow-ups</span></div>'
            '<p class="af-muted">Agents argue, code enforces: every limit, number and verdict below comes from code; '
            'the AI agents investigate, explain and answer questions inside those rules.</p>',
            unsafe_allow_html=True)
label, box = VERDICT[res["verdict"]]
box(f"Guardian on the proposals: {label}. {len(strategies)} strateg{'y' if len(strategies) == 1 else 'ies'} kept"
    + (f", {len(res.get('dropped', []))} dropped" if res.get("dropped") else "") + ".")

tab_p, tab_s, tab_e, tab_a, tab_t = st.tabs(["Profile & limits", "Strategies", "Explanation", "Follow-up (Analyst)",
                                             "Activity & evidence"])
followups = st.session_state.setdefault("followups", {}).setdefault(run_key, [])

# ---- 1. profile and limits -------------------------------------------------------------------------------
with tab_p:
    if limits.get("missing"):
        st.error("Profile incomplete, the Profiler asks before proposing anything: " + ", ".join(limits["missing"]))
    left, right = st.columns([2, 3])
    with left:
        st.subheader(f"What {profile.get('name', 'the client')} told us")
        st.caption("Facts (`profile`): entered or extracted, never scored by an LLM.")
        st.table(pd.DataFrame([(lab, fmt(k, profile.get(k))) for k, lab in PROFILE_FIELDS if k in profile],
                              columns=["", "value"]).set_index(""))
    with right:
        st.subheader("What the Profiler concluded")
        st.caption(f"Conclusions (`limits`): computed by rules from the facts and the {LABEL} data; same answers, same limits.")
        if not limits.get("missing"):
            c = st.columns(4)
            # short values only: st.metric truncates long ones in a 4-column row (seen in the screenshots)
            c[0].metric(f"Risk level · {limits['risk_name']}", f"{limits['risk_level']}/5")
            c[1].metric("Loss limit", pct(limits["loss_limit"], 0))
            c[2].metric("Defensive at least", pct(limits["min_defensive"], 0))
            c[3].metric("Crypto at most", pct(limits["max_crypto"]))
            st.caption(f"Risk tolerance {limits['risk_tolerance']}/5, capacity to take risk {limits['risk_capacity']}/5 "
                       f"→ risk level {limits['risk_level']}/5 ({limits['risk_name']}). Loss limit "
                       + (f"{limits['loss_limit_cad']:,} $, " if limits.get("loss_limit_cad") else "")
                       + f"set by your {limits['loss_limit_source']}. At most {pct(limits['horizon_max_growth'], 0)} "
                       f"in stocks for your horizon. Investing knowledge {limits['knowledge_score']}/5.")
            caps = explainer._caps_shown(strategies, limits, profile)
            if caps:
                st.markdown(f"**Largest share of the portfolio any one company may take** (its own cap, from its worst "
                            f"drop in the data ({LABEL}) and your limits, counted through the ETFs too): " + ", ".join(f"{t} {v}" for t, v in caps.items()))
            for r in limits.get("request_checks") or []:
                st.warning(f"**Your request: {r['ticker']} {pct(r['asked'], 0)} doesn't fit your limits.** "
                           + r["reason"][:1].upper() + r["reason"][1:] + ".")
        st.markdown("**Why these limits**")
        st.caption(profiler.SCALE_NOTE)
        st.markdown("\n".join(f"{i}. {x}" for i, x in
                              enumerate(limits.get("reasons_plain") or limits.get("reasons", []), 1)) or "–")

# ---- 2. strategies ---------------------------------------------------------------------------------------
with tab_s:
    if res.get("fixed_income_scenario"):
        from interface.ui.fixed_income import render_plan
        render_plan(res["fixed_income_scenario"])
    elif not strategies:
        st.info("No strategy: see the Profile tab and the Trace.")
    cols = st.columns(max(1, len(strategies)))
    for col, s in zip(cols, strategies):
        with col.container(border=True):
            stt, r = s["stats"], s["split_range"]
            st.subheader(s["name"])
            st.markdown(f"### {s['split']['growth']:.0%} / {s['split']['defensive']:.0%}")
            st.caption("growth / defensive" + (f" · goal floor {pct(r['floor'], 0)}" if r.get("floor") is not None else ""))
            if r.get("set_by_text"):
                st.markdown(f"<small>**Set by** {r['set_by_text']}"
                            + (f". The loss test alone would allow {pct(r['data_ceiling'], 0)}."
                               if r.get("set_by") != "worst_drop" and r.get("data_ceiling") is not None else ".")
                            + "</small>", unsafe_allow_html=True)
            if r.get("conflict_message"):
                st.error(r["conflict_message"])
            m = st.columns(2)
            m[0].metric(f"Worst drop {LABEL}", pct(stt.get("max_drawdown")))
            m[1].metric("Return in 2022", pct(stt.get("return_2022")))
            m = st.columns(2)
            m[0].metric("Volatility", pct(stt.get("ann_vol")))
            m[1].metric("Chance of a loss*", pct(stt.get("prob_loss"), 0))
            st.markdown("<small>**More growth, deeper worst drop** (past data, not a forecast)</small>",
                        unsafe_allow_html=True)
            chart(pc.split_curve_chart(pc.split_curve_data(s), limits, s, title=False), width="stretch")
            g = s.get("guardian", {})
            gl, gbox = VERDICT[g.get("verdict", "pass")]
            gbox(f"Guardian: {gl}")
            st.caption("Checks C–F: " + ck.summary(s.get("checks", [])))
            bad = [c for c in s.get("checks", []) if c["status"] != "pass"]
            with st.expander(f"Checks to disclose ({len(bad)})" if bad else "All checks C–F"):
                for c in (bad or s.get("checks", [])):
                    st.markdown(f"{ICON[c['status']]} **{c['check']}**: {c['reason']}  \n<small>source: "
                                f"{c['source']}</small>", unsafe_allow_html=True)
            with st.expander("What it holds"):
                st.table(pd.DataFrame({"weight": [pct(w) for w in s["weights"].values()]}, index=list(s["weights"])))
            with st.expander("Why it holds this"):
                st.markdown("\n".join(f"- {a}" for a in s.get("adjustments", [])))
            cons = unique(s.get("cons", []))
            if s.get("pros") or cons:
                st.markdown("\n".join([f"- **+** {x}" for x in s.get("pros", [])] + [f"- **−** {x}" for x in cons]))
    if strategies:
        st.caption(f"* Chance of ending below what was put in, 'risk only' view: the {LABEL} swings without assuming "
                   "their average return repeats. Simulation, not a forecast.")
        chart(market_charts.growth_chart(growth_df({s["name"]: s["weights"] for s in strategies})),
                        width="stretch")
        for s in strategies:
            df = pc.outcome_frame(s)
            if df is not None:
                st.markdown(f"<small>**{s['name']}**</small>",
                            unsafe_allow_html=True)
                chart(market_charts.outcome_chart(df), height=230)  # Streamlit theme squashed its rows
    for s in res.get("dropped", []):
        st.error(f"'{s['name']}' dropped by the Guardian: "
                 + ", ".join(f"{c['rule']} {c['detail']}" for c in s["guardian"]["checks"] if c["status"] == "fail"))

# ---- 3. explanation --------------------------------------------------------------------------------------
with tab_e:
    if e:
        src = SOURCE.get(e["source"], e["source"])
        st.caption(f"Written by: **{src}**" + (f" · `{e['model']}`" if e.get("model") else "")
                   + (f" · {e['check_calls']} self-check(s) with the Guardian's rules" if e.get("check_calls") else ""))
        if e.get("note") and e["note"] != "mock mode":
            st.caption(f"Note: {e['note']}")
        st.markdown(format_explanation(e["text"], strategies))
        st.divider()
        lab, box = VERDICT[e["verdict"]]
        st.markdown(f"**Guardian on this text:** {lab}")
        for c in e["checks"]:
            st.markdown(f"{ICON[c['status']]} **{c['rule']}** {c['text']}: {c['detail']}")
    else:
        st.info("No explanation: the profile is incomplete (see the Trace).")

# ---- 4. follow-up questions (Analyst) -------------------------------------------------------------------------
with tab_a:
    st.caption("Ask what you'd change. The Analyst (a Strands agent on Amazon Bedrock; offline, a deterministic analyst) "
               "decides which tools to call: its what-ifs RE-RUN the whole pipeline, Guardian included, and code checks "
               "every number in its answer (it must come from a tool result). English or French.")
    if limits.get("missing") or not strategies:
        st.info("Follow-ups need a complete profile and at least one strategy.")
    else:
        pick = st.columns(len(FOLLOW_UPS))
        for i, (c, ex_q) in enumerate(zip(pick, FOLLOW_UPS)):
            if c.button(ex_q, key=f"fu_ex_{i}"):
                st.session_state.fu_question = ex_q
        with st.form("follow_up_question"):
            q = st.text_input("Your question", key="fu_question", placeholder="e.g. What if I put 10% in Tesla?")
            if st.form_submit_button("Ask the Analyst", type="primary") and q.strip():
                with st.spinner("Analyst checking with the tools (each what-if re-runs the pipeline)…"):
                    followups.insert(0, analyst.ask(q.strip(), res, profile))
        for a in followups:
            st.markdown(f"**Q: {a['question']}**")
            st.markdown(a["answer"])
            src = {"mock": "deterministic analyst (no LLM)", "bedrock": "Strands agent on Amazon Bedrock, live"}.get(
                a["source"], a["source"])
            st.caption(f"{'✔' if a['status'] == 'valid' else '✘'} code checks: {a['status']} · answered by: **{src}**"
                       + (f" · `{a['model']}`" if a.get("model") else "")
                       + (f" · {a['note']}" if a.get("note") and a["note"] != "mock mode" else ""))
            with st.expander(f"Tool calls ({len(a['tool_calls'])}): what the Analyst checked"):
                for c in a["tool_calls"]:
                    st.markdown(f"- `{analyst.short(c)}`")
                    st.json(json.loads(json.dumps(c["result"], default=str)), expanded=False)
            st.divider()

# ---- 5. trace --------------------------------------------------------------------------------------------
with tab_t:
    render_record(res, profile, download_key="jury_activity_download")
    if followups:
        st.subheader("Follow-up activity")
        for a in reversed(followups):
            st.write(a["question"])
            st.caption(f"{a['source']} · {a['status']}")
            with st.expander("Analyst tool calls"):
                st.json(a["tool_calls"], expanded=False)
