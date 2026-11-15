"""Portfolio (layer 3, decision #17) on synthetic returns: no starter CSVs, no holdings file, no LLM."""
import numpy as np
import pandas as pd
import pytest

from dh.agents import portfolio
from dh.agents.pipeline import run
from dh.agents.profiler import derive_limits
from dh.agents.rules import CRYPTO, DEFENSIVE, EXCLUSIONS, STOCKS, UNIVERSE
from dh.agents.scenarios import AMIRA, MATEO, ROBERT


@pytest.fixture(autouse=True)
def fewer_scenarios(monkeypatch):
    """goal_outlook is the slow part (Joud's bootstrap); the method is the same with fewer paths."""
    monkeypatch.setattr(portfolio, "N_SEARCH", 100)
    monkeypatch.setattr(portfolio, "N_FINAL", 200)
    for k in ("N_LOSS", "N_LOSS_FINAL", "N_RANGE"):       # the loss model (R1): same method, fewer paths
        monkeypatch.setattr(portfolio, k, 300)


@pytest.fixture(scope="module")
def rets():
    """Every universe ticker; stocks fall together in 2022, aggregate bonds dip, ZST barely moves."""
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
        else:  # equity ETFs
            cols[t] = mkt + rng.normal(0, 0.002, len(idx))
    return pd.DataFrame(cols, index=idx)


def propose(profile, rets):
    return portfolio.propose(profile, derive_limits(profile), rets=rets, holdings={})


@pytest.mark.parametrize("p", [AMIRA, MATEO, ROBERT], ids=["amira", "mateo", "robert"])
def test_ceiling_respects_loss_limit_and_is_the_largest(p, rets):
    """Decision R1: scanning up, every share up to the ceiling keeps P(drop deeper than the loss limit over the
    horizon) ≤ alpha, and the next scanned share breaks it (unless the horizon rule or the floor stopped first). The
    final weights pass the same rule in a fresh simulation (G7 = D2)."""
    lim = derive_limits(p)
    ss = propose(p, rets)
    assert 1 <= len(ss) <= 3
    for s in ss:
        rk = s["risk"]
        assert rk["exceedance"] <= rk["alpha"] + rk["tolerance"] + 1e-9
        assert sum(s["weights"].values()) == pytest.approx(1.0)
        assert set(s["weights"]) <= set(lim["allowed_assets"])
        if s["level"]["rank"] != 1:  # lower levels stop below the ceiling on purpose (#32)
            assert s["split"]["growth"] <= s["level"]["target_growth"] + 1e-9
            continue
        ceil = s["split_range"]["ceiling"]
        scanned = [c for c in s["split_curve"] if c["exceedance"] is not None]
        assert all(c["exceedance"] <= rk["alpha"] + 1e-9 for c in scanned if c["growth"] <= ceil + 1e-9)
        nxt = [c for c in scanned if c["growth"] > ceil + 1e-9]
        if s["split_range"]["set_by"] == "worst_drop":
            assert nxt and nxt[0]["exceedance"] > rk["alpha"]   # the next step up breaks the rule


def test_liquidity_floor_is_hard(rets):
    p = {**AMIRA, "withdrawal_share_3y": 0.6}
    for s in propose(p, rets):
        assert s["split"]["defensive"] >= 0.6 - 1e-9


def test_conflict_when_goal_needs_more_risk_than_accepted(rets):
    p = {**ROBERT, "target_amount": 4_000_000}
    s = propose(p, rets)[0]
    assert s["split_range"]["conflict"] is True
    assert "Options:" in s["split_range"]["conflict_message"]


def test_beginner_gets_broad_etfs_only(rets):
    p = {**MATEO, "knowledge_level": "none", "quiz_correct": 0}
    ss = propose(p, rets)
    assert {s["flavour"] for s in ss} == {"core"}          # broad ETFs only, at up to 3 risk levels (#32)
    assert all(not set(s["weights"]) & (STOCKS | CRYPTO) for s in ss)


def test_esg_and_fossil_exclusion(rets):
    for s in propose(MATEO, rets):
        assert not set(s["weights"]) & EXCLUSIONS["fossil_fuels"]
        assert "SPY" not in s["weights"]


def test_robert_has_no_crypto_and_no_growth_tilt(rets):
    ss = propose(ROBERT, rets)
    assert all(not set(s["weights"]) & CRYPTO for s in ss)
    assert "growth" not in [s["key"] for s in ss]


def test_rounding_never_pushes_a_line_over_its_cap():
    """Caps that aren't multiples of 0.5% (5.8%, 8.8%): rounding used to give 6.0% / 9.0% and the Guardian dropped it."""
    g = {"QQQ": 0.40, "SPY": 0.25, "NVDA": 0.10, "MSFT": 0.10, "GOOGL": 0.05, "BTC-USD": 0.07, "ETH-USD": 0.03}
    caps = {t: 0.088 for t in STOCKS}
    for share in (0.6, 0.75, 0.9, 0.95):
        lim = {"max_crypto": 0.058, "company_caps": caps, "max_single": 0.088, "min_defensive": 0.05}
        w, _ = portfolio.build(g, {"ZST.TO": 0.5, "GLD": 0.5}, share, lim, holdings={})
        assert sum(v for t, v in w.items() if t in CRYPTO) <= 0.058 + 1e-9
        assert all(v <= 0.088 + 1e-9 for t, v in w.items() if t in STOCKS)
        assert sum(w.values()) == pytest.approx(1.0)


@pytest.mark.parametrize("p", [AMIRA, MATEO, ROBERT], ids=["amira", "mateo", "robert"])
def test_pipeline_proposals_pass_the_guardian(p, rets):
    res = run(p, holdings={}, rets=rets)
    assert res["strategies"], res["trace"].markdown()
    assert all(s["guardian"]["verdict"] != "fail" for s in res["strategies"])
    agents = [st["agent"] for st in res["trace"].steps]
    assert agents[:3] == ["Profiler", "Market data", "Portfolio"]


def test_crypto_only_if_asked(rets):
    """Crypto is never added by default: an AI-curious client who didn't ask gets a growth tilt without it."""
    p = {**AMIRA, "interests": ["ai"], "products_held": ["etfs", "stocks"]}
    ss = propose(p, rets)
    g = next(s for s in ss if s["key"] == "growth")
    assert not set(g["weights"]) & CRYPTO
    assert any("didn't ask" in a for a in g["adjustments"])


def test_crypto_kept_only_when_asked_allowed_and_model_agrees(rets):
    lim = derive_limits(AMIRA)
    g = next(s for s in propose(AMIRA, rets) if s["key"] == "growth")
    held = set(g["weights"]) & CRYPTO
    note = next(a for a in g["adjustments"] if a.startswith("crypto "))
    if held:
        assert note.startswith("crypto kept") and sum(g["weights"][t] for t in held) <= lim["max_crypto"] + 1e-9
    else:
        assert "growth assets" in note  # the model (growth ceiling) said no, with numbers


def test_requested_crypto_counts_as_asking(rets):
    p = {**AMIRA, "interests": [], "requested_positions": {"BTC-USD": 0.03}}
    assert "growth" in [k for k, _ in portfolio.offered(p, derive_limits(p))]


@pytest.mark.parametrize("p", [AMIRA, MATEO, ROBERT], ids=["amira", "mateo", "robert"])
def test_strategies_are_different_risk_levels(p, rets):
    """Decision #32: each strategy is a real risk level, at least 5 points of growth apart, most growth first,
    unique keys; every one stays inside the client's own limits (lower levels only add defensive weight)."""
    lim = derive_limits(p)
    ss = propose(p, rets)
    g = [s["split"]["growth"] for s in ss]
    assert g == sorted(g, reverse=True) and all(a - b >= 0.05 - 1e-9 for a, b in zip(g, g[1:]))
    assert [s["level"]["rank"] for s in ss] == sorted(s["level"]["rank"] for s in ss) and ss[0]["level"]["rank"] == 1
    assert len({s["key"] for s in ss}) == len(ss) and len({s["name"] for s in ss}) == len(ss)
    for s in ss:
        assert s["split"]["defensive"] >= lim["min_defensive"] - 1e-9
        assert s["risk"]["exceedance"] <= s["risk"]["alpha"] + s["risk"]["tolerance"] + 1e-9
        assert s["split_range"]["set_by"] in ("worst_drop", "horizon", "liquidity", "safety", "level")
        assert any(a.startswith("split ") and "set by" in a for a in s["adjustments"])


@pytest.mark.parametrize("p", [AMIRA, MATEO, ROBERT], ids=["amira", "mateo", "robert"])
def test_levels_are_ordered_by_measured_risk(p, rets):
    """Audit A3, decision R5: a 'more prudent' level never has a deeper worst drop AND a higher chance of loss than the
    level above (inverted levels are dropped), all levels share level 1's defensive basket, and every section of
    every strategy describes its final weights (A6)."""
    from dh.risk import levels as rl
    from dh.risk import sync
    ss = propose(p, rets)
    assert all(s["baskets"]["defensive"] == ss[0]["baskets"]["defensive"] for s in ss)
    ladder = [(s["name"], rl.risk_vector(s)) for s in ss]
    assert not [i for i in rl.check_labels(ladder) if i.code == "C-inverted"]
    assert all(sync.verify(s, rets) == [] for s in ss)



@pytest.mark.parametrize("p", [AMIRA, ROBERT], ids=["amira", "robert"])
def test_zero_loss_limit_runs_to_a_fail_with_reasons(p, rets):
    """max_loss_pct 0 used to stop the whole run (ValueError in the loss model, then a division by a 0% company cap in
    G4 for an existing portfolio): now nothing fits, the Guardian says why, and the existing portfolio is reviewed."""
    prof = {**p, "max_loss_pct": 0, "existing_positions": {"TSLA": 20000, "XBB.TO": 80000}}
    res = run(prof, rets=rets, holdings={}, critic=False)
    assert res["limits"]["loss_limit"] == 0 and res["verdict"] == "fail" and not res["strategies"]
    assert any("G7" in c["rule"] for s in res["dropped"] for c in s["guardian"]["checks"] if c["status"] == "fail")
    assert "could not be reviewed" not in res["trace"].markdown()
