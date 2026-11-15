"""Your profile: one step at a time, only the questions that apply, errors under the field, review before running."""

from __future__ import annotations

import streamlit as st

from dh.i18n import lang, tr

from interface.core import services, wizard
from interface.core.questions import ALL_STEPS, BY_ID, STEPS
from interface.ui import components as ui
from interface.ui import voice as voice_ui
from interface.ui.activity import live_run

S = st.session_state


def reset_widgets() -> None:
    """Forget the widgets' own memory so they show `answers` again (after a prefill or a reset)."""
    for k in [k for k in S if isinstance(k, str) and k.startswith("f_")]:
        del S[k]


def prefill(profile: dict, where: int = len(STEPS)) -> None:
    S.answers = wizard.from_profile(profile)
    S.tried = set(range(len(STEPS)))
    S.step = where
    reset_widgets()


def start_over() -> None:
    for k in ("answers", "tried", "res", "profile", "chat", "confirm_reset", "free_text_notes"):
        S.pop(k, None)
    S.step = 0
    reset_widgets()


def shown(q, raw) -> str:
    """An answer as the person would read it back."""
    c = wizard.check(q, raw)
    v = c.value
    if not c.ok:
        return "To fix"
    if v in (None, "", [], {}):
        return "–"
    if q.kind in ("choice", "yesno"):
        return dict(q.options).get(v, str(v))
    if q.kind == "choices":
        return ", ".join(tr(dict(q.options).get(x, x)) for x in v)
    if q.kind == "money":
        return f"{v:,.0f} $"
    if q.kind == "percent":
        return f"{v:g}%"
    if q.kind == "position":
        t, w = next(iter(v.items()))
        return f"{t}, {100 * w:g}%"
    return f"{v:g}" if isinstance(v, float) else str(v)


def quick_start() -> None:
    with st.expander("Start faster: an example client, or describe yourself in a few sentences"):
        demos = services.demo_clients()
        c1, c2 = st.columns([3, 1])
        pick = c1.selectbox("Example clients (fictional)", list(demos), format_func=lambda k: demos[k][0],
                            index=None, placeholder="Choose an example…", key="demo_pick")
        if c2.button("Use it", disabled=pick is None, width="stretch"):
            prefill(demos[pick][1])
            st.rerun()
        st.markdown("**Or describe your situation** — we fill in what we can, you check the rest.")
        voice_ui.dictation("profile_voice", "free_text")
        text = st.text_area("Your situation", key="free_text", height=110, label_visibility="collapsed",
                            placeholder="e.g. I'm 45, I have 50,000 $ to invest for my retirement in 20 years. "
                                        "I could accept a drop of 20%. My income is stable.")
        if st.button("Fill the form from my text"):
            try:
                with ui.thinking("Reading your text…"):
                    ex = services.extract_text(text)
                prefill(ex["profile"], where=0)
                S.free_text_notes = ex
                st.rerun()
            except (services.UserError, services.InternalError) as e:
                ui.error(str(e))
    ex = S.get("free_text_notes")
    if ex:
        miss = [BY_ID[m].label for m in ex.get("missing", []) if m in BY_ID]
        ui.notice("We filled in what your text said. Please check each step"
                  + (" and answer what was missing: " + "; ".join(miss) if miss else "") + ".", "info")


def nav(i: int, last: bool = False) -> None:
    # keyed container: on a phone the CSS puts Continue first and drops the spacer (interface/ui/theme.py)
    b1, b2, _, b3 = st.container(key=f"af_nav_{i}").columns([1, 1.3, 1.2, 1])
    if b1.button("← Back", disabled=i == 0, width="stretch", key=f"back_{i}"):
        S.step = i - 1
        st.rerun()
    if not last and b2.button("Continue →", type="primary", width="stretch", key=f"next_{i}"):
        S.tried.add(i)
        _, errs = wizard.check_step(i, S.answers)
        if not errs:
            S.step = i + 1
            st.rerun()
        else:
            S.nav_msg = f"Please fix the {len(errs)} answer{'s' if len(errs) > 1 else ''} marked in red."
            st.rerun()
    if S.get("confirm_reset"):
        if b3.button("Erase all?", width="stretch", key=f"reset2_{i}", help="Click to confirm"):
            start_over()
            st.rerun()
    elif b3.button("Start over", width="stretch", key=f"reset_{i}"):
        S.confirm_reset = True
        st.rerun()


def sync(i: int) -> None:
    """Widgets already hold this run's values: copy them into `answers` before checking (no one-run lag)."""
    for q in STEPS[i].questions:
        k = f"f_{q.id}"
        if q.kind == "position" and k + "_n" in S:
            S.answers[q.id] = (S[k + "_n"], S.get(k + "_p", ""))
        elif k in S:
            S.answers[q.id] = S[k]


def step_form(i: int) -> None:
    step = STEPS[i]
    sync(i)
    st.subheader(step.title)
    st.markdown(f'<p class="af-muted">{ui.esc(step.intro)}</p>', unsafe_allow_html=True)
    voice_ui.read_aloud(step.title + ". " + step.intro + " " + " ".join(
        q.label for q in step.questions if q.visible_if is None or q.visible_if(S.answers)), f"profile_step_{i}")
    errs = wizard.check_step(i, S.answers)[1] if i in S.tried else {}
    advanced = []
    for q in step.questions:              # in order: an answer can show or hide the questions after it
        if q.visible_if is not None and not q.visible_if(S.answers):
            continue
        if q.advanced:
            advanced.append(q)
            continue
        ui.field(q, S.answers, errs.get(q.id))
    if advanced:
        with st.expander("More options (optional)", expanded=any(q.id in errs or S.answers.get(q.id) for q in advanced)):
            for q in advanced:
                ui.field(q, S.answers, errs.get(q.id))
    if i in S.tried:                      # live: errors disappear as soon as the answer is fixed
        errs = wizard.check_step(i, S.answers)[1]
    msg = S.pop("nav_msg", None)
    if msg and errs:
        ui.error(msg)
    st.write("")
    nav(i)


def review() -> None:
    st.subheader("Check your answers")
    st.markdown('<p class="af-muted">' + ui.esc("Review names and amounts carefully. Change any answer with “Edit” before running the simulation. Analysis records may be saved to Amazon S3 or locally.") + '</p>',
                unsafe_allow_html=True)
    _, errors = wizard.all_values(S.answers)
    for i, step in enumerate(STEPS):
        qs = wizard.visible(i, S.answers)
        head, edit = st.container(key=f"af_row_{i}").columns([5, 1])  # stays on one line on a phone
        head.markdown(f"**{tr(step.title)}**" + (tr("  (to fix)") if i in errors else ""))
        if edit.button("Edit", key=f"edit_{i}", width="stretch"):
            S.step = i
            st.rerun()
        rows = [f"- {ui.esc(q.label)} **{ui.esc(shown(q, S.answers.get(q.id, q.default)))}**" for q in qs
                if not (not q.required and shown(q, S.answers.get(q.id, q.default)) == "–")]
        st.markdown("\n".join(rows) or "- –", unsafe_allow_html=True)
    if errors:
        first = min(errors)
        ui.notice(tr("Some answers still need attention, starting with “") + tr(STEPS[first].title) + tr("”."), "bad")
        if st.button("Go to the first answer to fix", type="primary"):
            S.step = first
            S.tried.add(first)
            st.rerun()
    else:
        if st.button("Run the analysis", type="primary", width="stretch"):
            values, _ = wizard.all_values(S.answers)
            profile = wizard.to_profile(values)
            if S.get("existing_positions"):  # branch portefeuille_existant: entered on the Welcome page
                profile["existing_positions"] = dict(S.existing_positions)
            try:
                with live_run() as on_step:
                    res = services.run_analysis(profile, on_step=on_step)
                S.profile, S.res, S.chat = profile, res, []
                S.goto = "Your results"
                st.rerun()
            except (services.UserError, services.InternalError) as e:
                ui.notice(str(e), "bad")
    st.write("")
    nav(len(STEPS), last=True)


def render() -> None:
    S.setdefault("answers", {})
    S.setdefault("tried", set())
    S.setdefault("step", 0)
    i = S.step
    titles = [s.title.replace(" (optional)", "") for s in ALL_STEPS]
    ui.steps_bar(titles, i)
    st.progress(wizard.progress(i), text=(f"Étape {i + 1} sur {len(ALL_STEPS)}" if lang() == "fr"
                                          else f"Step {i + 1} of {len(ALL_STEPS)}"))
    if i == 0:
        quick_start()
    if i < len(STEPS):
        step_form(i)
    else:
        review()

