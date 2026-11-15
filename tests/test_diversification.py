"""Diversification report and rules C3/C4/C6 (decision #18), on synthetic returns: no starter CSVs needed."""
import json

import numpy as np
import pandas as pd
import pytest

from dh.agents import diversification as dv

HOLD = {"SPY": {"NVDA": 0.07, "MSFT": 0.06, "AAPL": 0.06}, "QQQ": {"NVDA": 0.09, "MSFT": 0.08, "AAPL": 0.08}}  # ILLUSTRATIVE
SECTORS = {"NVDA": "Information Technology", "MSFT": "Information Technology", "AAPL": "Information Technology",
           "RY.TO": "Financials", "SPY": "Broad market (U.S.)", "ESGV": "Broad market (U.S., ESG-screened)",
           "QQQ": "Broad market (U.S. growth/tech-heavy)"}


@pytest.fixture
def rets():
    idx = pd.bdate_range("2021-11-15", "2026-11-12")
    rng = np.random.default_rng(1)
    mkt = rng.normal(0.0004, 0.01, len(idx))
    return pd.DataFrame({
        "SPY": mkt + rng.normal(0, 0.001, len(idx)),
        "ESGV": mkt + rng.normal(0, 0.001, len(idx)),        # ~0.99 with SPY: the same bet
        "QQQ": 1.2 * mkt + rng.normal(0, 0.004, len(idx)),
        "NVDA": 2 * mkt + rng.normal(0, 0.02, len(idx)),
        "MSFT": 1.1 * mkt + rng.normal(0, 0.01, len(idx)),
        "RY.TO": 0.8 * mkt + rng.normal(0, 0.008, len(idx)),
        "XBB.TO": rng.normal(0.0001, 0.003, len(idx)),
        "GLD": rng.normal(0.0002, 0.008, len(idx)),
        "BTC-USD": rng.normal(0.0005, 0.035, len(idx)),
    }, index=idx)


def rep(w, rets, hold=HOLD):
    return dv.report(w, rets=rets, holdings=hold, sectors=SECTORS)


def test_look_through_counts_companies_inside_etfs(rets):
    r = rep({"QQQ": 0.5, "NVDA": 0.1, "XBB.TO": 0.4}, rets)
    # NVDA = 10% direct + 50% x 9% through QQQ (Will's look_through)
    assert r["largest_company"] == {"name": "NVDA", "weight": pytest.approx(0.145)}
    assert r["look_through_coverage"] == pytest.approx(0.25)    # QQQ holdings data covers 25% of the fund
    assert r["currency"]["CAD"] == pytest.approx(0.4)


def test_rules_catch_tech_concentration_duplicates_and_single_class(rets):
    tech = rep({"NVDA": 0.3, "MSFT": 0.2, "QQQ": 0.4, "XBB.TO": 0.1}, rets)
    assert {c["rule"]: c["status"] for c in dv.check(tech)}["C3"] == "fail"          # Amira: not all tech
    dup = rep({"SPY": 0.5, "ESGV": 0.5}, rets)
    status = {c["rule"]: c["status"] for c in dv.check(dup)}
    assert status["C6"] == "fail" and status["C4"] == "fail"                         # same bet twice, equity only
    ok = rep({"SPY": 0.4, "RY.TO": 0.1, "XBB.TO": 0.4, "GLD": 0.1}, rets)
    assert all(c["status"] == "pass" for c in dv.check(ok))
    assert ok["diversification_ratio"] > 1 and ok["avg_correlation"] < dup["avg_correlation"]


def test_no_holdings_is_honest_and_json_ready(rets):
    r = rep({"QQQ": 0.6, "XBB.TO": 0.4}, rets, hold={})
    assert r["look_through_coverage"] == 0 and r["largest_company"] is None
    assert "lower bound" in dv.check(r)[0]["detail"]
    json.dumps(r)
    assert "holdings" in dv.describe(r)
