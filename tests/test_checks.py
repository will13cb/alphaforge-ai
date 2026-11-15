"""Portfolio checks C-F (decision #20): one test per check, pass and fail/warn paths, offline (synthetic data,
ILLUSTRATIVE holdings or {})."""
import json

import numpy as np
import pandas as pd
import pytest

from dh.agents import checks as ck
from dh.agents import diversification as dv
from dh.agents import guardian
from dh.agents.profiler import derive_limits
from dh.agents.scenarios import AMIRA, MATEO, ROBERT

HOLD = {"QQQ": {"NVDA": 0.09, "MSFT": 0.08, "AAPL": 0.08}}  # ILLUSTRATIVE
SECTORS = {"NVDA": "Information Technology", "MSFT": "Information Technology", "AAPL": "Information Technology",
           "JNJ": "Health Care", "XOM": "Energy", "RY.TO": "Financials"}


def rep(w, hold=HOLD):
    return dv.report(w, holdings=hold, sectors=SECTORS, correlations=False)


def status(c):
    return c["status"]


def test_shape_is_the_same_for_every_check():
    lim = derive_limits(MATEO)
    s = {"weights": {"XIU.TO": 0.3, "SPY": 0.3, "XBB.TO": 0.3, "GLD": 0.1},
         "stats": {"max_drawdown": -0.12, "worst_12m": -0.08, "stress_2022_drawdown": -0.1, "cvar_95": 0.012},
         "diversification": rep({"XIU.TO": 0.3, "SPY": 0.3, "XBB.TO": 0.3, "GLD": 0.1})}
    out = ck.run(s, dict(MATEO, capital=100_000), lim, holdings={})
    assert [c["check"] for c in out][:10] == ["C1", "C2", "C3", "C3b", "C4", "C5", "C6", "D1", "D2", "D3"]
    assert all(set(c) == {"check", "value", "limit", "status", "reason", "source"} for c in out)
    assert all(c["status"] in ("pass", "warn", "fail") for c in out)
    json.dumps(out)
    assert "✔" in ck.summary(out)


def test_c1_company_through_etfs():
    w = {"QQQ": 0.5, "NVDA": 0.10, "XBB.TO": 0.4}                    # NVDA = 10% + 50% × 9% = 14.5%
    assert status(ck.c1_company(w, {"max_single": 0.12}, HOLD)) == "fail"
    assert status(ck.c1_company(w, {"max_single": 0.15}, HOLD)) == "pass"


def test_c1_uses_each_company_cap_and_agrees_with_g4():
    """Decision #24: each company has its own cap; C1 and G4 must give the same verdict (bug: C1 used max_single)."""
    lim = derive_limits(MATEO)
    caps = lim["company_caps"]
    assert caps["TSLA"] < lim["max_single"]                                   # TSLA's own cap is the strict one
    for t, x in (("TSLA", 0.10), ("TSLA", 0.05), ("JNJ", 0.10), ("NVDA", 0.12)):
        s = {"weights": {t: x, "ESGV": 0.5 - x, "XBB.TO": 0.5}, "stats": {"max_drawdown": -0.1}}
        c1 = ck.c1_company(s["weights"], lim, {})
        g4 = next(c for c in guardian.check_strategy(s, lim, MATEO, holdings={}) if c["rule"] == "G4")
        assert c1["status"] == g4["status"], (t, x, c1["reason"], g4["detail"])
        assert (c1["status"] == "fail") == (x > caps[t] + 1e-9)
    assert "TSLA 10.0% vs" in ck.c1_company({"TSLA": 0.10, "XBB.TO": 0.9}, lim, {})["reason"]


def test_c2_geography():
    assert status(ck.c2_geography({"XIU.TO": 0.4, "RY.TO": 0.1, "XBB.TO": 0.5}, {})) == "warn"   # 100% Canada
    assert status(ck.c2_geography({"XIU.TO": 0.3, "SPY": 0.3, "XBB.TO": 0.4}, {})) == "pass"     # 50/50


def test_c3_sector_two_levels_and_c3b_job_sector():
    assert status(ck.c3_sector(rep({"NVDA": 0.3, "MSFT": 0.15, "XBB.TO": 0.55}))) == "fail"      # 45% tech
    assert status(ck.c3_sector(rep({"NVDA": 0.2, "MSFT": 0.15, "XBB.TO": 0.65}))) == "warn"      # 35%
    assert status(ck.c3_sector(rep({"NVDA": 0.1, "XBB.TO": 0.9}))) == "pass"
    r = rep({"JNJ": 0.2, "XBB.TO": 0.8})
    assert status(ck.c3b_job_sector(r, {"employment_sector": "Health Care"})) == "fail"          # 20% > 15%
    assert status(ck.c3b_job_sector(r, {"employment_sector": "Energy"})) == "pass"
    assert status(ck.c3b_job_sector(r, {})) == "pass"


def test_c4_classes_and_c5_concentration():
    assert status(ck.c4_classes(rep({"SPY": 1.0}))) == "fail"
    assert status(ck.c4_classes(rep({"SPY": 0.6, "XBB.TO": 0.4}))) == "pass"
    assert status(ck.c5_concentration({"NVDA": 0.4, "MSFT": 0.3, "XOM": 0.3}, {})) == "warn"     # 3 names
    assert status(ck.c5_concentration({"SPY": 0.5, "XBB.TO": 0.5}, {})) == "pass"                # broad ETFs


def test_c6_duplicates_and_near_duplicates():
    idx = pd.bdate_range("2024-01-01", periods=300)
    rng = np.random.default_rng(0)
    m = rng.normal(0, 0.01, 300)
    rets = pd.DataFrame({"SPY": m + rng.normal(0, 0.0005, 300), "ESGV": m + rng.normal(0, 0.0005, 300),
                         "QQQ": m + rng.normal(0, 0.005, 300), "XBB.TO": rng.normal(0, 0.003, 300)}, index=idx)
    dup = {"SPY": 0.4, "ESGV": 0.3, "XBB.TO": 0.3}
    assert status(ck.c6_duplicates(dup, dv.report(dup, rets=rets, holdings={}), {}, rets)) == "fail"
    near = {"SPY": 0.4, "QQQ": 0.3, "XBB.TO": 0.3}                                               # ~0.9
    assert status(ck.c6_duplicates(near, dv.report(near, rets=rets, holdings={}), {}, rets)) == "warn"
    ok = {"SPY": 0.5, "XBB.TO": 0.5}
    assert status(ck.c6_duplicates(ok, dv.report(ok, rets=rets, holdings={}), {}, rets)) == "pass"


def test_d_risk_vs_client():
    prof = {"max_loss_pct": 20, "capital": 100_000}
    lim = {"loss_limit": 0.15, "max_drawdown": 0.15}
    assert status(ck.d1_tolerance({"max_drawdown": -0.10}, prof)) == "pass"
    assert status(ck.d1_tolerance({"max_drawdown": -0.18}, prof)) == "warn"                      # > 80% of 20%
    assert status(ck.d1_tolerance({"max_drawdown": -0.25}, prof)) == "fail"
    d2 = ck.d2_capacity({"max_drawdown": -0.18}, lim, prof)
    assert status(d2) == "fail" and "18,000 $ vs 15,000 $" in d2["reason"]
    assert status(ck.d2_capacity({"max_drawdown": -0.10}, lim, prof)) == "pass"
    st = {"worst_12m": -0.20, "stress_2022_drawdown": -0.12, "cvar_95": 0.015}
    assert status(ck.d3_stress(st, lim)) == "warn" and status(ck.d3_stress(dict(st, worst_12m=-0.05), lim)) == "pass"


def test_e_goal():
    o = {"risk_only": {"prob_target": 0.4, "prob_loss": 0.2}, "replay": {"prob_target": 0.8}}
    assert status(ck.e_goal(o, {"target_amount": 120_000})) == "warn"
    assert status(ck.e_goal({**o, "risk_only": {"prob_target": 0.6, "prob_loss": 0.1}}, {"target_amount": 1})) == "pass"
    assert status(ck.e_goal(None, {})) == "pass"


def test_f_profile_fit():
    by = lambda out: {c["check"]: c["status"] for c in out}
    lim = derive_limits(ROBERT)                                                                  # 4 y → 15% growth
    f = by(ck.f_profile({"SPY": 0.5, "XBB.TO": 0.5}, ROBERT, lim, {}))
    assert f["F2"] == "fail" and f["F3"] == "pass"
    assert by(ck.f_profile({"SPY": 0.1, "XBB.TO": 0.9}, dict(ROBERT, objective="safety_cushion"), lim, {}))["F1"] == "fail"
    beg = dict(AMIRA, knowledge_level="none", years_experience=0, quiz_correct=0)
    assert by(ck.f_profile({"NVDA": 0.1, "XBB.TO": 0.9}, beg, derive_limits(beg), {}))["F4"] == "fail"
    assert by(ck.f_profile({"XOM": 0.1, "XBB.TO": 0.9}, dict(MATEO, exclusions=[]), derive_limits(MATEO), {}))["F5"] == "warn"
    f6 = by(ck.f_profile({"XOM": 0.1, "XBB.TO": 0.9}, MATEO, derive_limits(MATEO), {}))       # fossil excluded, held
    assert f6["F6"] == "fail"
    via = by(ck.f_profile({"SPY": 0.5, "XBB.TO": 0.5}, MATEO, derive_limits(MATEO), {"SPY": {"XOM": 0.01}}))
    assert via["F6"] == "warn"


def test_guardian_g14_to_g17_call_the_checks():
    s = {"weights": {"XIU.TO": 0.10, "RY.TO": 0.05, "XBB.TO": 0.45, "ZST.TO": 0.40}, "stats": {"max_drawdown": -0.06}}
    out = {c["rule"]: c["status"] for c in guardian.check_strategy(s, derive_limits(ROBERT), ROBERT, holdings={})}
    assert out["G14"] == "warn" and out["G15"] == "pass" and out["G16"] == "pass" and out["G17"] == "pass"
    over = dict(s, stats={"max_drawdown": -0.20})
    assert {c["rule"]: c["status"] for c in guardian.check_strategy(over, derive_limits(ROBERT), ROBERT, holdings={})}["G17"] == "fail"
