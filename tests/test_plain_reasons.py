"""The Profiler's reasons written for the client: every score names its scale, nothing changes the engine's reasons."""
from dh.agents.profiler import derive_limits
from dh.agents.scenarios import DEMO_PROFILES


def test_plain_reasons_name_the_scale_and_leave_engine_reasons_alone():
    lim = derive_limits(DEMO_PROFILES["robert_tsla"], drops={})
    plain = lim["reasons_plain"]
    assert any("risk tolerance 4/5 (Growth)" in r for r in plain)
    assert any("2/5 (Cautious)" in r and "risk level" in r for r in plain)
    assert not any(r.rstrip(".").endswith(("→ 2", "→ 4", "→ 5")) for r in plain)
    assert "reaction to a 20% drop 'hold' → 4" in lim["reasons"]  # Explainer facts (cache hash) unchanged


def test_plain_knowledge_steps_follow_the_score():
    for k, p in DEMO_PROFILES.items():
        lim = derive_limits(p, drops={})
        if lim.get("missing"):
            continue
        know = [r for r in lim["reasons_plain"] if "knowledge" in r and "/5" in r]
        assert know[-1].count(f"{lim['knowledge_score']}/5"), (k, know)
