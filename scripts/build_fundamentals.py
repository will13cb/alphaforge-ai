"""Annual statements for every stock of the loaded universe → data/raw/fundamentals/ (gitignored).

    python scripts/build_fundamentals.py                 # every stock in dh.data.universe() (starter + harness extra)
    python scripts/build_fundamentals.py --tickers ENB.TO RY.TO

Yahoo Finance via yfinance (`income_stmt`, `cashflow`, `info`). Kept, per fiscal year (up to 4-5 years):
net income to common shareholders (else net income), dividends paid to common shareholders (else all cash dividends),
free cash flow, operating cash flow, in the statements' own currency. A ticker whose statements are missing is listed
in info.csv with the reason, never dropped silently. dh.fundamentals turns them into payout and coverage.
Snapshot of what is published today: not point-in-time, never for a backtest.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# item → Yahoo row labels, first found wins
ROWS = {
    "net_income_common": ("income_stmt", ["Net Income Common Stockholders", "Net Income"]),
    "dividends_paid_common": ("cashflow", ["Common Stock Dividend Paid", "Cash Dividends Paid"]),
    "free_cash_flow": ("cashflow", ["Free Cash Flow"]),
    "operating_cash_flow": ("cashflow", ["Operating Cash Flow"]),
}
SOURCE = "Yahoo Finance via yfinance (annual income statement and cash flow)"


def yahoo_fetch(ticker: str) -> dict:
    """{'income_stmt': DataFrame, 'cashflow': DataFrame, 'info': dict}, Yahoo's own layout (rows = items)."""
    import yfinance as yf
    k = yf.Ticker(ticker)
    return {"income_stmt": k.income_stmt, "cashflow": k.cashflow, "info": k.info or {}}


def extract(ticker: str, raw: dict, retrieved: str) -> tuple[list[dict], dict]:
    """Long rows for one ticker + its info row. Dividends paid are stored as a positive amount."""
    info = raw.get("info") or {}
    ccy = info.get("financialCurrency") or info.get("currency")
    rows, missing = [], []
    for item, (stmt, labels) in ROWS.items():
        df = raw.get(stmt)
        present = [x for x in labels if df is not None and x in df.index]
        if not present:
            missing.append(item)
            continue
        # year by year, the first label that has a number (Yahoo can keep a row but leave its recent years empty:
        # "Common Stock Dividend Paid" empty for L.TO and V since 2024, "Cash Dividends Paid" filled)
        for period in df.columns:
            label = next((x for x in present if pd.notna(pd.to_numeric(df.loc[x, period], errors="coerce"))), None)
            if label is None:
                continue
            v = float(pd.to_numeric(df.loc[label, period]))
            rows.append(dict(ticker=ticker, period_end=pd.Timestamp(period).date().isoformat(), item=item,
                             value=abs(v) if item == "dividends_paid_common" else v,
                             currency=ccy, label=label, source=SOURCE, retrieved=retrieved))
    # a company that pays nothing has no dividend row at all: that's 0, not missing
    if "dividends_paid_common" in missing and rows and "net_income_common" not in missing:
        missing.remove("dividends_paid_common")
        for p in sorted({r["period_end"] for r in rows if r["item"] == "net_income_common"}):
            rows.append(dict(ticker=ticker, period_end=p, item="dividends_paid_common", value=0.0, currency=ccy,
                             label="(no dividend row: none paid)", source=SOURCE, retrieved=retrieved))
    error = "no statements returned" if not rows else (f"missing: {', '.join(missing)}" if missing else "")
    return rows, dict(ticker=ticker, financial_currency=info.get("financialCurrency"), trading_currency=info.get("currency"),
                      retrieved=retrieved, error=error)


def main(argv=None, fetch=None) -> int:
    from dh import data

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tickers", nargs="*", help="default: every stock (asset_class equity) of the loaded universe")
    ap.add_argument("--out", default=None, help="default data/raw/fundamentals")
    a = ap.parse_args(argv)
    fetch = fetch or yahoo_fetch
    if a.tickers:
        tickers = a.tickers
    else:
        u = data.universe()
        tickers = sorted(u.loc[u.asset_class == "equity", "ticker"])
    out = Path(a.out) if a.out else data.load_config().data_dir / "fundamentals"
    today = date.today().isoformat()
    rows, infos = [], []
    for t in tickers:
        try:
            r, i = extract(t, fetch(t), today)
        except Exception as e:  # noqa: BLE001 — one failing ticker must not stop the others; the reason is kept
            r, i = [], dict(ticker=t, financial_currency=None, trading_currency=None, retrieved=today,
                            error=f"{type(e).__name__}: {e}"[:200])
        rows += r
        infos.append(i)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["ticker", "period_end", "item", "value", "currency", "label", "source", "retrieved"]
                 ).to_csv(out / "annual.csv", index=False)
    info = pd.DataFrame(infos)
    info.to_csv(out / "info.csv", index=False)
    pd.DataFrame([dict(file="annual.csv", source=SOURCE, retrieved=today,
                       processing="annual rows kept as published; dividends paid as a positive amount; "
                                  "net income to common shareholders preferred over net income",
                       limitations="snapshot, not point-in-time; Yahoo's labels and restatements; no FFO/AFFO for REITs",
                       terms="Yahoo Finance terms: personal use, no redistribution (decision #11)")]
                 ).to_csv(out / "sources_metadata.csv", index=False)
    bad = info[info.error.fillna("") != ""]
    print(f"{len(tickers) - len(bad)} of {len(tickers)} stocks with complete statements → {out}")
    for _, r in bad.iterrows():
        print(f"  {r.ticker}: {r.error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
