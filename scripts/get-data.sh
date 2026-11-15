#!/usr/bin/env bash
# Put the AlphaForge starter CSVs in data/raw/ (gitignored).
#   1. if the CSVs sit in Datathon2026Infos/alphaforge_starter/, copy them
#   2. else if S3_BUCKET is set, sync from s3://$S3_BUCKET/raw
#   3. else rebuild them with the official build_dataset.py (needs yfinance + internet)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
src=Datathon2026Infos/alphaforge_starter
mkdir -p data/raw
if [ -f "$src/prices_daily.csv" ]; then
  cp "$src"/*.csv data/raw/
elif [ -n "${S3_BUCKET:-}" ] && aws s3 ls "s3://$S3_BUCKET/raw/" >/dev/null 2>&1; then
  aws s3 sync "s3://$S3_BUCKET/raw/" data/raw/
else
  cp "$src/build_dataset.py" data/raw/   # its OUT_DIR is its own folder
  .venv/bin/python data/raw/build_dataset.py
fi
ls -lh data/raw/
echo "Next: make check"
