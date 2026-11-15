"""Research mode (harness.toml [data] extra set, branch produit_cadusa): profile-driven baskets in the Portfolio and
the F7 dividend check. Off by default: identical to the demo. Offline: patched config, coverage and groups."""
import pytest

from dh import data, fundamentals
from dh.agents import checks, portfolio

LIMITS = {"allowed_assets": ["XIU.TO", "SPY", "QQQ", "NVDA", "MSFT", "GOOGL", "ESGV", "XESG.TO", "XEF.TO", "XEC.TO",
                             "ZST.TO", "XBB.TO", "XSB.TO", "AGG", "GLD", "RY.TO", "TD.TO", "FTS.TO", "ENB.TO", "JNJ", "PG"],
          "loss_limit": 0.2}
PAYOUT_3Y = {"RY.TO": .42, "TD.TO": .54, "FTS.TO": .46, "ENB.TO": 1.30, "JNJ": .47, "PG": .64}


@pytest.fixture
def research(monkeypatch):
    monkeypatch.setattr(data, "load_config", lambda path=None: data.Config(extra=("cadusa",)))
    monkeypatch.setattr(portfolio, "EQUITY_ETFS", portfolio.EQUITY_ETFS | {"XEF.TO", "XEC.TO", "XESG.TO"})
    monkeypatch.setattr(fundamentals, "coverage", lambda t, years=3: {"payout_ratio_3y": PAYOUT_3Y[t]})


def test_off_by_default_the_baskets_are_the_demo_ones():
    g, d, _ = portfolio.baskets("core", {"interests": ["esg"], "horizon_years": 4}, LIMITS)
    assert set(g) == {"XIU.TO", "ESGV"} and set(d) == {"ZST.TO", "XBB.TO"}


def test_esg_replaces_xiu_by_xesg(research):
    g, _, notes = portfolio.baskets("core", {"interests": ["esg"], "horizon_years": 10}, LIMITS)
    assert set(g) == {"XESG.TO", "ESGV"} and any("XESG.TO" in n for n in notes)       # replaced, never both (C6)


@pytest.mark.parametrize("horizon,bond", [(4, "XSB.TO"), (5, "XSB.TO"), (10, "XBB.TO")])
def test_short_horizon_takes_short_bonds(research, horizon, bond):
    _, d, _ = portfolio.baskets("core", {"horizon_years": horizon}, LIMITS)
    assert bond in d and ({"XBB.TO", "XSB.TO"} - {bond}).isdisjoint(d)


def test_income_names_must_be_covered(research):
    g, _, notes = portfolio.baskets("income", {"horizon_years": 10}, LIMITS)
    assert "ENB.TO" not in g and {"RY.TO", "TD.TO", "FTS.TO", "JNJ", "PG"} <= set(g)
    assert any("ENB.TO left out" in n and "130%" in n for n in notes)
    assert sum(g.values()) == pytest.approx(1)


def test_income_unchanged_when_statements_are_missing(research, monkeypatch):
    def missing(t, years=3):
        raise SystemExit("annual.csv missing")
    monkeypatch.setattr(fundamentals, "coverage", missing)
    g, _, notes = portfolio.baskets("income", {"horizon_years": 10}, LIMITS)
    assert "ENB.TO" in g and any("not checked" in n for n in notes)


def test_international_only_when_one_country_is_over_the_c2_limit(research):
    core, _, _ = portfolio.baskets("core", {"horizon_years": 10}, LIMITS)              # 50/50: C2 fine
    assert not {"XEF.TO", "XEC.TO"} & set(core)
    g, _, notes = portfolio.baskets("growth", {"horizon_years": 10}, LIMITS)           # all U.S.
    intl = g["XEF.TO"] + g["XEC.TO"]
    assert g["XEF.TO"] == pytest.approx(3 * g["XEC.TO"]) and intl == pytest.approx(.30)
    assert 1 - intl <= portfolio.MAX_COUNTRY_EQUITY + 1e-9 and any("United States was 100%" in n for n in notes)


def test_f7_warns_only_in_research_mode(monkeypatch):
    w = {"ENB.TO": .1, "RY.TO": .1, "XIU.TO": .8}
    facts = {"ENB.TO": {"status": "not covered", "reason": "dividends are 130% of the last 3 years' earnings"},
             "RY.TO": {"status": "covered", "reason": "42%"}}
    monkeypatch.setattr(fundamentals, "dividend_facts", lambda t: facts[t])
    monkeypatch.setattr(fundamentals, "annual", lambda: None)
    assert not checks.data_extra()                                                      # demo: F7 never added
    assert checks.f7_dividends(w)["status"] == "warn" and "ENB.TO" in checks.f7_dividends(w)["reason"]
    monkeypatch.setattr(data, "load_config", lambda path=None: data.Config(extra=("cadusa",)))
    assert checks.data_extra()
    def missing():
        raise SystemExit("missing")
    monkeypatch.setattr(fundamentals, "annual", missing)
    assert checks.f7_dividends(w) is None                                               # no data → no row, no guess


# ---- dividends across the architecture (Guardian G19, F1, Explainer, funds) ---------------------------------------

HELD = [{"ticker": "RY.TO", "status": "covered", "payout_3y": .42, "reason": "dividends are 42% of the last 3 years' earnings"},
        {"ticker": "ENB.TO", "status": "not covered", "payout_3y": 1.30,
         "reason": "dividends are 130% of the last 3 years' earnings (more than earned)"}]


def test_g18_exists_only_in_research_mode(monkeypatch):
    import importlib
    from dh.agents import guardian
    assert "G19" not in guardian.RULES                                       # demo: 17 rules
    try:
        monkeypatch.setattr(data, "load_config", lambda path=None: data.Config(extra=("cadusa",)))
        g = importlib.reload(guardian)
        assert "G19" in g.RULES
        monkeypatch.setattr(checks, "f7_dividends", lambda w: {"status": "warn", "reason": "ENB.TO: 130%"})
        rows = [r for r in g._portfolio_checks({"weights": {"ENB.TO": .2, "XIU.TO": .8}, "stats": {}}, {}, {}, {})
                if r["rule"] == "G19"]
        assert rows and rows[0]["status"] == "warn" and "ENB.TO" in rows[0]["detail"]
    finally:
        monkeypatch.setattr(data, "load_config", lambda path=None: data.Config())
        importlib.reload(guardian)


def test_f1_income_counts_covered_payers_and_dividend_etfs(monkeypatch):
    w = {"RY.TO": .2, "ENB.TO": .2, "XEI.TO": .2, "SPY": .4}
    base = {"horizon_years": 10, "objective": "income"}
    lim = {"horizon_max_growth": 1, "liquidity_floor": 0, "knowledge_score": 4, "allowed_assets": list(w)}
    f1 = lambda: next(c for c in checks.f_profile(w, base, lim, {}) if c["check"] == "F1")
    assert f1()["value"] == .4                                              # demo: the fixed list (RY, ENB)
    monkeypatch.setattr(data, "load_config", lambda path=None: data.Config(extra=("cadusa",)))
    monkeypatch.setattr(fundamentals, "covered_payers", lambda w: {"RY.TO"})
    c = f1()
    assert c["value"] == .4 and "covered by their earnings or dividend ETFs" in c["reason"]   # RY + XEI, not ENB


def test_explainer_facts_carry_dividends_only_in_research_mode(monkeypatch):
    from dh.agents import explainer
    assert explainer._dividend_facts({"RY.TO": .5}) == {}                    # demo: facts and cache hash unchanged
    monkeypatch.setattr(data, "load_config", lambda path=None: data.Config(extra=("cadusa",)))
    monkeypatch.setattr(fundamentals, "held_dividends", lambda w: HELD)
    f = explainer._dividend_facts({"RY.TO": .5, "ENB.TO": .5})
    assert [d["status"] for d in f["dividends"]] == ["covered", "not covered"]
    assert f["dividends"][1]["share_of_3y_earnings_paid"] == "130.0%" and "80%" in f["dividends_rule"]
    ph, table = explainer.placeholders(f)                                    # strict G12: numbers become ids
    assert "130.0%" not in str(ph) and "130.0%" in table.values()


def test_fund_reason_gives_its_distributions(monkeypatch):
    monkeypatch.setattr(data, "universe", lambda: __import__("pandas").DataFrame(
        [("XEI.TO", "x", "etf_equity", "TSX", "CAD", "Broad market (x)")],
        columns=["ticker", "name", "asset_class", "market", "currency", "sector"]))
    monkeypatch.setattr(fundamentals, "dividend_history", lambda t: {"yield_ttm": .051, "cuts": [2023]})
    d = fundamentals.dividend_facts("XEI.TO")
    assert d["status"] == "fund" and "5.1% of the price over 12 months" in d["reason"] and "2023" in d["reason"]
