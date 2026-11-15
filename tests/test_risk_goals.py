"""(B) dh.risk.goals: statuses from curves (pure), the zero-premium guard, and the current anomaly reproduced."""
import pytest
from risk_markets import market, mix

from dh.agents import market as mk
from dh.risk import goals as g
from dh.risk.contracts import Assumption

CENTRAL = Assumption("central", 0.03, "test premium")
ASSUMPTIONS = {"zero_premium": g.ZERO_PREMIUM, "central": CENTRAL, "favourable": g.FAVOURABLE}


def curve(probs, shares=(0, .2, .4, .6, .8, 1.0)):
    return [{"share": s, "prob": p, "p50": 100 + 10 * s} for s, p in zip(shares, probs)]


class TestInterpretation:
    def test_reachable_without_equity(self):
        c = {"zero_premium": curve([.9] * 6), "central": curve([.9] * 6)}
        assert g.classify(c, ASSUMPTIONS, .6, .5, .25).status is g.GoalStatus.WITHOUT_EQUITY

    def test_needs_equity_never_above_ceiling(self):
        c = {"zero_premium": curve([.1] * 6), "central": curve([.1, .3, .45, .55, .7, .8])}
        a = g.classify(c, ASSUMPTIONS, .6, .5, .25)
        assert a.status is g.GoalStatus.NEEDS_EQUITY and a.min_share == .6
        b = g.classify(c, ASSUMPTIONS, .4, .5, .25)
        assert b.status is not g.GoalStatus.NEEDS_EQUITY and b.min_share is None

    def test_only_favourable_low_and_impossible(self):
        z = curve([0] * 6)
        assert g.classify({"zero_premium": z, "central": curve([.2, .3, .4, .45, .45, .45]),
                           "favourable": curve([.3, .5, .7, .8, .8, .8])}, ASSUMPTIONS, .6, .5, .25).status \
            is g.GoalStatus.ONLY_FAVOURABLE
        assert g.classify({"zero_premium": z, "central": curve([.1, .2, .3, .4, .4, .4]),
                           "favourable": curve([.1, .2, .3, .4, .4, .4])}, ASSUMPTIONS, .6, .5, .25).status \
            is g.GoalStatus.LOW_PROBABILITY
        assert g.classify({"zero_premium": z, "central": curve([0, .05, .1, .1, .1, .1]),
                           "favourable": curve([0, .05, .1, .2, .2, .2])}, ASSUMPTIONS, .6, .5, .25).status \
            is g.GoalStatus.IMPOSSIBLE

    def test_explanation_never_asks_for_more_than_the_ceiling(self):
        c = {"zero_premium": curve([0] * 6), "central": curve([0] * 6), "favourable": curve([0] * 6)}
        f = g.explanation_facts(g.classify(c, ASSUMPTIONS, .6, .5, .25))
        assert f["min_share"] is None and f["options"] and f["status"] == "impossible_within_limits"


class TestMethod:
    def test_zero_premium_never_buys_variance(self):
        """Under zero premium, a share > 0 is never returned even if its probability is higher (variance only)."""
        c = curve([.1, .2, .3, .55, .6, .7])
        assert g.min_share(c, g.ZERO_PREMIUM, .5, 1.0) is None

    def test_probability_curve_end_to_end(self):
        df = market(seed=1)
        cur = g.probability_curve(lambda s: mix(df, s), [0, .5, 1], CENTRAL, cash_daily=0.025 / 261,
                                  capital=100_000, horizon_years=5, target=120_000, n_scenarios=300)
        assert [c["share"] for c in cur] == [0, .5, 1] and all(0 <= c["prob"] <= 1 for c in cur)

    def test_inputs_validated(self):
        with pytest.raises(ValueError):
            g.classify({}, ASSUMPTIONS, .6, .5, .6)
        with pytest.raises(ValueError):
            g.probability_curve(lambda s: mix(market(), s), [0], CENTRAL, 0.0, 0, 5, 1000)


class TestAnomaly:
    def test_current_risk_only_view_median_falls_with_stocks(self):
        """Documents A2 (passes today): in the view the current floor uses, more stocks lower the median, so the
        floor search can only reward variance."""
        df = market(seed=2).rename(columns={"EQ": "SPY", "BOND": "XBB.TO", "CASH": "ZST.TO"})
        p50 = [mk.goal_outlook({"SPY": s, "ZST.TO": 1 - s} if s < 1 else {"SPY": 1.0}, capital=100_000,
                               horizon_years=5, target_amount=130_000, n_scenarios=400, rets=df)["risk_only"]["final_p50"]
               for s in (0.2, 0.6, 1.0)]
        assert p50[0] > p50[1] > p50[2]
