"""Download a product catalogue's prices into data/raw/products_<name>/ (gitignored), in the starter's format.

    python scripts/build_products.py                       # catalogue "cadusa", starter window 2021-11-12..2026-11-12
    python scripts/build_products.py --start 2016-11-14    # 10 years (CAD conversion needs `make data-long` first)
    python scripts/build_products.py --tickers XEF.TO SLV  # a subset

Same download code as the organizers (their build_prices: yfinance, auto_adjust=False, adj_close, dividends and
splits), so a product added here is measured exactly like the starter's 31. Then:
- the catalogue is checked (dh.products.validate_catalogue): any 'fail' stops before downloading;
- every series is checked (dh.products.quality_report); a product whose series fails is left out of the loadable
  files and listed, never dropped silently;
- the files: assets_universe.csv, prices_daily.csv, corporate_actions.csv (starter columns), quality_report.csv,
  sources_metadata.csv (source, date, processing, limits, terms: the brief asks it for any added data).
To use them: harness.toml [data] extra = ["cadusa"].
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OFFICIAL = ROOT / "Datathon2026Infos" / "alphaforge_starter" / "build_dataset.py"


def load_official():
    spec = importlib.util.spec_from_file_location("alphaforge_build_dataset", OFFICIAL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fx_coverage(fx_path: Path, start: str, end: str) -> str | None:
    """None if USD/CAD covers the window, else what's missing (USD prices before the first rate stay NaN in CAD)."""
    if not fx_path.exists():
        return f"{fx_path} missing: run `make data` (USD products can't be converted to CAD without it)"
    d = pd.read_csv(fx_path, parse_dates=["date"])["date"]
    if d.min() > pd.Timestamp(start) + pd.Timedelta(days=7):
        return f"USD/CAD starts {d.min().date()}, after {start}: run `make data-long` for a longer window"
    return None


def sources_metadata(name: str, start: str, end: str) -> pd.DataFrame:
    today = date.today().isoformat()
    common = dict(retrieved=today, terms="Yahoo Finance terms: personal use, no redistribution (decision #11)")
    return pd.DataFrame([
        dict(file="prices_daily.csv", source="Yahoo Finance via yfinance", **common,
             processing=f"organizers' build_prices, {start}..{end}; adj_close adjusted for splits and dividends",
             limitations="unofficial API; adjusted history can be revised; issuer data not cross-checked"),
        dict(file="corporate_actions.csv", source="Yahoo Finance via yfinance", **common,
             processing="dividends and splits from the same download", limitations="as reported by Yahoo"),
        dict(file="assets_universe.csv", source=f"dh.product_catalogue ({name})", retrieved=today,
             terms="team's own classification", processing="market and currency checked on Yahoo (fast_info)",
             limitations="sector/exposure labels by the team; ETF holdings not loaded (look-through = lower bound)"),
        dict(file="quality_report.csv", source="dh.products.quality_report", retrieved=today, terms="ours",
             processing="history, coverage, big moves, stale quotes, gaps, toolkit data_quality",
             limitations="flags, never corrections"),
    ])


def main(argv=None, download=None) -> int:
    from dh import products
    from dh.data import load_config

    off = None
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--catalogue", default="cadusa")
    ap.add_argument("--start", default=None, help="first day (default: the starter's)")
    ap.add_argument("--end", default=None, help="last day (default: the starter's)")
    ap.add_argument("--tickers", nargs="*", help="only these catalogue tickers")
    ap.add_argument("--out", default=None, help="default data/raw/products_<catalogue>")
    a = ap.parse_args(argv)

    if download is None:
        off = load_official()
    start = a.start or (off.START if off else "2021-11-12")
    end = a.end or (off.END if off else "2026-11-12")
    cfg = load_config()
    out = Path(a.out) if a.out else cfg.data_dir / f"products_{a.catalogue}"

    cat = products.catalogue(a.catalogue)
    if a.tickers:
        unknown = sorted(set(a.tickers) - set(cat.ticker))
        if unknown:
            print(f"not in catalogue {a.catalogue!r}: {', '.join(unknown)}")
            return 1
        cat = cat[cat.ticker.isin(a.tickers)].reset_index(drop=True)
    issues = products.validate_catalogue(cat)
    for i in issues:
        print(f"[{i['status']}] {i['ticker']}: {i['check']}: {i['reason']}")
    if any(i["status"] == "fail" for i in issues):
        print("catalogue has errors: nothing downloaded")
        return 1

    if download is None:
        off.START, off.END = start, end
        download = off.build_prices
    prices, actions = download(cat[["ticker", "name", "asset_class", "market", "currency", "sector"]])

    report = products.quality_report(prices, cat, start, end)
    bad = report.loc[report.status == "fail", "ticker"].tolist()
    keep = cat[~cat.ticker.isin(bad)]
    out.mkdir(parents=True, exist_ok=True)
    keep.to_csv(out / "assets_universe.csv", index=False)
    prices[prices.ticker.isin(keep.ticker)].sort_values(["ticker", "date"]).to_csv(out / "prices_daily.csv", index=False)
    actions[actions.ticker.isin(keep.ticker)].to_csv(out / "corporate_actions.csv", index=False)
    report.to_csv(out / "quality_report.csv", index=False)
    sources_metadata(a.catalogue, start, end).to_csv(out / "sources_metadata.csv", index=False)

    counts = report.status.value_counts().to_dict()
    print(f"\n{len(keep)} of {len(cat)} products written to {out} ({start}..{end}); quality: {counts}")
    for _, r in report[report.status != "ok"].iterrows():
        print(f"  [{r.status}] {r.ticker}: {r.reasons}")
    if bad:
        print(f"left out (series unusable): {', '.join(bad)}")
    warn = fx_coverage(cfg.data_dir / "fx_usdcad_daily.csv", start, end)
    if warn:
        print(f"WARNING: {warn}")
    print(f'\nTo load them: harness.toml [data] extra = ["{a.catalogue}"], then `python -m dh check`.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
