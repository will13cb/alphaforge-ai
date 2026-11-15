"""Fixes from the audit (notes/audit-2026-11-15.md, decision #34), each pinned by a test. Offline, synthetic data."""
import numpy as np
import pandas as pd
import pytest

from dh.agents import checks, diversification as dv, guardian, market, requests
from dh.personas import DISCLAIMER


def test_p6_g12_catches_a_loss_written_as_a_gain():
    s = {"weights": {"SPY": .15, "XBB.TO": .85}, "stats": {"max_drawdown": -0.086, "return_2022": 0.019}}
    g12 = lambda t: guardian.check_explanation(t + " " + DISCLAIMER, s, {}, {})[1]  # noqa: E731
    assert g12("Its worst drop was 8.6%.")["status"] == "pass"        # plain wording of a loss: fine
    assert g12("In 2022 it returned 1.9%.")["status"] == "pass"
    bad = g12("It gained 8.6% over the period.")
    assert bad["status"] == "fail" and "sign" in bad["detail"]
    assert g12("+8.6% in 2022")["status"] == "fail"
    assert g12("It rose by 1.9% in 2022.")["status"] == "pass"         # a real gain written as a gain


def test_p9_sharpe_is_against_cash():
    idx = pd.bdate_range("2021-11-15", "2026-11-12")
    rng = np.random.default_rng(3)
    r = pd.DataFrame({"ZST.TO": 0.0002 + rng.normal(0, 0.0003, len(idx)), "SPY": rng.normal(0.0005, 0.01, len(idx))},
                     index=idx)
    a = market.asset_summary(rets=r)
    assert abs(a.loc["ZST.TO", "sharpe"]) < 0.5                  # cash scores ~0 (was ~6 with rf = 0)
    assert market.cash_rate(r) == pytest.approx((1 + r["ZST.TO"]).prod() ** (261.0 / len(r)) - 1, rel=0.05)


def test_p10_c3_has_one_answer():
    rep = {"largest_sector": {"name": "Information Technology", "weight": 0.35}, "look_through_coverage": 1.0,
           "redundant_pairs": [], "n_asset_classes": 2, "asset_classes": {"equity": .6, "bonds": .4}}
    assert dv.check(rep)[0]["status"] == checks.c3_sector(rep)["status"] == "warn"


def test_c1_uses_each_companys_own_cap():
    lim = {"max_single": 0.10, "company_caps": {"TSLA": 0.03, "JNJ": 0.10}}
    c = checks.c1_company({"TSLA": 0.05, "JNJ": 0.08, "XBB.TO": 0.87}, lim, {})
    assert c["status"] == "fail" and "TSLA 5.0% vs 3.0%" in c["reason"]   # was ✔: 8% (JNJ) vs the 10% largest cap


def test_p21_crypto_pairs_use_weekly_correlation():
    idx = pd.bdate_range("2023-01-02", "2024-12-31")
    rng = np.random.default_rng(5)
    spy = rng.normal(0, 0.01, len(idx))
    btc = np.roll(spy, 1) * 2 + rng.normal(0, 0.01, len(idx))   # reacts a day later (UTC vs New York close)
    r = pd.DataFrame({"SPY": spy, "BTC-USD": btc, "QQQ": spy + rng.normal(0, 0.002, len(idx))}, index=idx)
    c = dv.corr_matrix(r)
    assert abs(r.corr().loc["SPY", "BTC-USD"]) < 0.2 < c.loc["SPY", "BTC-USD"]     # weekly sees the link
    assert c.loc["SPY", "QQQ"] == pytest.approx(r.corr().loc["SPY", "QQQ"])         # non-crypto pairs: daily


def test_p8_p13_no_noise_pros():
    def strat(ret, dd, n):
        return {"stats": {"max_drawdown": dd, "ann_return": ret, "return_2022": -0.05},
                "checks": [{"check": "C5", "status": "pass", "value": n, "reason": ""}]}
    ss = [strat(0.08, -0.10, 268.5), strat(0.0798, -0.12, 180.0)]
    requests.pros_cons(ss, {"loss_limit": 0.25, "max_drawdown": 0.25}, {})
    text = " ".join(p for s in ss for p in s["pros"])
    assert "highest return" not in text and "spread out" not in text


def test_one_dividend_list():
    from dh.agents.portfolio import STRATEGY_DEFS
    from dh.agents.rules import DIVIDEND_PAYERS, STOCKS
    assert {t for t in STRATEGY_DEFS["income"]["growth"] if t in STOCKS} == DIVIDEND_PAYERS


def test_no_smallest_and_largest_for_the_same_shown_number():
    def strat(dd):
        return {"stats": {"max_drawdown": dd, "ann_return": 0.05, "return_2022": -0.05}, "checks": []}
    ss = [strat(-0.0381), strat(-0.0384)]                       # both shown as -3.8%
    requests.pros_cons(ss, {"loss_limit": 0.15, "max_drawdown": 0.15}, {})
    text = " ".join(x for s in ss for x in s["pros"] + s["cons"])
    assert "smallest worst drop" not in text and "largest worst drop" not in text
