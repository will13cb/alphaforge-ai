"""Branch produit_cadusa: the catalogue, groups derived from data, the quality report, extra catalogues in dh.data,
and the build script. Offline: synthetic prices, a fake download."""
import importlib.util

import numpy as np
import pandas as pd
import pytest

from dh import data, products
from dh.agents import rules

DAYS = pd.bdate_range("2021-11-12", "2026-11-12")


# ---- catalogue ---------------------------------------------------------------------------------------------------

def test_catalogue_is_60_clean_products():
    cat = products.catalogue()
    assert len(cat) == 60 and cat.asset_id.is_unique and cat.ticker.is_unique
    assert products.validate_catalogue(cat) == []
    assert set(products.STARTER_COLUMNS) <= set(cat.columns)       # loadable next to the starter's file


def test_simplest_to_integrate():
    cat, start = products.catalogue(), products.starter_universe()
    assert set(cat.asset_class) <= set(start.asset_class)            # no new asset class
    assert not set(cat.ticker) & set(start.ticker)
    assert "Energy" not in set(cat.loc[cat.asset_class == "equity", "sector"])   # fossil-fuel list stays exact
    tsx = cat.ticker.str.endswith(".TO")
    assert (cat.loc[tsx, "currency"] == "CAD").all() and (cat.loc[tsx, "market"] == "TSX").all()
    assert (cat.loc[~tsx, "currency"] == "USD").all() and (cat.loc[~tsx, "market"] != "TSX").all()


def test_catalogue_fills_what_the_starter_lacks():
    cat, start = products.catalogue(), products.starter_universe()
    new_sectors = set(cat.loc[cat.asset_class == "equity", "sector"]) - set(start.loc[start.asset_class == "equity", "sector"])
    assert {"Materials", "Real Estate"} <= new_sectors
    assert {"silver", "gold", "international_developed", "emerging", "country", "inflation_linked", "cash",
            "high_yield", "corporate", "small_cap", "factor_dividend", "esg"} <= set(cat.sub_class)


def test_sector_labels_follow_the_checks_convention():
    """The checks count any label as a sector unless it starts with Broad market / Bonds / Gold / Commodities."""
    cat = products.catalogue()
    for _, r in cat.iterrows():
        assert r.sector in products.GICS_SECTORS or r.sector.startswith(products.NOT_A_SECTOR), r.ticker
    assert (cat.loc[cat.asset_class == "equity", "sector"].isin(products.GICS_SECTORS)).all()


def test_validate_catches_each_kind_of_error():
    good = products.catalogue().iloc[:1]
    row = lambda t, n, ac, sub, mk, ccy, sec="Materials", cx="USD": (t, n, ac, sub, mk, ccy, sec, "e", cx, "g")
    bad = pd.DataFrame([
        row("XEF.TO", "dup", "etf_equity", "x", "TSX", "CAD", "Broad market (x)", "Other"),   # duplicate
        row("SPY", "S&P 500", "etf_equity", "broad", "NYSE Arca", "USD", "Broad market (x)"),  # starter ticker
        row("ABC", "euro", "equity", "stock", "NYSE", "EUR"),                     # currency not convertible
        row("DEF", "fund", "etf_multi_asset", "x", "NYSE", "USD"),                # class the checks don't know
        row("GHI.TO", "usd on tsx", "equity", "stock", "TSX", "USD"),             # .TO priced in USD
        row("JKL", "nyse on tsx", "equity", "stock", "TSX", "USD"),               # U.S. ticker, TSX market
        row("MNO", None, "equity", "stock", "NYSE", "USD"),                       # missing name
        row("PQR", "odd", "equity", "fund", "NYSE", "USD"),                       # a company that isn't a stock
        row("STU", "pseudo sector", "etf_equity", "x", "NYSE", "USD", "Dividend (U.S.)"),  # would count as a sector
        row("VWX", "oil", "equity", "stock", "NYSE", "USD", "Energy"),            # fossil-fuel list to update
        row("YZA", "fx", "equity", "stock", "NYSE", "USD", "Materials", "EUR"),   # currency exposure label
    ], columns=products.COLUMNS)
    issues = products.validate_catalogue(pd.concat([good[products.COLUMNS], bad], ignore_index=True))
    found = {(i["ticker"], i["check"], i["status"]) for i in issues}
    for expected in [("XEF.TO", "unique", "fail"), ("SPY", "starter", "fail"), ("ABC", "currency", "fail"),
                     ("DEF", "asset_class", "fail"), ("GHI.TO", "currency", "fail"), ("JKL", "market", "fail"),
                     ("MNO", "name", "fail"), ("PQR", "sub_class", "warn"), ("STU", "sector", "fail"),
                     ("VWX", "exclusions", "warn"), ("YZA", "currency_exposure", "fail")]:
        assert expected in found, expected
    assert products.validate_catalogue(pd.DataFrame({"ticker": ["A"]}))[0]["check"] == "columns"


# ---- groups derived from data -------------------------------------------------------------------------------------

def test_groups_from_data_equal_rules_on_the_starter():
    g = products.asset_groups(products.starter_universe())
    assert g["stocks"] == rules.STOCKS and g["equity_etfs"] == rules.EQUITY_ETFS and g["bond_etfs"] == rules.BOND_ETFS
    assert g["crypto"] == rules.CRYPTO and g["gold"] == rules.GOLD and g["defensive"] == rules.DEFENSIVE
    assert g["etfs"] == rules.ETFS and g["universe"] == rules.UNIVERSE and rules.COMMODITIES == set()


def test_groups_on_the_catalogue_follow_the_defensive_definition():
    g = products.asset_groups(products.catalogue())
    assert g["gold"] == {"CGL.TO"} and g["commodities"] == {"SLV"}
    assert g["defensive"] == {"XSB.TO", "PSA.TO", "BNDX", "CGL.TO"}          # short, cash, aggregate, gold
    for t in ("XCB.TO", "XHY.TO", "XRB.TO", "TIP", "EMB", "SLV"):            # credit, inflation, EM or commodity risk
        assert t not in g["defensive"], t


def test_rules_add_the_catalogue_only_when_extra_is_set(monkeypatch):
    import importlib
    try:
        monkeypatch.setattr(data, "load_config", lambda path=None: data.Config(extra=("cadusa",)))
        r = importlib.reload(rules)
        assert {"LLY", "NTR.TO"} <= r.STOCKS and "XEF.TO" in r.EQUITY_ETFS and "SLV" in r.COMMODITIES <= r.ETFS
        assert {"XSB.TO", "PSA.TO", "BNDX", "CGL.TO"} <= r.DEFENSIVE and "CGL.TO" in r.GOLD
        assert r.EXCLUSIONS["single_stocks"] >= {"LLY"} and "LLY" in r.UNIVERSE
    finally:
        monkeypatch.setattr(data, "load_config", lambda path=None: data.Config())
        r = importlib.reload(rules)
    assert "LLY" not in r.STOCKS and r.COMMODITIES == set()


def test_checks_read_exposure_and_currency_risk(monkeypatch):
    from dh.agents import checks, diversification as dv, market
    monkeypatch.setattr(market, "countries", lambda tickers=None: {t: "Canada" if t.endswith(".TO") else "United States"
                                                                   for t in tickers})
    assert market.exposures(["XEF.TO", "XIU.TO", "EWJ"]) == {"XEF.TO": "Developed ex-North America",
                                                             "XIU.TO": "Canada", "EWJ": "Japan"}
    assert dv.currency_of("XEF.TO") == "Other" and dv.currency_of("XHY.TO") == "CAD"   # unhedged / CAD-hedged
    assert dv.currency_of("XIU.TO") == "CAD" and dv.currency_of("SPY") == "USD"        # starter unchanged
    monkeypatch.setattr(checks, "STOCKS", set()), monkeypatch.setattr(checks, "EQUITY_ETFS", {"XEF.TO", "XIU.TO"})
    c2 = checks.c2_geography({"XEF.TO": .6, "XIU.TO": .4}, {})                # before: "Canada 100%"
    assert c2["value"] == .6 and c2["reason"].startswith("Developed ex-North America 60%")
    assert "Other 60%" in c2["reason"] and "CAD 40%" in c2["reason"] and "where the holdings are" in c2["reason"]
    starter = checks.c2_geography({"XIU.TO": .6, "SPY": .4}, {})["reason"]     # starter text unchanged (demo cache)
    assert starter.endswith("(country of listing); currency CAD 60%, USD 40%") or "(country of listing)" in starter


def test_research_tools_only_with_extra(monkeypatch):
    from dh.agents import market
    assert market.agent_tools() == list(market.AGENT_TOOLS)                  # demo: the tool list is unchanged
    monkeypatch.setattr(data, "load_config", lambda path=None: data.Config(extra=("cadusa",)))
    assert market.agent_tools()[-1] is market.dividend_facts


# ---- quality report -----------------------------------------------------------------------------------------------

def _series(ticker, days=DAYS, ccy="USD", seed=0, volume=1_000):
    rng = np.random.default_rng(seed)
    px = 50 * np.cumprod(1 + rng.normal(0, .01, len(days)))
    return pd.DataFrame({"date": days, "ticker": ticker, "close": px, "adj_close": px, "volume": volume, "currency": ccy})


def _cat(*rows):
    return pd.DataFrame([(t, t, "etf_equity", "x", "NYSE Arca", c, "Broad market (x)", "e", c, "g") for t, c in rows],
                        columns=products.COLUMNS)


def _report(prices, *rows, start="2021-11-12"):
    return products.quality_report(prices, _cat(*rows), start, "2026-11-12").set_index("ticker")


def test_clean_series_is_ok():
    r = _report(_series("AAA"), ("AAA", "USD")).loc["AAA"]
    assert r.status == "ok" and r.history == "full_window" and r.years == pytest.approx(5.0, abs=.01)


def test_bad_inputs_fail_with_a_reason():
    s = _series("STR"); s["adj_close"] = s["adj_close"].astype(object); s.loc[10, "adj_close"] = "abc"
    z = _series("ZER"); z.loc[20, "adj_close"] = 0.0
    d = pd.concat([_series("DUP"), _series("DUP").iloc[:3]])
    m = _series("CCY", ccy="CAD")
    rep = _report(pd.concat([s, z, d, m]), ("STR", "USD"), ("ZER", "USD"), ("DUP", "USD"), ("CCY", "USD"), ("NONE", "USD"))
    assert (rep.status == "fail").all()
    assert "non-numeric" in rep.loc["STR", "reasons"] and "<= 0" in rep.loc["ZER", "reasons"]
    assert "duplicate dates" in rep.loc["DUP", "reasons"] and "catalogue says USD" in rep.loc["CCY", "reasons"]
    assert rep.loc["NONE", "reasons"] == "no prices downloaded"


def test_big_move_is_flagged_not_removed():
    s = _series("JMP"); s.loc[500:, ["close", "adj_close"]] *= 1.6
    r = _report(s, ("JMP", "USD")).loc["JMP"]
    assert r.status == "warn" and f"% on {DAYS[500].date()}" in r.reasons and r.rows == len(DAYS)


def test_stale_needs_zero_volume():
    s = _series("STL"); s.loc[100:107, ["close", "adj_close"]] = s.loc[99, "adj_close"]
    calm = s.copy(); calm["ticker"] = "TCK"                                     # same flat days, but traded
    s.loc[100:107, "volume"] = 0
    rep = _report(pd.concat([s, calm]), ("STL", "USD"), ("TCK", "USD"))
    assert rep.loc["STL", "stale_run"] == 8 and "stale" in rep.loc["STL", "reasons"]
    assert rep.loc["TCK", "stale_run"] == 0


def test_history_classes():
    ten = pd.bdate_range("2016-11-14", "2026-11-12")                              # a 10-year window
    late = _series("LTE", days=ten[ten >= "2018-02-01"])                         # 8.8 y: late, still >= 5 y
    short = _series("SHT", days=ten[ten >= "2024-01-11"])                        # 2.8 y
    rep = _report(pd.concat([late, short]), ("LTE", "USD"), ("SHT", "USD"), start="2016-11-14")
    assert rep.loc["LTE", "history"] == "late_start" and rep.loc["SHT", "history"] == "short_history"
    assert "short history" in rep.loc["SHT", "reasons"]


# ---- extra catalogues in dh.data ---------------------------------------------------------------------------------

def _write(folder, uni, px):
    folder.mkdir(parents=True, exist_ok=True)
    uni.to_csv(folder / "assets_universe.csv", index=False)
    px.to_csv(folder / "prices_daily.csv", index=False)


@pytest.fixture
def two_catalogues(tmp_path, monkeypatch):
    def setup(extra_uni=None, extra=("t",), fx_value=1.25):
        uni = pd.DataFrame({"ticker": ["SPY", "XIU.TO"], "currency": ["USD", "CAD"], "name": ["s", "x"],
                            "asset_class": "etf_equity", "market": ["NYSE Arca", "TSX"], "sector": "s"})
        _write(tmp_path, uni, pd.concat([_series("SPY", seed=1), _series("XIU.TO", ccy="CAD", seed=2)]))
        pd.DataFrame({"date": DAYS, "usdcad": fx_value}).to_csv(tmp_path / "fx_usdcad_daily.csv", index=False)
        eu = extra_uni if extra_uni is not None else pd.DataFrame(
            {"ticker": ["SLV", "XEF.TO"], "currency": ["USD", "CAD"], "name": ["s", "x"], "asset_class": "etf_equity",
             "market": ["NYSE Arca", "TSX"], "sector": "s", "exposure": ["Global", "Developed ex-North America"]})
        _write(tmp_path / "products_t", eu, pd.concat([_series(t, ccy=c, seed=3 + i)
                                                       for i, (t, c) in enumerate(zip(eu.ticker, eu.currency))]))
        cfg = data.Config(data_dir=tmp_path, extra=tuple(extra))
        monkeypatch.setattr(data, "load_config", lambda path=None: cfg)
        for f in (data.universe, data.prices, data.fx, data._panel, data._returns):
            f.cache_clear()
        return cfg
    yield setup
    for f in (data.universe, data.prices, data.fx, data._panel, data._returns):
        f.cache_clear()


def test_extra_catalogue_loads_in_cad_and_leaves_the_starter_unchanged(two_catalogues):
    two_catalogues(extra=())
    alone = data.returns()
    two_catalogues()
    both = data.returns()
    assert set(both.columns) == {"SPY", "XIU.TO", "SLV", "XEF.TO"}
    pd.testing.assert_frame_equal(both[alone.columns], alone)
    raw = data.prices().query("ticker == 'SLV'").set_index("date")["adj_close"]
    assert data.price_panel(["SLV"])["SLV"].iloc[5] == pytest.approx(raw.iloc[5] * 1.25)   # USD x USD/CAD
    raw_cad = data.prices().query("ticker == 'XEF.TO'").set_index("date")["adj_close"]
    assert data.price_panel(["XEF.TO"])["XEF.TO"].iloc[5] == pytest.approx(raw_cad.iloc[5])  # CAD untouched


def test_extra_catalogue_errors_are_explicit(two_catalogues, tmp_path):
    dup = pd.DataFrame({"ticker": ["SPY"], "currency": ["USD"], "name": ["s"], "asset_class": "etf_equity",
                        "market": ["NYSE Arca"], "sector": "s"})
    two_catalogues(extra_uni=dup)
    with pytest.raises(ValueError, match="more than one catalogue: SPY"):
        data.universe()
    two_catalogues(extra=("missing",))
    with pytest.raises(SystemExit, match="make data-products"):
        data.universe()
    eur = pd.DataFrame({"ticker": ["ASML.AS"], "currency": ["EUR"], "name": ["a"], "asset_class": "equity",
                        "market": ["Euronext"], "sector": "s"})
    two_catalogues(extra_uni=eur)
    with pytest.raises(ValueError, match=r"no CAD conversion for: ASML.AS \(EUR\)"):
        data.returns()


def test_market_tools_show_where_the_holdings_are(two_catalogues):
    from dh.agents import market
    two_catalogues()
    meta = market._meta()
    assert meta.loc["XEF.TO", "country"] == "Canada"                         # where it is listed
    assert meta.loc["XEF.TO", "exposure"] == "Developed ex-North America"    # where its holdings are


# ---- build script, offline ---------------------------------------------------------------------------------------

def _build_module():
    spec = importlib.util.spec_from_file_location("build_products", data.ROOT / "scripts" / "build_products.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_writes_starter_format_and_leaves_out_unusable(tmp_path, capsys):
    def fake_download(uni):
        ccy = dict(zip(uni.ticker, uni.currency))
        px = pd.concat([_series(t, ccy=ccy[t], seed=i, days=DAYS if t != "LLY" else DAYS[DAYS >= "2024-01-11"])
                        for i, t in enumerate(uni.ticker) if t != "SLV"])           # SLV: nothing came back
        for c in ("open", "high", "low"):
            px[c] = px["close"]
        return px, pd.DataFrame(columns=["ex_date", "ticker", "action", "value", "unit"])

    mod = _build_module()
    assert mod.main(["--out", str(tmp_path), "--tickers", "XEF.TO", "SLV", "LLY"], download=fake_download) == 0
    for f in ("assets_universe.csv", "prices_daily.csv", "corporate_actions.csv", "quality_report.csv", "sources_metadata.csv"):
        assert (tmp_path / f).exists(), f
    uni, rep = pd.read_csv(tmp_path / "assets_universe.csv"), pd.read_csv(tmp_path / "quality_report.csv")
    assert set(uni.ticker) == {"XEF.TO", "LLY"} and set(products.STARTER_COLUMNS) <= set(uni.columns)
    assert rep.set_index("ticker").loc["SLV", "status"] == "fail" and "SLV" in capsys.readouterr().out
    assert rep.set_index("ticker").loc["LLY", "history"] == "short_history"
    assert mod.main(["--out", str(tmp_path), "--tickers", "NOPE"], download=fake_download) == 1
