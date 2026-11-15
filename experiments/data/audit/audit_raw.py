"""Audit 1: raw starter data (prices, FX, corporate actions, macro, universe)."""
import pandas as pd, numpy as np
R = "data/raw/"
p = pd.read_csv(R + "prices_daily.csv", parse_dates=["date"])
u = pd.read_csv(R + "assets_universe.csv")
print("prices", p.shape, "tickers", p.ticker.nunique(), "dates", p.date.min().date(), p.date.max().date())
print("dup (ticker,date):", p.duplicated(["ticker", "date"]).sum(), "| NaN per col:", p.isna().sum()[p.isna().sum() > 0].to_dict())
for c in ("open", "high", "low", "close", "adj_close"):
    bad = (p[c] <= 0).sum()
    if bad: print("non-positive", c, bad)
print("high<low:", (p.high < p.low).sum(), "| close outside [low,high]:", ((p.close > p.high * 1.0001) | (p.close < p.low * 0.9999)).sum())
print("zero volume rows:", (p.volume == 0).sum(), p.loc[p.volume == 0, ["ticker", "date"]].head(5).values.tolist())
rows = p.groupby("ticker").date.agg(["count", "min", "max"])
print("rows per ticker: min", rows["count"].min(), rows["count"].idxmin(), "max", rows["count"].max(), rows["count"].idxmax())
p = p.sort_values(["ticker", "date"])
p["r"] = p.groupby("ticker").adj_close.pct_change()
big = p[p.r.abs() > 0.15][["ticker", "date", "r"]]
print("daily |adj return| > 15%:", len(big)); print(big.sort_values("r").to_string(index=False)[:1500])
# stale prices (5+ identical adj_close in a row) outside crypto
p["same"] = p.groupby("ticker").adj_close.diff().eq(0)
streak = p.groupby("ticker").same.apply(lambda s: s.groupby((~s).cumsum()).sum().max())
print("longest run of unchanged adj_close:", streak[streak >= 3].to_dict())
# adj vs close: dividend adjustment factor monotone? split check on close
p["rc"] = p.groupby("ticker").close.pct_change()
jumps = p[(p.rc.abs() > 0.3)][["ticker", "date", "rc", "r"]]
print("close-to-close jumps > 30% (split days?):", jumps.to_string(index=False) if len(jumps) else "none")
ca = pd.read_csv(R + "corporate_actions.csv")
print("corporate actions:", ca.shape, ca.columns.tolist()); print(ca[ca.iloc[:, 2].astype(str).str.contains("plit", na=False) | (ca.columns.str.contains("split").any())].head(0))
splits = ca[[c for c in ca.columns if c.lower() in ("type", "action", "event")][0]] if any(c.lower() in ("type", "action", "event") for c in ca.columns) else None
print(ca.head(3).to_string())
fx = pd.read_csv(R + "fx_usdcad_daily.csv", parse_dates=["date"])
print("fx", fx.shape, fx.date.min().date(), fx.date.max().date(), "NaN", fx.isna().sum().to_dict(), "dup", fx.date.duplicated().sum())
fx["d"] = fx.usdcad.pct_change()
print("fx usdcad range", fx.usdcad.min(), fx.usdcad.max(), "| max daily move", round(fx.d.abs().max(), 4), "| usdcad*cadusd-1 max", round((fx.usdcad * fx.cadusd - 1).abs().max(), 4))
eq_days = set(p[p.ticker == "SPY"].date); tsx = set(p[p.ticker == "XIU.TO"].date); fxd = set(fx.date)
print("US days not TSX:", len(eq_days - tsx), "| TSX days not US:", len(tsx - eq_days), "| US days without FX row:", len(eq_days - fxd))
m = pd.read_csv(R + "macro_rates.csv", parse_dates=["date"])
print("macro series:", m.groupby("series_id").agg(n=("value", "size"), first=("date", "min"), last=("date", "max"), freq=("frequency", "first")).to_string())
print("universe classes:", u.asset_class.value_counts().to_dict(), "| markets:", u.market.value_counts().to_dict())
