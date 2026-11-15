"""(E) dh.risk.frontier: one measure per chart, dominated points and backtracking detected."""
import numpy as np
import pandas as pd
import pytest

from dh import metrics
from dh import quant_toolkit as qt
from dh.risk import frontier as fr
from dh.risk.contracts import ReturnMeasure

D = 261


@pytest.fixture(scope="module")
def rets():
    """Assets up to 70% volatility: the volatility drag makes CAGR fall along the arithmetic frontier."""
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2021-11-12", "2026-11-12")
    # D: highest arithmetic mean, lowest CAGR (drag 0.8²/2 = 0.32 > 0.30): the top of the frontier must bend back
    vols, mus = np.array([.05, .15, .30, .80]), np.array([.03, .08, .15, .30])
    return pd.DataFrame(rng.normal(mus / D, vols / np.sqrt(D), (len(idx), 4)), idx, list("ABCD"))


class TestMethod:
    def test_arithmetic_frontier_is_clean(self, rets):
        f = fr.frontier(rets, ReturnMeasure.ARITHMETIC, n_points=12)
        assert f.issues == []

    def test_geometric_envelope_is_clean_and_labelled(self, rets):
        f = fr.frontier(rets, ReturnMeasure.GEOMETRIC, n_points=12)
        assert f.issues == [] and "pareto" in f.method

    def test_dominated_detection(self):
        pts = pd.DataFrame({"vol": [.1, .2, .3], "ret": [.05, .08, .07]})
        assert fr.dominated(pts).tolist() == [False, False, True]

    def test_mixed_measures_flagged(self):
        pts = pd.DataFrame({"vol": [.1, .2], "ret": [.05, .08]})
        assert [i.code for i in fr.check(pts, ReturnMeasure.ARITHMETIC, ReturnMeasure.GEOMETRIC)] == ["E-measures"]


class TestTechnical:
    def test_solver_failure_is_an_issue_not_a_crash(self, monkeypatch):
        """Exercise solver failure explicitly: convergence on a fixed seed depends on SciPy version."""
        def fails(*args, **kwargs):
            raise RuntimeError("Iteration limit reached")
        monkeypatch.setattr(qt, "efficient_frontier", fails)
        idx = pd.bdate_range("2021-11-12", "2026-11-12")
        vols, mus = np.array([.05, .15, .30, .70]), np.array([.03, .08, .15, .40])
        r = pd.DataFrame(np.random.default_rng(1).normal(mus / D, vols / np.sqrt(D), (len(idx), 4)), idx, list("ABCD"))
        f = fr.frontier(r, n_points=12)
        assert [i.code for i in f.issues] == ["E-solver"] and f.points.empty

    def test_too_few_assets_or_days(self, rets):
        with pytest.raises(ValueError):
            fr.frontier(rets[["A"]])
        with pytest.raises(ValueError):
            fr.frontier(rets.iloc[:30])


class TestAnomaly:
    def test_current_chart_method_backtracks(self, rets):
        """Documents A5 (passes today): market_charts' method (arithmetic optimisation, CAGR plot) bends back."""
        ppy = metrics.periods_per_year(rets)
        ef = qt.efficient_frontier(rets.mean() * ppy, rets.cov() * ppy, n_points=12)["frontiere"]
        pts = []
        for _, row in ef.iterrows():
            w = {t: row[t] for t in rets.columns if row[t] > 1e-6}
            p = metrics.portfolio_returns(rets[list(w)], w)
            pts.append({"vol": metrics.ann_vol(p), "ret": metrics.ann_return(p)})
        codes = {i.code for i in fr.check(pd.DataFrame(pts), ReturnMeasure.ARITHMETIC, ReturnMeasure.GEOMETRIC)}
        assert {"E-measures", "E-backtrack", "E-dominated"} <= codes
