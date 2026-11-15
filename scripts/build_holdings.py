"""Raw issuer holdings files (data/raw/holdings/) → data/raw/etf_holdings.csv, with sanity checks.

    .venv/bin/python scripts/build_holdings.py

Logic lives in src/dh/holdings.py (tested offline). Sources and limits: data/README.md.
"""

from dh.agents.rules import STOCKS
from dh.holdings import OTHER, build, default_path

out = default_path()
df = build(out.parent / "holdings", out)
print(f"\nwrote {out} ({len(df)} rows)\n")
for etf, g in df.groupby("etf", sort=False):
    tot = g.weight.sum()
    ok = "ok" if abs(tot - 1) <= 0.02 else "CHECK: outside ±2%"
    cash = g.loc[g.holding == OTHER, "weight"].sum()
    print(f"{etf}: {(g.holding != OTHER).sum()} holdings, weights sum {tot:.2%} ({ok}), "
          f"cash/futures/FX {cash:.2%}, as of {g.as_of.iloc[0] or 'UNKNOWN'}")
    ours = g[g.holding.isin(STOCKS)]
    print("   our universe stocks: " + (", ".join(f"{h} {w:.2%}" for h, w in zip(ours.holding, ours.weight)) or "none"))
