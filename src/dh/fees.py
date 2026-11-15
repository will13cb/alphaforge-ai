"""ETF fees for the existing-portfolio review: what holding these funds costs a year, in $ (workshop slide 13).

`fees.json` is written by scripts/build_fees.py (Yahoo Finance net expense ratio, date in the file). A ticker without
a figure is listed as unknown, never assumed to be free. Single stocks have no fund fee (0 by definition).
Fees are NOT taken out of the historical returns (adjusted prices already net of the fund's own fees for an ETF).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).with_name("fees.json")


@lru_cache(maxsize=1)
def table() -> dict:
    try:
        return json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}


def mer(ticker: str) -> float | None:
    v = table().get(ticker)
    return v if isinstance(v, (int, float)) else None


def yearly(positions_cad: dict[str, float], funds: set[str]) -> dict:
    """{by_ticker: {t: {mer, cost_cad}}, total_cad, weighted_mer, unknown: [...], source}. `funds`: which tickers
    are funds (ETFs and stand-in funds); the others (single stocks) have no fund fee."""
    by, unknown, total = {}, [], 0.0
    for t, v in positions_cad.items():
        if t not in funds:
            continue
        m = mer(t)
        if m is None:
            unknown.append(t)
            continue
        by[t] = {"mer": m, "cost_cad": round(v * m, 2)}
        total += v * m
    known = sum(positions_cad[t] for t in by)
    return {"by_ticker": by, "total_cad": round(total, 2),
            "weighted_mer": round(total / sum(positions_cad.values()), 6) if positions_cad else 0.0,
            "funds_mer": round(total / known, 6) if known else None, "unknown": sorted(unknown),
            "source": f"{table().get('_source', 'no fee file')}, {table().get('_fetched', '')}".strip(", ")}
