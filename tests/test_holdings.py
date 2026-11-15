"""Holdings ingest: issuer-style raw files → etf_holdings.csv → {etf: {holding: weight}}. Offline, fake files."""
import pytest

from dh.holdings import build, holdings

XIU_RAW = """iShares S&P/TSX 60 Index ETF
Fund Holdings as of,"Nov 12, 2026"

Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Location
RY,ROYAL BANK OF CANADA,Financials,Equity,"1,000",60.00,Canada
BBD.B,BOMBARDIER INC CLASS B,Industrials,Equity,500,39.50,Canada
CAD,CAD CASH,Cash and/or Derivatives,Cash,10,0.50,Canada

The content contained herein is owned or licensed by BlackRock.
"""

SPY_RAW = """Fund Name:,SPDR S&P 500 ETF Trust
Holdings:,As of 12-Nov-2026

Name,Ticker,Identifier,Weight,Sector
ALPHABET INC CL A,GOOGL,x,3.0,-
ALPHABET INC CL C,GOOG,x,2.0,-
DOLLAR GENERAL CORP,DG,x,1.0,-
OTHER CO,OTH,x,93.9,-
US DOLLAR,-,x,0.1,-
"""


@pytest.fixture
def built(tmp_path):
    raw = tmp_path / "holdings"
    raw.mkdir()
    (raw / "XIU_holdings.csv").write_text(XIU_RAW)
    (raw / "holdings-daily-us-en-spy.csv").write_text(SPY_RAW)
    out = tmp_path / "etf_holdings.csv"
    return build(raw, out), out


def test_mapping(built):
    df, out = built
    h = holdings(out)
    assert h["XIU.TO"] == pytest.approx({"RY.TO": 0.60, "BBD-B.TO": 0.395})       # .TO suffix, % → fraction
    assert h["SPY"]["GOOGL"] == pytest.approx(0.05) and "GOOG" not in h["SPY"]   # share classes merged
    assert h["SPY"]["DG"] == pytest.approx(0.01)                                 # Dollar General is not cash
    assert set(df.as_of) == {"2026-11-12"}
    assert df.groupby("etf").weight.sum().tolist() == pytest.approx([1.0, 1.0])  # cash kept as "other"


def test_missing_file_is_direct_only(tmp_path):
    assert holdings(tmp_path / "nope.csv") == {}
