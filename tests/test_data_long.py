"""Longer histories (decision #31): assets that start later, stand-ins, FX without look-ahead, stress windows.
Offline: synthetic files, patched into dh.data."""
import numpy as np
import pandas as pd
import pytest

from dh import data, metrics
from dh.agents import market

DAYS = pd.bdate_range("2006-01-02", "2010-12-31")
START = {"SPY": "2006-01-02", "XBB.TO": "2006-01-02", "ESGV": "2008-06-02", "ZST.TO": "2009-01-05", "TSLA": "2010-06-29"}
CCY = {"SPY": "USD", "XBB.TO": "CAD", "ESGV": "USD", "ZST.TO": "CAD", "TSLA": "USD"}


def _install(monkeypatch, start=START, fx_start="2006-01-02", proxies=(("ESGV", "SPY"), ("ZST.TO", "cash"))):
    rng = np.random.default_rng(1)
    rows = []
    for t, s in start.items():
        d = DAYS[DAYS >= s]
        rows.append(pd.DataFrame({"date": d, "ticker": t, "adj_close": 100 * np.cumprod(1 + rng.normal(0, .01, len(d)))}))
    uni = pd.DataFrame({"ticker": list(start), "currency": [CCY[t] for t in start], "market": "x",
                        "name": list(start), "asset_class": "x", "sector": None})
    fxd = DAYS[DAYS >= fx_start]
    macro = pd.DataFrame({"date": [pd.Timestamp("2005-01-03"), pd.Timestamp("2008-12-09")], "series_id": "V39079",
                          "value": [2.5, 1.5]})
    monkeypatch.setattr(data, "prices", lambda: pd.concat(rows, ignore_index=True))
    monkeypatch.setattr(data, "universe", lambda: uni)
    monkeypatch.setattr(data, "fx", lambda: pd.Series(1.25, index=fxd))
    monkeypatch.setattr(data, "macro", lambda sid=None: macro[macro.series_id == sid] if sid else macro)
    cfg = data.Config(proxies=proxies)
    monkeypatch.setattr(data, "load_config", lambda path=None: cfg)
    data._panel.cache_clear(), data._returns.cache_clear()
    yield
    data._panel.cache_clear(), data._returns.cache_clear()


@pytest.fixture
def staggered(monkeypatch):
    yield from _install(monkeypatch)


def test_young_asset_is_missing_not_flat(staggered):
    r = data.returns()
    first = r["TSLA"].first_valid_index()
    assert first > pd.Timestamp("2010-06-29") and r.loc[: first - pd.Timedelta(days=1), "TSLA"].isna().all()
    port = metrics.portfolio_returns(r, {"SPY": .5, "TSLA": .5})
    assert port.index[0] >= first                     # the strategy's window starts at its youngest holding
    assert len(port) < len(r["SPY"].dropna())


def test_stand_ins_only_before_the_first_price(staggered):
    r, raw = data.returns(), data.price_panel().pct_change(fill_method=None).iloc[1:]
    zst_first = raw["ZST.TO"].first_valid_index()
    assert r["ZST.TO"].notna().all()
    cash = r.loc[r.index < zst_first, "ZST.TO"]
    days = (cash.index[-1] - r.index[r.index.get_loc(cash.index[-1]) - 1]).days   # a Monday accrues the weekend
    assert cash.iloc[-1] == pytest.approx(1.015 ** (days / 365.25) - 1, rel=1e-6)   # 1.5% rate after 2008-12-09
    assert (r.loc[r.index >= zst_first, "ZST.TO"] == raw.loc[raw.index >= zst_first, "ZST.TO"]).all()  # real after
    esgv_first = raw["ESGV"].first_valid_index()
    assert (r.loc[r.index < esgv_first, "ESGV"] == r.loc[r.index < esgv_first, "SPY"]).all()
    assert len(data.proxies_used()) == 2 and "ZST.TO before" in data.proxies_used()[1]


def test_no_stand_ins_when_none_configured(monkeypatch):
    for _ in _install(monkeypatch, proxies=()):
        assert data.returns()["ZST.TO"].isna().any() and data.proxies_used() == []


def test_usd_prices_before_fx_are_missing_not_back_filled(monkeypatch):
    for _ in _install(monkeypatch, fx_start="2007-01-02"):
        p = data.price_panel(["SPY", "XBB.TO"])
        assert p.loc[p.index < "2007-01-02", "SPY"].isna().all()       # no rate from the future
        assert p.loc[p.index < "2007-01-02", "XBB.TO"].notna().any()   # CAD asset unaffected


def test_same_start_gives_the_old_numbers(monkeypatch):
    same = {t: "2006-01-02" for t in START}
    for _ in _install(monkeypatch, start=same):
        wide = data.prices().pivot(index="date", columns="ticker", values="adj_close").sort_index().ffill()
        rate = data.fx().reindex(wide.index).ffill().bfill()
        for t in wide.columns:
            if CCY[t] == "USD":
                wide[t] = wide[t] * rate
        old = wide.pct_change(fill_method=None).iloc[1:]
        pd.testing.assert_frame_equal(data.returns()[old.columns], old)
        w = {"SPY": .4, "XBB.TO": .6}
        new, ref = metrics.portfolio_returns(data.returns(), w), old[list(w)].fillna(0) @ pd.Series(w)
        assert new.index.equals(ref.index)  # same days (no NaN to drop on equal starts)
        np.testing.assert_allclose(new.to_numpy(), ref.to_numpy(), rtol=0, atol=1e-12)  # not bit-equal on every BLAS (macOS)


def test_stress_windows_only_when_covered(staggered):
    r = data.returns()
    long = market.strategy_stats({"SPY": .6, "XBB.TO": .4}, rets=r)
    young = market.strategy_stats({"SPY": .5, "TSLA": .5}, rets=r)
    assert "stress_2008" in long and "stress_2008_drawdown" in long and long["stress_2008_drawdown"] <= 0
    assert "stress_2008" not in young and "stress_2020" not in long
    assert data.period_label(r) == "2006-2010"


def test_long_build_splices_fred_before_the_bank_of_canada(monkeypatch, tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("bld", data.ROOT / "scripts" / "build_long_data.py")
    bld = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bld)
    fake = type("M", (), {})()
    fake.START, fake.END, fake.RETRIEVED = "2005-01-03", "2005-01-10", "today"
    fake.boc = lambda sid: pd.DataFrame({"date": ["2005-01-06", "2005-01-07"], "value": [1.21, 1.22]})
    fake.get = lambda url: b"DATE,DEXCAUS\n2005-01-03,1.20\n2005-01-04,.\n2005-01-05,1.205\n2005-01-06,9.99\n"
    seen = {}
    fake.main = lambda: seen.update(fx=fake.boc("FXUSDCAD"))  # returns None, like the official main
    monkeypatch.setattr(bld, "load_official", lambda: fake)
    monkeypatch.setattr(bld, "verified_get", fake.get)  # the script installs its verified downloader
    assert bld.main(["--start", "2005-01-03", "--out", str(tmp_path)]) == 0
    fx = seen["fx"]
    assert list(fx["date"]) == ["2005-01-03", "2005-01-05", "2005-01-06", "2005-01-07"]  # FRED before, BoC from its 1st day
    assert list(fx["value"]) == [1.20, 1.205, 1.21, 1.22] and (tmp_path / "BUILD_INFO.txt").exists()
