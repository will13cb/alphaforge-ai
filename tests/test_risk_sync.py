"""(F) dh.risk.sync: stamps, stale sections detected and refreshed; the current gap reproduced on the Portfolio."""
import numpy as np
import pandas as pd
import pytest
from risk_markets import market as synth

from dh.agents import market, portfolio
from dh.agents.profiler import derive_limits
from dh.agents.rules import CRYPTO, DEFENSIVE, STOCKS, UNIVERSE
from dh.agents.scenarios import AMIRA
from dh.risk import sync


class TestTechnical:
    def test_fingerprint_order_and_rounding(self):
        assert sync.fingerprint_weights({"A": .3, "B": .7}) == sync.fingerprint_weights({"B": .7, "A": 0.1 + 0.2})
        assert sync.fingerprint_weights({"A": .3, "B": .7}) != sync.fingerprint_weights({"A": .31, "B": .69})
        assert sync.fingerprint_weights({"A": 1.0, "B": 0.0}) == sync.fingerprint_weights({"A": 1.0})
        with pytest.raises(ValueError):
            sync.fingerprint_weights({})

    def test_data_fingerprint_sees_a_window_change(self):
        df = synth()
        assert sync.fingerprint_data(df) != sync.fingerprint_data(df.iloc[1:])


class TestInterpretation:
    def test_stale_section_blocks_and_refresh_fixes(self):
        df = synth()
        w0, w1 = {"EQ": .6, "BOND": .4}, {"EQ": .5, "BOND": .5}
        s = sync.stamp({"weights": w0, "outlook": {"p": 1}}, "outlook", df, "old")
        s = {**s, "weights": w1}
        assert [i.code for i in sync.verify(s, df)] == ["F-stale-weights"]

        def outlook(w):
            return {"p": w["EQ"]}
        new = sync.refresh(s, {"outlook": outlook}, df)
        assert sync.verify(new, df) == [] and new["outlook"]["p"] == .5

    def test_stale_without_producer_stays_blocked(self):
        df = synth()
        s = {**sync.stamp({"weights": {"BOND": 1.0}, "stats": {}}, "stats", df, "old"), "weights": {"EQ": 1.0}}
        assert sync.verify(sync.refresh(s, {}, df), df)[0].severity == "block"


@pytest.fixture(scope="module")
def rets():
    """Same shape as tests/test_portfolio.py: equity ETFs ~0.96 correlated, so the C6 merge fires."""
    idx = pd.bdate_range("2021-11-15", "2026-11-12")
    rng = np.random.default_rng(7)
    in22 = (idx.year == 2022).astype(float)
    mkt = rng.normal(0.0005, 0.010, len(idx)) - 0.0012 * in22
    cols = {}
    for t in sorted(UNIVERSE):
        if t == "ZST.TO":
            cols[t] = rng.normal(0.00012, 0.0006, len(idx))
        elif t in DEFENSIVE or t == "TLT":
            cols[t] = rng.normal(0.0001, 0.004, len(idx)) - 0.0002 * in22
        elif t in CRYPTO:
            cols[t] = 1.5 * mkt + rng.normal(0.0003, 0.03, len(idx))
        elif t in STOCKS:
            cols[t] = 1.2 * mkt + rng.normal(0, 0.012, len(idx))
        else:
            cols[t] = mkt + rng.normal(0, 0.002, len(idx))
    return pd.DataFrame(cols, index=idx)


class TestAnomaly:
    def test_outlook_describes_final_weights(self, rets, monkeypatch):
        """A6, fixed: assemble computes the outlook on the final weights and stamps it; was xfail strict."""
        monkeypatch.setattr(portfolio, "N_SEARCH", 100)
        monkeypatch.setattr(portfolio, "N_FINAL", 300)
        for k in ("N_LOSS", "N_LOSS_FINAL", "N_RANGE"):
            monkeypatch.setattr(portfolio, k, 300)
        lim = derive_limits(AMIRA)
        s = next(x for x in portfolio.propose(AMIRA, lim, rets=rets, holdings={})
                 if any(a.startswith("C6") for a in x["adjustments"]))
        o = market.goal_outlook(s["weights"], capital=AMIRA["capital"], horizon_years=AMIRA["horizon_years"],
                                monthly_contribution=AMIRA.get("monthly_contribution") or 0.0,
                                target_amount=AMIRA.get("target_amount"), n_scenarios=300, rets=rets)
        assert s["stats"]["prob_loss"] == pytest.approx(round(o["risk_only"]["prob_loss"], 4), abs=1e-9)
        assert sync.verify(s, rets) == []
