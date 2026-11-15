"""Rebuild the starter dataset with a LONGER history (decision #31), same assets, same files, same format.

    make data-long                      # default start 2004-11-18 (GLD's first day: every ETF but ZST/ESGV exists)
    make data-long START=2007-01-02     # or another start
    .venv/bin/python scripts/build_long_data.py --start 2004-11-18 --out data/raw

Runs the organizers' `Datathon2026Infos/alphaforge_starter/build_dataset.py` unchanged (official file, not edited):
loads it, overrides START and OUT_DIR, and fills USD/CAD before the Bank of Canada series begins with FRED's DEXCAUS
(Federal Reserve H.10, CAD per USD, noon buying rates in New York; same unit), marked in a `source` column. Writes the
6 CSVs + data_quality_warnings.txt into --out (data/raw/ by default: gitignored, never committed, decision #11).

Needs internet (Yahoo Finance via yfinance, Bank of Canada Valet, FRED) and `pip install yfinance pandas`.
Assets that didn't exist yet simply start later (ESGV 2018, ZST.TO 2011, SHOP.TO 2015, BTC-USD 2014, ETH-USD 2017...);
dh.data handles that (NaN before the first price, harness stand-ins for ZST.TO and ESGV only).
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / "Datathon2026Infos" / "alphaforge_starter" / "build_dataset.py"


def load_official():
    spec = importlib.util.spec_from_file_location("alphaforge_build_dataset", OFFICIAL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ssl_context():
    """Certificate check ON, with the certifi bundle (python.org's macOS Python doesn't read the system keychain:
    'CERTIFICATE_VERIFY_FAILED'). SSL_CERT_FILE, if set (e.g. a school or company proxy's certificate), wins."""
    import os
    import ssl
    if os.getenv("SSL_CERT_FILE"):
        return ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def verified_get(url: str) -> bytes:
    """Same as the official script's get(), with a verified SSL context (never unverified)."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as r:
            return r.read()
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            raise SystemExit(
                f"Certificate check failed for {url.split('/')[2]} ({e.reason}).\n"
                "- macOS with Python from python.org: run '/Applications/Python 3.12/Install Certificates.command', retry.\n"
                "- On a school/company network or VPN that inspects HTTPS: retry on another network (phone hotspot),\n"
                "  or set SSL_CERT_FILE to that network's root certificate. Verification is never turned off.") from e
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default="2004-11-18", help="first day, YYYY-MM-DD (default: GLD's first trading day)")
    ap.add_argument("--end", default=None, help="last day, YYYY-MM-DD (default: the official script's END)")
    ap.add_argument("--out", default=str(ROOT / "data" / "raw"))
    a = ap.parse_args(argv)

    mod = load_official()
    mod.START = a.start
    if a.end:
        mod.END = a.end
    mod.OUT_DIR = Path(a.out)
    mod.get = verified_get
    official_boc = mod.boc

    def boc_with_fred_before(series_id: str) -> pd.DataFrame:
        """Bank of Canada as in the official script; for USD/CAD, FRED DEXCAUS fills the days before BoC starts."""
        d = official_boc(series_id)
        if series_id != "FXUSDCAD":
            return d
        first = d["date"].min() if len(d) else mod.END
        if str(first) <= mod.START:
            return d
        f = pd.read_csv(io.BytesIO(mod.get(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXCAUS&cosd={mod.START}&coed={first}")))
        f.columns = ["date", "value"]
        f["value"] = pd.to_numeric(f["value"], errors="coerce")
        f = f.dropna()
        f = f[f["date"] < str(first)]
        print(f"USD/CAD: Bank of Canada from {first}; FRED DEXCAUS fills {len(f)} days from {f['date'].min()}")
        return pd.concat([f, d], ignore_index=True)

    mod.boc = boc_with_fred_before
    print(f"building {mod.START} → {mod.END} into {mod.OUT_DIR} with the official script ({OFFICIAL.name})")
    rc = mod.main()
    (mod.OUT_DIR / "BUILD_INFO.txt").write_text(
        f"Built by scripts/build_long_data.py on {mod.RETRIEVED}: window {mod.START} to {mod.END}.\n"
        "Prices: Yahoo Finance (yfinance), adj_close. USD/CAD: Bank of Canada FXUSDCAD, FRED DEXCAUS before it.\n"
        "Macro: Bank of Canada Valet, FRED. Terms: Yahoo (no redistribution), bankofcanada.ca/terms, fred.stlouisfed.org/legal.\n")
    return rc or 0


if __name__ == "__main__":
    sys.exit(main())
