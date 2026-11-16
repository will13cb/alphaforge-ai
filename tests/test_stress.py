"""“What if March 2020 happened again?” (decision #50): offline, on a synthetic data/raw_stress folder."""
import numpy as np
import pandas as pd
import pytest

from dh import data, stress

DAYS = pd.bdate_range("2019-12-02", "2020-06-30")
PEAK, TROUGH = pd.Timestamp("2020-02-19"), pd.Timestamp("2020-03-23")


def _write(folder, crash=-0.30, fx_jump=0.0, tickers=("SPY", "XBB.TO")):
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    n = ((DAYS > PEAK) & (DAYS <= TROUGH)).sum()
    for t in tickers:
        daily = np.where((DAYS > PEAK) & (DAYS <= TROUGH), (1 + (crash if t == "SPY" else 0.0)) ** (1 / n) - 1, 0.0)
        rows.append(pd.DataFrame({"date": DAYS, "ticker": t, "adj_close": 100 * np.cumprod(1 + daily)}))
    pd.concat(rows).to_csv(folder / "prices_daily.csv", index=False)
    pd.DataFrame({"ticker": list(tickers), "currency": ["USD" if t == "SPY" else "CAD" for t in tickers],
                  "market": "x", "name": list(tickers), "asset_class": "x"}).to_csv(
        folder / "assets_universe.csv", index=False)
    fx = np.where(DAYS > PEAK, 1.30 * (1 + fx_jump), 1.30)
    pd.DataFrame({"date": DAYS, "usdcad": fx}).to_csv(folder / "fx_usdcad_daily.csv", index=False)
    pd.DataFrame({"date": [DAYS[0]], "series_id": ["V39079"], "value": [1.75]}).to_csv(
        folder / "macro_rates.csv", index=False)
    data._panel.cache_clear(), data._returns.cache_clear(), data._files_at.cache_clear()
    return folder


def test_replay_numbers_and_limit(tmp_path):
    f = _write(tmp_path / "raw_stress")
    res = stress.replay({"SPY": .5, "XBB.TO": .5}, loss_limit=.15, capital=400_000, folder=f)
    assert res["available"]
    n = ((DAYS > PEAK) & (DAYS <= TROUGH)).sum()
    d = 0.7 ** (1 / n) - 1
    expected = (1 + 0.5 * d) ** n - 1                                   # half in a −30% asset, rebalanced daily
    assert res["deepest_drop"] == pytest.approx(expected, abs=1e-9)
    assert res["deepest_drop_cad"] == round(-expected * 400_000)
    assert res["loss_limit_cad"] == 60_000
    assert res["worst_holdings"][0]["ticker"] == "SPY"
    assert res["path"][0]["date"] == "2019-12-03" and res["path"][-1]["date"] == "2020-06-30"
    res = stress.replay({"SPY": .3, "XBB.TO": .7}, loss_limit=.15, capital=400_000, folder=f)
    assert res["within_limit"] and res["margin"] > 0
    assert "sous votre limite de 15 %" in stress.sentence(res, "fr")
    assert "within your 15% limit" in stress.sentence(res, "en")
    res = stress.replay({"SPY": .8, "XBB.TO": .2}, loss_limit=.15, folder=f)
    assert res["within_limit"] is False and "au-delà" in stress.sentence(res, "fr")


def test_weaker_cad_softens_us_drop(tmp_path):
    f = _write(tmp_path / "raw_stress", fx_jump=0.10)
    res = stress.replay({"SPY": 1.0}, folder=f)
    assert res["deepest_drop"] > -0.30                                  # in CAD, less than −30%
    assert any("Canadian dollar fell" in a for a in res["assumptions"])


def test_missing_history_is_not_replayed(tmp_path):
    f = _write(tmp_path / "raw_stress")
    res = stress.replay({"SPY": .5, "NVDA": .5}, folder=f)
    assert not res["available"] and res["missing"] == ["NVDA"]
    assert not stress.replay({"SPY": 1}, folder=tmp_path / "nowhere")["available"]


def test_starter_calculations_untouched(tmp_path):
    """The replay reads its own folder: the harness's config (and so every 2021-2026 number) is unchanged."""
    _write(tmp_path / "raw_stress")
    assert stress.config(tmp_path / "raw_stress").data_dir != data.load_config().data_dir
    assert data.load_config().start == ""
