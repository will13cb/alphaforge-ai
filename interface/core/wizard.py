"""The step-by-step form, as plain data: which questions show, what is wrong, where we are, what the engine gets.

No Streamlit here (tests/test_interface_wizard.py). Answers are kept RAW (what was typed) so that going back never
loses anything; they are parsed again each time a step is checked.
"""

from __future__ import annotations

from . import validation as v
from .questions import ALL_STEPS, BY_ID, STEPS, Question


def visible(step_index: int, answers: dict, show_advanced: bool = True) -> list[Question]:
    """Questions of a step that apply to these answers (hidden ones are not asked and not checked)."""
    if step_index >= len(STEPS):
        return []
    out = []
    for q in STEPS[step_index].questions:
        if q.visible_if is not None and not q.visible_if(answers):
            continue
        if q.advanced and not show_advanced:
            continue
        out.append(q)
    return out


def check(q: Question, raw) -> v.Check:
    """One answer → Check, with the engine's limits for profile fields."""
    k = q.kind
    if k in ("whole", "decimal"):
        lo, hi = q.bounds or v.bounds(q.id)
        return (v.whole_number if k == "whole" else v.decimal)(raw, lo, hi, q.required)
    if k == "money":
        lo, hi = q.bounds or v.bounds(q.id)
        return v.money(raw if raw not in (None, "") else (q.default or ""), lo, hi, q.required)
    if k == "percent":  # asked in %, the engine's schema may hold a fraction (withdrawal_share_3y: 0-1 → 0-100%)
        lo, hi = q.bounds or v.bounds(q.id)
        if hi <= 1:
            lo, hi = 100 * lo, 100 * hi
        return v.percent(raw, lo, hi, q.required)
    if k in ("choice", "yesno"):
        return v.choice(raw if raw is not None else q.default, [o for o, _ in q.options], q.required)
    if k == "choices":
        return v.choices(raw, [o for o, _ in q.options])
    if k == "name":
        return v.name(raw, q.required)
    if k == "position":
        name, pct = raw if isinstance(raw, (list, tuple)) and len(raw) == 2 else ("", "")
        return v.position(name, pct)
    return v.Check(False, None, "Unknown question type.")


def check_step(step_index: int, answers: dict) -> tuple[dict, dict]:
    """(values, errors) for the visible questions of a step. errors: {question id: message}."""
    values, errors = {}, {}
    for q in visible(step_index, answers):
        c = check(q, answers.get(q.id, q.default))
        if c.ok:
            values[q.id] = c.value
        else:
            errors[q.id] = c.message
    errors.update(cross_checks(step_index, answers, values))
    return values, errors


def cross_checks(step_index: int, answers: dict, values: dict) -> dict:
    """Combinations the engine can't use, with what to do. Rules come from the engine (goal_outlook /
    required_return need money to invest; a target must be above zero)."""
    out = {}
    if step_index < len(STEPS) and STEPS[step_index].id == "money":
        cap, mon = values.get("capital"), values.get("monthly_contribution")
        if cap is not None and cap == 0 and not mon:
            out["capital"] = "Enter an amount to invest today, or a monthly amount: with neither, there is nothing to invest."
    return out


def all_values(answers: dict) -> tuple[dict, dict]:
    """Every step at once: (values, errors keyed by step index → {question: message})."""
    values, errors = {}, {}
    for i in range(len(STEPS)):
        val, err = check_step(i, answers)
        values.update(val)
        if err:
            errors[i] = err
    return values, errors


def first_step_with_errors(answers: dict) -> int | None:
    _, errors = all_values(answers)
    return min(errors) if errors else None


def progress(step_index: int) -> float:
    return min(1.0, step_index / (len(ALL_STEPS) - 1))


def to_profile(values: dict) -> dict:
    """Checked values → the engine's `profile` (contract §1). Hidden questions don't contribute."""
    p = {k: values[k] for k in ("name", "age", "income_stability", "emergency_fund_months", "objective", "capital",
                                "horizon_years", "loss_reaction", "max_loss_pct", "knowledge_level") if values.get(k) is not None}
    p.setdefault("name", "You")
    p["monthly_contribution"] = values.get("monthly_contribution") or 0.0
    if values.get("has_target") == "yes" and values.get("target_amount"):
        p["target_amount"] = values["target_amount"]
    p["withdrawal_share_3y"] = (values.get("withdrawal_share_3y") or 0) / 100 if values.get("withdrawals") == "yes" else 0.0
    if values.get("years_experience") is not None:
        p["years_experience"] = values["years_experience"]
    for k in ("products_held", "interests", "exclusions"):
        p[k] = list(values.get(k) or [])
    if values.get("employment_sector"):
        p["employment_sector"] = values["employment_sector"]
    if values.get("request"):
        p["requested_positions"] = dict(values["request"])
    return p


def from_profile(profile: dict) -> dict:
    """An engine profile (demo client, free-text extraction) → raw answers to prefill the form."""
    a = {}
    for k in ("name", "age", "income_stability", "emergency_fund_months", "objective", "capital",
              "monthly_contribution", "horizon_years", "loss_reaction", "max_loss_pct", "knowledge_level",
              "years_experience", "employment_sector"):
        if profile.get(k) not in (None, ""):
            a[k] = profile[k] if isinstance(profile[k], str) else f"{profile[k]:g}" if isinstance(profile[k], float) else str(profile[k])
    for k in ("products_held", "interests", "exclusions"):
        a[k] = [x for x in profile.get(k) or [] if x in dict(BY_ID[k].options)]
    if profile.get("target_amount"):
        a["has_target"], a["target_amount"] = "yes", f"{profile['target_amount']:g}"
    if profile.get("withdrawal_share_3y"):
        a["withdrawals"], a["withdrawal_share_3y"] = "yes", f"{100 * profile['withdrawal_share_3y']:g}"
    if profile.get("requested_positions"):
        t, w = next(iter(profile["requested_positions"].items()))
        a["request"] = (t, f"{100 * w:g}")
    return a
