"""The demo app and its chart helpers, offline."""
from pathlib import Path

import pytest

from dh.__main__ import _cli_profile
from dh.agents import portfolio_charts as pc
from dh.agents.scenarios import DEMO_PROFILES, ROBERT

ROOT = Path(__file__).resolve().parents[1]

STRATEGY = dict(
    name="Broad core", split={"growth": 0.15, "defensive": 0.85},
    stats={"max_drawdown": -0.086, "return_2022": -0.05, "ann_vol": 0.04},
    split_curve=[{"growth": g / 20, "max_drawdown": -0.01 - g / 100, "stress_2022": -g / 200, "return_2022": -g / 150,
                  "ann_vol": 0.01 + g / 200} for g in range(21)],
    outlook={"horizon_years": 4, "total_invested": 400_000, "target_amount": None,
             "risk_only": {"prob_loss": 0.3, "prob_target": None, "final_p5": 350_000, "final_p50": 410_000, "final_p95": 470_000},
             "replay": {"prob_loss": 0.1, "prob_target": None, "final_p5": 380_000, "final_p50": 450_000, "final_p95": 520_000}},
)
LIMITS = {"loss_limit": 0.15, "min_defensive": 0.85, "horizon_max_growth": 0.15}


def test_demo_profiles_are_the_cli_profiles():
    assert DEMO_PROFILES["robert_tsla"] == {**ROBERT, "requested_positions": {"TSLA": 0.25}}
    assert _cli_profile("robert") is DEMO_PROFILES["robert_tsla"]  # same facts → same Explainer cache hash
    assert _cli_profile("amira") is DEMO_PROFILES["amira"]


def test_split_curve_data_is_the_strategy_curve():
    df = pc.split_curve_data(STRATEGY)
    assert len(df) == 21 and df["growth"].iloc[-1] == 1.0
    assert (df["worst_drop"] >= 0).all() and df["worst_drop"].iloc[5] == pytest.approx(0.06)
    spec = pc.split_curve_chart(df, LIMITS, STRATEGY).to_dict()
    assert len(spec["layer"]) == 6  # horizon band + label, curve, loss-limit rule + label, chosen split
    assert pc.split_curve_data({"split_curve": []}).empty


def test_outcome_frame_reuses_the_outlook():
    df = pc.outcome_frame(STRATEGY)
    assert list(df["key"]) == ["risk_only", "replay"]
    assert df.loc[0, "p50"] == 410_000 and df.loc[1, "p95"] == 520_000
    assert pc.outcome_frame({"outlook": None}) is None


def test_app_runs_or_asks_for_the_data():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=600).run()
    assert not at.exception, at.exception
    if not (ROOT / "data" / "raw" / "prices_daily.csv").exists():
        assert any("make data" in m.value for m in at.markdown)
    else:
        assert at.tabs and len(at.tabs) == 5


def test_app_follow_up_question_goes_to_the_analyst():
    """The Follow-up tab: a question → analyst.ask → answer checked by code, tool calls listed (needs the CSVs)."""
    if not (ROOT / "data" / "raw" / "prices_daily.csv").exists():
        pytest.skip("needs the starter CSVs")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=600).run()
    at.text_input(key="fu_question").set_value("What if I put 10% in Tesla?")
    at.button[[b.label for b in at.button].index("Ask the Analyst")].click().run()
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Q: What if I put 10% in Tesla?" in text and "TSLA" in text
    assert any("code checks: valid" in c.value for c in at.caption)


def test_app_run_is_saved_and_saving_never_breaks_it(monkeypatch, tmp_path):
    """Each app run goes to the trace store (S3, else a local copy); a failing save leaves the run intact."""
    from dh import tracestore
    from dh.agents.pipeline import run
    from dh.agents.scenarios import DROPS_DEMO

    monkeypatch.setattr(tracestore, "LOCAL_DIR", tmp_path)
    monkeypatch.delenv("S3_BUCKET", raising=False)
    res = run(DEMO_PROFILES["robert_tsla"], propose=False, drops=DROPS_DEMO)
    out = tracestore.save_run_safe(res, DEMO_PROFILES["robert_tsla"], persona="robert_tsla")
    assert out["stored"] == "local" and len(list(tmp_path.rglob("*.json"))) == 1
    assert res["trace"].steps[-1]["agent"] == "Trace store"

    def boom(*a, **k):
        raise OSError("read-only disk")
    monkeypatch.setattr(tracestore, "save_run", boom)
    res2 = run(DEMO_PROFILES["robert_tsla"], propose=False, drops=DROPS_DEMO)
    assert tracestore.save_run_safe(res2, DEMO_PROFILES["robert_tsla"]) is None
    assert res2["stored"]["stored"] == "none" and "read-only" in res2["stored"]["note"] and res2["limits"]
