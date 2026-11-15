"""dh.risk — independent checks of the formulas the modules rely on (technical / method).
`TestAnomaly` tests describe the DESIRED behaviour and fail today (xfail strict): when a phase-2 fix lands they pass,
strict turns that into a failure, and the marker must be removed consciously (no silent "resolved")."""
import numpy as np
import pandas as pd
import pytest
from risk_markets import market

from dh import metrics
from dh import quant_toolkit as qt
from dh.risk import frontier as fr
from dh.risk.contracts import Assumption, Issue, ReturnMeasure
from dh.risk.goals import recentre
from dh.risk.loss_model import drawdowns


class TestTechnical:
    def test_drawdowns_matches_quant_toolkit(self):
        r = market(regime="equity_crash")["EQ"]
        assert drawdowns(r.to_numpy()[None, :])[0] == pytest.approx(qt.max_drawdown(r), abs=1e-12)

    def test_drawdown_known_values(self):
        assert drawdowns(np.array([[-0.10, 0.05, -0.02]]))[0] == pytest.approx(-0.10)
        assert drawdowns(np.array([[0.10, -0.50, 1.0]]))[0] == pytest.approx(-0.50)
        assert drawdowns(np.zeros((1, 5)))[0] == 0.0

    def test_issue_rejects_unknown_kind(self):
        with pytest.raises(ValueError):
            Issue("x", "block", "typo", "m")


class TestMethod:
    def test_geometric_is_arithmetic_minus_drag(self):
        """CAGR ≈ μ − σ²/2 on log-normal-like data: the two measures must not be swapped (E)."""
        r = market(years=20, seed=1)["EQ"]
        mu, vol, cagr = (fr.measure_of(r, ReturnMeasure.ARITHMETIC), metrics.ann_vol(r),
                         fr.measure_of(r, ReturnMeasure.GEOMETRIC))
        assert cagr < mu
        assert abs(fr.drag_gap(mu, vol, cagr)) < 0.005

    def test_log_measure_is_log_of_cagr(self):
        r = market(seed=2)["EQ"]
        assert fr.measure_of(r, ReturnMeasure.LOG) == pytest.approx(np.log1p(metrics.ann_return(r)), rel=2e-3)

    def test_recentre_sets_mean_and_keeps_swings(self):
        r = market(seed=3)["EQ"]
        a = Assumption("t", 0.04, "test")
        x = recentre(r, cash_daily=0.025 / 261, a=a, growth_share=0.5)
        assert x.mean() * metrics.periods_per_year(x) == pytest.approx(0.025 + 0.5 * 0.04, rel=1e-3)
        assert x.std() == pytest.approx(r.std())

    def test_bootstrap_keeps_the_mean(self):
        r = market(seed=4)["EQ"]
        p = qt.bootstrap_paths(r, n_periods=261, n_scenarios=2000, seed=0).to_numpy()
        assert p.mean() == pytest.approx(r.mean(), abs=3 * r.std() / np.sqrt(p.size / 11))


class TestAnomaly:
    def test_metrics_drawdown_counts_day_one(self):
        """A10, fixed in metrics.max_drawdown (starting value counts as a peak); was xfail strict."""
        assert metrics.max_drawdown([-0.10, 0.05, -0.02]) == pytest.approx(-0.10)

    def test_one_drawdown_definition(self):
        """A10, fixed: metrics and quant_toolkit agree; was xfail strict."""
        r = pd.Series([-0.10, 0.05, -0.02])
        assert metrics.max_drawdown(r) == pytest.approx(qt.max_drawdown(r))
