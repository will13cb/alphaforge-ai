"""(A) dh.risk.loss_model on markets with KNOWN parameters: does the ceiling keep the client within the limit in
fresh futures, how stable is it across windows, and what happens in stress regimes."""
from itertools import pairwise

import numpy as np
import pytest
from risk_markets import REGIMES, market, mix, true_exceedance

from dh.risk import loss_model as lm

GRID = [round(0.1 * i, 2) for i in range(11)]
FAST = {"n_scenarios": 300, "seed": 0}


class TestTechnical:
    def test_short_history_refused(self):
        with pytest.raises(ValueError):
            lm.HistoricalWindow().distribution(market()["EQ"].iloc[:10], 1)

    def test_horizon_and_alpha_validated(self):
        df = market()
        with pytest.raises(ValueError):
            lm.StationaryBootstrapLoss(**FAST).distribution(df["EQ"], 0)
        with pytest.raises(ValueError):
            lm.equity_ceiling(lambda s: mix(df, s), GRID, 0.15, 4, alpha=0.0, model=lm.HistoricalWindow())

    def test_zero_loss_limit_is_a_decision_not_a_crash(self):
        """A client who accepts no loss at all (max_loss_pct 0): every share with risk breaks it, said, not raised."""
        df = market()
        dec = lm.equity_ceiling(lambda s: mix(df, s), GRID, 0.0, 4, alpha=0.10, model=lm.HistoricalWindow())
        assert dec.share is None and dec.issues[0].code == "A-none"
        assert lm.HistoricalWindow().distribution(mix(df, .5), 4).exceedance(0.0) == 1.0
        with pytest.raises(ValueError):
            lm.equity_ceiling(lambda s: mix(df, s), GRID, 1.0, 4, alpha=0.10, model=lm.HistoricalWindow())

    def test_nan_dropped_and_total_loss_refused(self):
        r = market()["EQ"].copy()
        r.iloc[5] = np.nan
        assert len(lm.HistoricalWindow().distribution(r, 1).samples) == 1
        r.iloc[6] = -1.0
        with pytest.raises(ValueError):
            lm.HistoricalWindow().distribution(r, 1)


class TestMethod:
    def test_observed_vs_simulated_are_labelled(self):
        df = market()
        h = lm.HistoricalWindow().distribution(mix(df, .5), 4)
        b = lm.StationaryBootstrapLoss(**FAST).distribution(mix(df, .5), 4)
        assert (h.evidence.value, b.evidence.value) == ("observed", "simulated")
        assert h.horizon_years is None and b.horizon_years == 4

    def test_longer_horizon_deeper_losses(self):
        m = lm.StationaryBootstrapLoss(**FAST)
        p = mix(market(), .6)
        assert m.distribution(p, 15).exceedance(0.15) > m.distribution(p, 2).exceedance(0.15)

    def test_exceedance_monotone_in_limit_and_share(self):
        m, df = lm.StationaryBootstrapLoss(**FAST), market()
        d = m.distribution(mix(df, .6), 5)
        assert d.exceedance(0.10) >= d.exceedance(0.20) >= d.exceedance(0.30)
        assert m.distribution(mix(df, .8), 5).exceedance(.15) >= m.distribution(mix(df, .2), 5).exceedance(.15)

    def test_bootstrap_ceiling_safer_than_window_ceiling_out_of_sample(self):
        """Audit T5 made a test: over several 5-year histories of the same market, the window method's ceiling is
        breached in fresh 10-year futures far more often than alpha; the bootstrap-on-horizon method less so.
        It does NOT prove the bootstrap reaches alpha (5 years of data cannot): see the numbers in the doc."""
        limit, alpha, years = 0.15, 0.10, 10
        win, boot = [], []
        for seed in range(8):
            df = market(seed=seed)
            for model, acc in ((lm.HistoricalWindow(), win), (lm.StationaryBootstrapLoss(**FAST), boot)):
                s = lm.equity_ceiling(lambda x, df=df: mix(df, x), GRID, limit, years, alpha, model).share or 0.0
                acc.append(true_exceedance(s, limit, years, n=200))
        assert np.mean(win) > 0.3
        assert np.mean(boot) < np.mean(win)

    def test_window_ceilings_report_a_range(self):
        df = market(years=5, seed=5)
        res = lm.window_ceilings(lambda s: mix(df, s), GRID, 0.15, 4, 0.10,
                                 lambda: lm.StationaryBootstrapLoss(**FAST), years=3, step_years=1)
        assert len(res["by_window"]) == 3 and res["range"] is not None

    def test_window_ceilings_skip_years_before_a_young_asset(self):
        """Long history (decision #47): a share holding an asset that starts later (ETH 2017) has no days in the
        early windows. Windows start once every share has data, instead of failing on an empty window."""
        df = market(years=9, seed=5)
        late = df.index[int(len(df) * 5 / 9)]
        port_of = lambda s: mix(df, s) if s == 0.0 else mix(df, s).loc[late:]   # noqa: E731
        res = lm.window_ceilings(port_of, GRID, 0.15, 4, 0.10,
                                 lambda: lm.StationaryBootstrapLoss(**FAST), years=3, step_years=1)
        assert res["by_window"] and all(a >= str(late.date()) for a, _ in res["by_window"])

    def test_common_random_numbers_make_exceedance_monotone(self):
        """Same indices for every share: the exceedance curve rises with the share without sampling wiggles."""
        m, df = lm.StationaryBootstrapLoss(**FAST), market(seed=6)
        p = [m.distribution(mix(df, s), 10).exceedance(0.15) for s in GRID]
        assert all(b >= a - 1e-12 for a, b in pairwise(p))

    def test_scan_stops_at_first_breach_and_reports_loss_only(self):
        df = market(seed=7)
        dec = lm.equity_ceiling(lambda s: mix(df, s), GRID, 0.25, 4, 0.10, lm.StationaryBootstrapLoss(**FAST),
                                max_share=0.2)
        assert dec.share <= 0.2 and dec.loss_only >= dec.share
        assert dec.table[-1]["exceedance"] > 0.10 or dec.table[-1]["share"] == 1.0

    def test_none_when_even_zero_breaks(self):
        """A 100% bond portfolio can still break a tight limit: say so (A-none), never force a share."""
        df = market(seed=7)
        dec = lm.equity_ceiling(lambda s: mix(df, s), GRID, 0.15, 4, 0.10, lm.StationaryBootstrapLoss(**FAST))
        assert dec.share is None and [i.code for i in dec.issues] == ["A-none"]


class TestScenarios:
    @pytest.mark.parametrize("regime", [r for r in REGIMES if r != "calm"])
    def test_stress_regimes_never_look_safer_than_calm_on_the_window(self, regime):
        calm = lm.HistoricalWindow().distribution(mix(market(), .6), 5).samples[0]
        hit = lm.HistoricalWindow().distribution(mix(market(regime=regime), .6), 5).samples[0]
        if regime == "inflation":   # nominal drawdown need not be deeper: the real loss is the risk (A13)
            pytest.skip("nominal measure: inflation risk is not a drawdown, needs a real-terms view")
        assert hit <= calm + 0.02

