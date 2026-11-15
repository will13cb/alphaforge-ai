"""First start of a hosted copy (Streamlit Community Cloud): get the data CSVs if they are missing.

Order: 1. the team's S3 bucket (`make data-up` put them there; needs S3_BUCKET + AWS credentials in the host's
secrets), 2. rebuild with the organizers' script (works after the AWS account closes). Add other sources here.

The data never goes in git (Yahoo's terms, decision #11), so a hosted app rebuilds it with the organizers' own script
(`Datathon2026Infos/alphaforge_starter/build_dataset.py`, via `scripts/build_long_data.py`, same window 2021-11-12 to
2026-11-12). Only when AF_AUTO_DATA=1 (set it in the host's secrets): a laptop never downloads by surprise.

    from dh.bootstrap import ensure_data
    ok, note = ensure_data()      # (True, "") when data/raw is ready
"""

from __future__ import annotations

import importlib.util
import os
import threading

from .data import ROOT, load_config

STARTER_START = "2021-11-12"
PREFIX = "raw"  # s3://$S3_BUCKET/raw/ (same place as scripts/get-data.sh and `make data-up`)
FILES = ("assets_universe.csv", "prices_daily.csv", "fx_usdcad_daily.csv", "macro_rates.csv", "corporate_actions.csv")
# Fetched too when they are in S3 (not required): SPY holdings for the ETF look-through, so the hosted app
# computes the same strategies as the laptop that filled the caches, and the sources table.
OPTIONAL = ("etf_holdings.csv", "sources_metadata.csv")
_LOCK = threading.Lock()  # one build even if several visitors open the app at once


def data_present() -> bool:
    folder = load_config().data_dir
    return all((folder / f).exists() for f in FILES)


def ensure_data() -> tuple[bool, str]:
    """(ready, note). Builds data/raw/ once when AF_AUTO_DATA=1 and files are missing; never raises."""
    if data_present():
        return True, ""
    if os.getenv("AF_AUTO_DATA") != "1":
        return False, "data/raw/ is missing (run `make data`; on a host, set AF_AUTO_DATA=1 to build it at start)"
    with _LOCK:
        if data_present():
            return True, ""
        note = from_s3()
        if data_present():
            return True, ""
        try:
            spec = importlib.util.spec_from_file_location("build_long_data", ROOT / "scripts" / "build_long_data.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.main(["--start", STARTER_START, "--out", str(load_config().data_dir)])
        except (Exception, SystemExit) as e:  # noqa: BLE001 — the app shows the reason instead of crashing
            return False, f"{note}; could not build the data ({type(e).__name__}: {str(e)[:200]})"
    return data_present(), "" if data_present() else "the build finished but some files are missing"


def from_s3() -> str:
    """Download s3://$S3_BUCKET/raw/*.csv into data/raw/. Returns why it didn't, or ""; never raises."""
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        return "S3_BUCKET not set"
    try:
        import boto3
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        folder = load_config().data_dir
        folder.mkdir(parents=True, exist_ok=True)
        for f in FILES:
            s3.download_file(bucket, f"{PREFIX}/{f}", str(folder / f))
        for f in OPTIONAL:
            try:
                s3.download_file(bucket, f"{PREFIX}/{f}", str(folder / f))
            except Exception:  # noqa: BLE001 — optional: absent is fine
                pass
        return ""
    except Exception as e:  # noqa: BLE001 — expired keys, closed account, missing file: fall back to the rebuild
        return f"S3 unavailable ({type(e).__name__})"
