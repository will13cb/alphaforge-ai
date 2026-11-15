"""Check each stand-in (dh.standins) against the real fund's prices, over the same window as our data.

    .venv/bin/python scripts/validate_standins.py          # needs data/raw (make data) + internet (Yahoo Finance)

For each fund: worst drop, 2022 return, volatility and total return, real vs stand-in, plus the tracking error and
the weekly correlation. Writes src/dh/standins_validation.json (derived statistics only, no prices: the app shows
them offline next to each stand-in) and logs the worst-drop gap of each fund to results.csv (dh.log_run).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from dh import data, metrics, standins  # noqa: E402

OUT = ROOT / "src" / "dh" / "standins_validation.json"


def stats(x: pd.Series) -> dict:
    x = x.dropna()
    y = x[x.index.year == 2022]
    return {"worst_drop": round(metrics.max_drawdown(x), 4), "return_2022": round(float((1 + y).prod() - 1), 4),
            "ann_vol": round(metrics.ann_vol(x), 4), "total_return": round(float((1 + x).prod() - 1), 4)}


def main() -> None:
    import yfinance as yf
    rets = data.returns()
    start, end = rets.index[0], rets.index[-1]
    out = {}
    for t, (src, hedged, name, how) in standins.STAND_INS.items():
        px = yf.download(t, start=str(start.date()), end=str((end + pd.Timedelta(days=1)).date()), auto_adjust=True,
                         progress=False)["Close"].squeeze()
        if px is None or len(px) < 250:
            print(f"{t}: not enough prices, skipped")
            continue
        px = px[px.index.dayofweek < 5]
        if not t.endswith(".TO"):   # U.S. listing: priced in USD, converted to CAD like our data (Bank of Canada FX)
            fx = data.fx()
            px = px * fx.reindex(px.index.union(fx.index)).sort_index().ffill().reindex(px.index)
        real = px.reindex(rets.index.union(px.index)).ffill().reindex(rets.index).pct_change(fill_method=None)
        si = standins.hedged_returns(rets[src])[0] if hedged else rets[src]
        idx = real.dropna().index.intersection(si.dropna().index)
        if len(idx) < 250:
            print(f"{t}: overlap too short, skipped")
            continue
        r, s = real.loc[idx], si.loc[idx]
        weekly = lambda x: (1 + x).resample("W-FRI").prod() - 1
        out[t] = {"measured_with": src, "hedged": hedged, "window": f"{idx[0].date()} to {idx[-1].date()}",
                  "real": stats(r), "stand_in": stats(s),
                  "tracking_error": round(float((s - r).std() * metrics.periods_per_year(r) ** 0.5), 4),
                  "weekly_corr": round(float(weekly(s).corr(weekly(r))), 4),
                  "source": f"Yahoo Finance {t} adjusted close"}
        gap = out[t]["stand_in"]["worst_drop"] - out[t]["real"]["worst_drop"]
        print(f"{t:8} real {out[t]['real']['worst_drop']:.1%} vs stand-in {out[t]['stand_in']['worst_drop']:.1%} "
              f"(gap {gap:+.1%}), weekly corr {out[t]['weekly_corr']:.3f}")
        metrics.log_run(round(gap, 4), experiment=f"standin-{t}", metric="worst_drop_gap",
                        notes=f"stand-in minus real worst drop, {src}{' hedged' if hedged else ''}, "
                              "scripts/validate_standins.py")
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"written {OUT.relative_to(ROOT)} ({len(out)} funds)")


if __name__ == "__main__":
    main()
