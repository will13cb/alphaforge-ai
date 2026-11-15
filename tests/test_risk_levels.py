"""(C) dh.risk.levels: Pareto comparison, contradictions reported, and the real inversion found in results.csv."""
from pathlib import Path

import pandas as pd
import pytest

from dh.risk import levels as lv

RESULTS = Path(__file__).resolve().parents[1] / "results.csv"


def v(dd, vol, pl):
    return lv.RiskVector(max_drawdown=dd, ann_vol=vol, prob_loss=pl)


class TestInterpretation:
    def test_safer_riskier_mixed(self):
        """R5: the ladder is judged on worst drop and chance of loss (volatility is in the vector, not primary)."""
        assert lv.compare(v(.05, .04, .02), v(.10, .08, .05))["verdict"] == "safer"
        assert lv.compare(v(.10, .08, .05), v(.05, .04, .02))["verdict"] == "riskier"
        assert lv.compare(v(.05, .04, .06), v(.10, .08, .05))["verdict"] == "mixed"
        assert lv.compare(v(.05, .09, .02), v(.10, .08, .05))["verdict"] == "safer"

    def test_ladder_inversion_blocks_and_mixed_discloses(self):
        issues = lv.check_labels([("bold", v(.10, .08, .05)), ("prudent", v(.12, .07, .04))])
        assert [i.code for i in issues] == ["C-mixed"]
        issues = lv.check_labels([("bold", v(.10, .08, .05)), ("prudent", v(.12, .07, .06))])
        assert [i.code for i in issues] == ["C-inverted"] and issues[0].severity == "block"

    def test_order_keeps_unrankable_together(self):
        o = lv.order({"a": v(.05, .09, .06), "b": v(.10, .08, .05), "c": v(.20, .15, .10)})
        assert o["layers"][0] == ["a", "b"] and o["contradictions"]

    def test_missing_measures_reported_not_guessed(self):
        issues = lv.check_labels([("bold", lv.RiskVector()), ("prudent", lv.RiskVector())])
        assert issues and issues[0].code == "C-missing"


class TestAnomaly:
    def test_results_csv_latest_ladders_are_not_inverted(self):
        """A3 on REAL data: the persona strategies logged last (`make log-personas`, one commit) are ordered by risk.
        Before the fix this found Robert's 'more prudent' strategy riskier (−9.5% / 5.7% vs −8.6% / 3.9%)."""
        if not RESULTS.exists():
            pytest.skip("results.csv missing")
        df = pd.read_csv(RESULTS)
        df = df[df.experiment == "persona-strategies"]
        if df.empty:
            pytest.skip("persona rows missing")
        df = df[df.commit == df.sort_values("timestamp").commit.iloc[-1]]
        rank = {"most growth your limits allow": 1, "more prudent": 2, "most prudent": 3}
        for persona, rows in df.groupby("persona"):
            by_key = {}
            for _, r in rows.iterrows():
                key, metric = r.metric.rsplit("_", 1) if r.metric.count("_") == 1 else (
                    r.metric.split("_")[0], "_".join(r.metric.split("_")[1:]))
                by_key.setdefault(key, {"label": str(r.notes).split(": ")[-1]})[metric] = r.value
            ladder = sorted((x for x in by_key.values() if x["label"] in rank and "max_drawdown" in x),
                            key=lambda x: rank[x["label"]])
            vecs = [(x["label"], lv.RiskVector(max_drawdown=-x["max_drawdown"], prob_loss=x.get("prob_loss")))
                    for x in ladder]
            assert not [i for i in lv.check_labels(vecs) if i.code == "C-inverted"], persona
