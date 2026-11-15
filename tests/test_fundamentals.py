"""Dividend payout and coverage (dh.fundamentals, scripts/build_fundamentals.py). Offline: synthetic files."""
import importlib.util

import numpy as np
import pandas as pd
import pytest

from dh import data, fundamentals as f

DAYS = pd.bdate_range("2021-11-12", "2026-11-12")
FY = ["2023-12-31", "2024-12-31", "2025-12-31"]


def _annual(t, ni, div, fcf=(50, 50, 50), ccy="CAD"):
    rows = []
    for p, a, b, c in zip(FY, ni, div, fcf):
        for item, v in (("net_income_common", a), ("dividends_paid_common", b), ("free_cash_flow", c),
                        ("operating_cash_flow", 100)):
            rows.append(dict(ticker=t, period_end=p, item=item, value=v, currency=ccy, label="x",
                             source="test", retrieved="2026-11-15"))
    return rows


def _quarterly(t, amounts_by_year, monthly=False):
    rows = []
    for y, amt in amounts_by_year.items():
        months = range(1, 13) if monthly else (2, 5, 8, 11)
        rows += [dict(ex_date=pd.Timestamp(y, m, 15), ticker=t, action="dividend", value=amt, unit="CAD per share")
                 for m in months]
    return rows


@pytest.fixture
def files(tmp_path, monkeypatch):
    uni = pd.DataFrame([("COV", "Covered Co", "equity", "TSX", "CAD", "Industrials"),
                        ("THN", "Thin Co", "equity", "TSX", "CAD", "Consumer Staples"),
                        ("NOT", "Not Co", "equity", "TSX", "CAD", "Utilities"),
                        ("LOS", "Loss Co", "equity", "TSX", "CAD", "Materials"),
                        ("ZER", "No Dividend Co", "equity", "TSX", "CAD", "Information Technology"),
                        ("BNK", "Bank Co", "equity", "TSX", "CAD", "Financials"),
                        ("USD", "Reports in USD", "equity", "TSX", "CAD", "Industrials"),
                        ("NOS", "No statements", "equity", "TSX", "CAD", "Industrials"),
                        ("ETF", "A fund", "etf_equity", "TSX", "CAD", "Broad market (x)")],
                       columns=["ticker", "name", "asset_class", "market", "currency", "sector"])
    uni.to_csv(tmp_path / "assets_universe.csv", index=False)
    px = pd.concat([pd.DataFrame({"date": DAYS, "ticker": t, "close": 50.0, "adj_close": 50.0, "volume": 1000,
                                  "currency": "CAD"}) for t in uni.ticker])
    px.to_csv(tmp_path / "prices_daily.csv", index=False)
    acts = (_quarterly("COV", {2022: .50, 2023: .52, 2024: .55, 2025: .60, 2026: .60})
            + _quarterly("NOT", {2022: 1.0, 2023: 1.0, 2024: .5, 2025: .5, 2026: .5})       # a cut in 2024
            + _quarterly("ETF", {2022: .3, 2023: .3, 2024: .3, 2025: .3, 2026: .3})
            + _quarterly("THN", {2022: .1, 2023: .1, 2024: .1, 2025: .1, 2026: .1}, monthly=True))
    acts.append(dict(ex_date=pd.Timestamp("2023-12-20"), ticker="COV", action="dividend", value=5.0, unit="CAD per share"))
    acts = [a for a in acts if a["ex_date"] <= DAYS[-1]]
    pd.DataFrame(acts).to_csv(tmp_path / "corporate_actions.csv", index=False)
    (tmp_path / "fundamentals").mkdir()
    rows = (_annual("COV", (100, 100, 100), (40, 40, 40)) + _annual("THN", (100, 100, 100), (90, 90, 90))
            + _annual("NOT", (100, 100, 100), (120, 120, 120)) + _annual("LOS", (100, 100, -10), (30, 30, 30))
            + _annual("ZER", (100, 100, 100), (0, 0, 0)) + _annual("BNK", (100, 100, 100), (50, 50, 50), fcf=(1e6,) * 3)
            + _annual("USD", (100, 100, 100), (30, 30, 30), ccy="USD"))
    pd.DataFrame(rows).to_csv(tmp_path / "fundamentals" / "annual.csv", index=False)
    info = pd.DataFrame({"ticker": list(uni.ticker), "financial_currency": "CAD", "trading_currency": "CAD",
                         "retrieved": "2026-11-15", "error": ""})
    info.loc[info.ticker == "USD", "financial_currency"] = "USD"
    info.loc[info.ticker == "NOS", "error"] = "no statements returned"
    info.to_csv(tmp_path / "fundamentals" / "info.csv", index=False)
    cfg = data.Config(data_dir=tmp_path)
    monkeypatch.setattr(data, "load_config", lambda path=None: cfg)
    caches = (data.universe, data.prices, f.annual, f.info)
    for c in caches:
        c.cache_clear()
    yield tmp_path
    for c in caches:
        c.cache_clear()


@pytest.mark.parametrize("t,status,payout", [("COV", "covered", .4), ("THN", "thin", .9), ("NOT", "not covered", 1.2),
                                             ("LOS", "loss", None), ("ZER", "no dividend", 0.0)])
def test_status_from_the_statements(files, t, status, payout):
    d = f.dividend_facts(t)
    assert d["status"] == status, d["reason"]
    assert d["coverage"]["payout_ratio"] == (pytest.approx(payout) if payout is not None else None)


def test_the_status_uses_three_years_and_flags_cash():
    cov = dict(currency="CAD", dividends_paid_common=30.0, net_income_common=100.0, net_income_3y=200.0,
               dividends_3y=230.0, payout_ratio_3y=1.15, earnings_coverage_3y=200 / 230, fcf_coverage=.6,
               years_used=["a", "b", "c"])
    status, reason = f.verdict(cov)                       # 30% last year, 115% over 3 years (the BCE.TO pattern)
    assert status == "not covered" and "115% of the last 3 years" in reason and "0.6× the dividend" in reason
    assert f.verdict(cov, sector="Financials")[1].count("free cash flow") == 0      # meaningless for banks
    assert f.verdict(cov, sector="Real Estate")[0] == "not measurable"            # REIT: FFO needed
    assert f.verdict(dict(cov, earnings_coverage_3y=1.1, payout_ratio_3y=.91))[0] == "thin"
    assert f.verdict(dict(cov, net_income_3y=-5.0))[0] == "loss"
    assert "free cash flow was negative" in f.verdict(dict(cov, fcf_coverage=-2.8))[1]          # FTS.TO: not "-2.8×"


def test_three_year_payout_and_coverages(files):
    c = f.dividend_facts("LOS")["coverage"]
    assert c["payout_ratio_3y"] == pytest.approx(90 / 190) and c["earnings_coverage"] == pytest.approx(-10 / 30)
    assert f.dividend_facts("COV")["coverage"]["fcf_coverage"] == pytest.approx(50 / 40)


def test_history_specials_cuts_and_monthly_timing(files):
    h = f.dividend_facts("COV")["history"]
    assert h["special_dividends"] == {"2023-12-20": 5.0} and h["cuts"] == []      # a special is not a raise then a cut
    assert h["dps_by_year"][2023] == pytest.approx(4 * .52)                     # regular payments only
    assert h["dps_growth_per_year"] == pytest.approx((.60 / .50) ** (1 / 3) - 1)
    assert type(h["dps_growth_per_year"]) is float                                    # plain number, not np.float64
    assert h["yield_ttm"] == pytest.approx(h["dps_ttm"] / 50)
    assert f.dividend_facts("NOT")["history"]["cuts"] == [2024]
    assert f.dividend_facts("THN")["history"]["cuts"] == []                      # monthly payer, same amount


def test_caveats_and_funds(files):
    bank = f.dividend_facts("BNK")
    assert bank["coverage"]["fcf_coverage"] is None and any("banks" in n for n in bank["notes"])
    assert any("statements in USD" in n for n in f.dividend_facts("USD")["notes"])
    assert any("Utilities" in n or "utilities" in n for n in f.dividend_facts("NOT")["notes"])
    etf = f.dividend_facts("ETF")
    assert etf["status"] == "fund" and "coverage" not in etf and etf["history"]["yield_ttm"] > 0
    assert all("never for a backtest" in f.dividend_facts(t)["notes"][-1] for t in ("COV", "BNK"))


def test_errors_are_returned(files):
    assert "not in the loaded universe" in f.dividend_facts("XYZ")["error"]
    nos = f.dividend_facts("NOS")
    assert nos["status"] == "no data" and "no statements returned" in nos["reason"]
    (files / "fundamentals" / "annual.csv").unlink()
    f.annual.cache_clear()
    assert "make data-fundamentals" in f.dividend_facts("COV")["reason"]


def test_agent_tool_validates_and_rounds(files):
    from dh.agents import market
    assert "error" in market.dividend_facts("COV") and "error" in market.dividend_facts([f"T{i}" for i in range(11)])
    out = market.dividend_facts(["COV", "XYZ"])
    assert out["companies"][0]["status"] == "covered" and "error" in out["companies"][1] and "team rule" in out["rule"]


# ---- build script, offline ---------------------------------------------------------------------------------------

def _build():
    spec = importlib.util.spec_from_file_location("build_fundamentals", data.ROOT / "scripts" / "build_fundamentals.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_extract_takes_the_first_filled_label_year_by_year():
    mod = _build()
    cols = pd.to_datetime(["2025-12-31", "2024-12-31"])
    raw = {"income_stmt": pd.DataFrame({cols[0]: [200.0], cols[1]: [180.0]}, index=["Net Income Common Stockholders"]),
           "cashflow": pd.DataFrame({cols[0]: [np.nan, -90.0, 60.0], cols[1]: [-80.0, -85.0, 50.0]},
                                    index=["Common Stock Dividend Paid", "Cash Dividends Paid", "Free Cash Flow"]),
           "info": {"financialCurrency": "USD", "currency": "CAD"}}
    rows, info = mod.extract("ABC.TO", raw, "2026-11-15")
    div = {r["period_end"]: (r["value"], r["label"]) for r in rows if r["item"] == "dividends_paid_common"}
    assert div == {"2025-12-31": (90.0, "Cash Dividends Paid"), "2024-12-31": (80.0, "Common Stock Dividend Paid")}
    assert info["financial_currency"] == "USD" and info["error"] == "missing: operating_cash_flow"
    no_div = dict(raw, cashflow=raw["cashflow"].loc[["Free Cash Flow"]])
    rows, _ = mod.extract("ZZ", no_div, "2026-11-15")
    assert {r["value"] for r in rows if r["item"] == "dividends_paid_common"} == {0.0}   # none paid = 0, not missing


def test_build_keeps_going_when_one_ticker_fails(tmp_path, capsys):
    mod = _build()
    good = {"income_stmt": pd.DataFrame({pd.Timestamp("2025-12-31"): [1.0]}, index=["Net Income"]),
            "cashflow": pd.DataFrame({pd.Timestamp("2025-12-31"): [-0.5, 1.0, 2.0]},
                                     index=["Cash Dividends Paid", "Free Cash Flow", "Operating Cash Flow"]), "info": {}}

    def fetch(t):
        if t == "BAD":
            raise RuntimeError("Yahoo said no")
        return good
    assert mod.main(["--tickers", "OK", "BAD", "--out", str(tmp_path)], fetch=fetch) == 0
    info = pd.read_csv(tmp_path / "info.csv").set_index("ticker")
    assert "Yahoo said no" in info.loc["BAD", "error"] and pd.isna(info.loc["OK", "error"])
    assert set(pd.read_csv(tmp_path / "annual.csv").ticker) == {"OK"} and "BAD" in capsys.readouterr().out
