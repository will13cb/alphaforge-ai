"""Put the data CSVs in the team's S3 bucket, so a hosted copy of the app can fetch them (`dh.bootstrap`).

    make data-up          # data/raw/*.csv → s3://$S3_BUCKET/raw/   (credentials and bucket from .env)

Private bucket, team use only: the CSVs are never made public (Yahoo's terms, decision #11). Prints what it uploaded.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dh.bootstrap import FILES, PREFIX  # noqa: E402
from dh.data import load_config  # noqa: E402


def main() -> int:
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        print("S3_BUCKET is not set in .env")
        return 1
    folder = load_config().data_dir
    missing = [f for f in FILES if not (folder / f).exists()]
    if missing:
        print(f"missing in {folder}: {', '.join(missing)} (run `make data` first)")
        return 1
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
    for f in sorted(p.name for p in folder.glob("*.csv")) + [f for f in ("BUILD_INFO.txt",) if (folder / f).exists()]:
        s3.upload_file(str(folder / f), bucket, f"{PREFIX}/{f}")
        print(f"uploaded {f}  →  s3://{bucket}/{PREFIX}/{f}  ({(folder / f).stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
