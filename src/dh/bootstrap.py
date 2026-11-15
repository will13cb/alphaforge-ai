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
# Research mode (harness.toml [data] extra, decision #41): each extra catalogue's folder is required when configured;
# the companies' statements (dividend coverage) are optional. Same keys under raw/ as the local folders.
EXTRA_FILES = ("assets_universe.csv", "prices_daily.csv", "corporate_actions.csv")
EXTRA_OPTIONAL = ("quality_report.csv", "sources_metadata.csv")
FUNDAMENTALS = ("fundamentals", ("annual.csv", "info.csv", "sources_metadata.csv"))


def required() -> list[str]:
    """Paths under data/raw/ the app needs: the starter's files, plus each configured extra catalogue's."""
    return list(FILES) + [f"products_{n}/{f}" for n in load_config().extra for f in EXTRA_FILES]


def optional() -> list[str]:
    sub, files = FUNDAMENTALS
    return (list(OPTIONAL) + [f"products_{n}/{f}" for n in load_config().extra for f in EXTRA_OPTIONAL]
            + ([f"{sub}/{f}" for f in files] if load_config().extra else []))
_LOCK = threading.Lock()  # one build even if several visitors open the app at once


def data_present() -> bool:
    folder = load_config().data_dir
    return all((folder / f).exists() for f in required())


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
            folder = load_config().data_dir
            if not all((folder / f).exists() for f in FILES):
                mod.main(["--start", STARTER_START, "--out", str(folder)])
            for n in load_config().extra:  # research mode: the extra catalogue, same organizers' download
                if not all((folder / f"products_{n}" / f).exists() for f in EXTRA_FILES):
                    spec = importlib.util.spec_from_file_location("build_products", ROOT / "scripts" / "build_products.py")
                    bp = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(bp)
                    bp.main(["--catalogue", n, "--start", STARTER_START])
            ensure_holdings()
        except (Exception, SystemExit) as e:  # noqa: BLE001 — the app shows the reason instead of crashing
            return False, f"{note}; could not build the data ({type(e).__name__}: {str(e)[:200]})"
    return data_present(), "" if data_present() else "the build finished but some files are missing"


def from_s3() -> str:
    """Download s3://$S3_BUCKET/raw/ into data/raw/ (starter files, plus extra catalogues and statements in research
    mode). Returns why it didn't, or ""; never raises."""
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        return "S3_BUCKET not set"
    try:
        import boto3
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        folder = load_config().data_dir
        folder.mkdir(parents=True, exist_ok=True)
        for f in required():
            (folder / f).parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, f"{PREFIX}/{f}", str(folder / f))
        for f in optional():
            try:
                (folder / f).parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(bucket, f"{PREFIX}/{f}", str(folder / f))
            except Exception:  # noqa: BLE001 — optional: absent is fine
                pass
        return ""
    except Exception as e:  # noqa: BLE001 — expired keys, closed account, missing file: fall back to the rebuild
        return f"S3 unavailable ({type(e).__name__})"


def ensure_holdings() -> str:
    """ETF look-through on a host without S3: fetch the issuers' direct files (SPY) and build etf_holdings.csv.
    Best effort, never raises: without it the look-through is "direct only" and the app says so."""
    from . import holdings
    out = holdings.default_path()
    if out.exists():
        return "present"
    try:
        raw = out.parent / "holdings"
        got = holdings.download(raw)
        if not any(raw.glob("*")):
            return "no issuer file"
        holdings.build(raw, out)
        holdings.holdings.cache_clear() if hasattr(holdings.holdings, "cache_clear") else None
        return "built from " + ", ".join(got)
    except Exception as e:  # noqa: BLE001
        return f"not built ({type(e).__name__})"
