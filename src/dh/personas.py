"""The three fictional personas from the official brief (pp. 5-7). Facts only from the brief;
any numeric constraint we add (caps, vol targets) is OUR assumption and must be labelled so."""

from __future__ import annotations

PERSONAS = {
    "amira": dict(
        name="Amira",
        age=26,
        job="Software engineer",
        risk="high",
        horizon_years="15+",
        experience="intermediate",
        objective="Grow capital over the long term.",
        preferences=[
            "Very interested in AI and emerging technologies",
            "Open to high-growth companies and significant volatility; interested in crypto",
            "Still wants diversification; not exclusively technology",
        ],
        tests="High risk must not mean 'anything goes'; respect her wish to diversify.",
    ),
    "mateo": dict(
        name="Mateo",
        age=41,
        job="Operations manager",
        risk="moderate",
        horizon_years="8-12",
        experience="intermediate",
        objective="Balanced capital growth over the medium and long term.",
        preferences=[
            "High importance on ESG factors",
            "Avoid companies with significant environmental or social controversies",
            "Balance between growth potential and stability",
            "Open to emerging tech if it fits his risk; little interest in speculation",
        ],
        tests="Incorporate more than risk/return: personal (ESG) preferences, not return alone.",
    ),
    "robert": dict(
        name="Robert",
        age=59,
        job="Healthcare professional",
        risk="low-to-moderate",
        horizon_years="3-5",
        experience="advanced",
        objective="Preserve capital while keeping some growth potential.",
        preferences=[
            "Prefers established companies with business models he understands",
            "Values stability and quality; little interest in crypto",
            "Follows markets actively, interested in new opportunities",
            "May be tempted by a highly publicised company even if riskier than he'd like",
        ],
        tests="Challenge requests that conflict with his profile; explain the risk, don't just agree.",
    ),
}

DISCLAIMER = (
    "Simulation only, for a fictional persona. Not financial advice; no real transactions."
)


def describe(key: str, simulated: bool = True) -> str:
    """Plain-text persona card, ready to drop into an agent prompt. With `simulated`, it also gives the numbers the
    pipeline actually runs (scenarios.DEMO_PROFILES), so the card and the result describe the same client (audit P11:
    the brief says Robert's horizon is "3-5" years; the pipeline uses 4)."""
    p = PERSONAS[key]
    prefs = "\n".join(f"- {x}" for x in p["preferences"])
    card = (
        f"{p['name']}, {p['age']}, {p['job']}. Risk: {p['risk']}. Horizon: {p['horizon_years']} years. "
        f"Experience: {p['experience']}.\nObjective: {p['objective']}\nPreferences:\n{prefs}"
    )
    if simulated:
        from .agents.scenarios import DEMO_PROFILES  # local: scenarios imports this module
        d = DEMO_PROFILES[key]
        card += (f"\n\nSimulated as (our fictional numbers): horizon {d['horizon_years']:g} years, capital "
                 f"{d['capital']:,.0f} $, largest loss accepted {d['max_loss_pct']:g}%, knowledge {d['knowledge_level']}.")
    return card
