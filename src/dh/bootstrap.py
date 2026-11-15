"""First start of a hosted copy (Streamlit Community Cloud): get the data CSVs if they are missing.

Order: 1. the team's S3 bucket (`make data-up` put them there; needs S3_BUCKET + AWS credentials in the host's
secrets), 2. rebuild with the organizers' script (works after the AWS account closes). Add other sources here.

The data never goes in git (Yahoo's terms, decision #11), so a hosted app rebuilds it with the organizers' own script
(`Datathon2026Infos/alphaforge_starter/build_dataset.py`, via `scripts/build_long_data.py`), from harness.toml [data]
start to the official END, or from 2021-11-12 if start is "" (the submission default, decision #48). Only when AF_AUTO_DATA=1 (set it in the host's secrets): a laptop never downloads by surprise.

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
    return (list(OPTIONAL) + [f"fixed_income/{f}" for f in ("instruments.csv", "reference_snapshot.json", "sources_metadata.csv", "quality_report.csv")] + [f"products_{n}/{f}" for n in load_config().extra for f in EXTRA_OPTIONAL]
            + ([f"{sub}/{f}" for f in files] if load_config().extra else []))
_LOCK = threading.Lock()  # one build even if several visitors open the app at once


def build_start() -> str:
    """First day a host rebuild downloads: harness.toml [data] start (decision #47), else the starter's own."""
    return load_config().start or STARTER_START


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
            start = build_start()
            if not all((folder / f).exists() for f in FILES):
                mod.main(["--start", start, "--out", str(folder)])
            for n in load_config().extra:  # research mode: the extra catalogue, same organizers' download
                if not all((folder / f"products_{n}" / f).exists() for f in EXTRA_FILES):
                    spec = importlib.util.spec_from_file_location("build_products", ROOT / "scripts" / "build_products.py")
                    bp = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(bp)
                    bp.main(["--catalogue", n, "--start", start])
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


def ensure_fixed_income() -> str:
    """Load the separate S3 catalogue even when market data is already present.

    Explicit hosted opt-in only. Missing S3 files leave the public-source lookup
    available; no market-history rebuild is required for this mode.
    """
    folder = load_config().data_dir / "fixed_income"
    if (folder / "instruments.csv").exists():
        return "present"
    bucket = os.getenv("S3_BUCKET")
    if os.getenv("AF_AUTO_DATA") != "1" or not bucket:
        return "S3 catalogue not configured"
    with _LOCK:
        if (folder / "instruments.csv").exists():
            return "present"
        try:
            import boto3
            from botocore.config import Config
            client = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"),
                                  config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 0}))
            folder.mkdir(parents=True, exist_ok=True)
            # Publish instruments last: readers must not see a catalogue without
            # its dated context/FX snapshot while downloading.
            for name in ("reference_snapshot.json", "sources_metadata.csv", "quality_report.csv", "instruments.csv"):
                temporary = folder / (name + ".download")
                try:
                    client.download_file(bucket, f"{PREFIX}/fixed_income/{name}", str(temporary))
                    temporary.replace(folder / name)
                except Exception:
                    temporary.unlink(missing_ok=True)
            return "loaded" if (folder / "instruments.csv").exists() else "S3 catalogue unavailable"
        except Exception as error:
            return f"S3 catalogue unavailable ({type(error).__name__})"
