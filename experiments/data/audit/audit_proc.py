"""Audit 2: what dh.data does to the data (calendar, FX, holidays, asynchronous trading)."""
import pandas as pd, numpy as np
from dh import data, metrics
ca = pd.read_csv("data/raw/corporate_actions.csv")
print("actions:", ca.action.value_counts().to_dict()); print(ca[ca.action != "dividend"].to_string(index=False))
p = data.prices(); cnq = p[(p.ticker == "CNQ.TO") & (p.date.between("2022-08-17", "2022-08-25"))][["date", "close", "adj_close"]]
cnq["r_adj"] = cnq.adj_close.pct_change(); cnq["r_close"] = cnq.close.pct_change(); print(cnq.round(4).to_string(index=False))
r = data.returns()
zero = (r == 0).mean().sort_values()
print("share of exact 0% days after alignment (ffill):", {k: round(v, 3) for k, v in zero.items() if k in ("SPY", "XIU.TO", "BTC-USD", "ZST.TO", "RY.TO", "AAPL")})
# FX conversion check: SPY CAD return = (1+r_usd)(1+r_fx)-1
raw = p.pivot(index="date", columns="ticker", values="adj_close")
fx = data.fx()
both = pd.concat([raw["SPY"], fx.rename("fx")], axis=1).dropna()
r_usd, r_fx = both["SPY"].pct_change(), both["fx"].pct_change()
implied = ((1 + r_usd) * (1 + r_fx) - 1).dropna()
diff = (r["SPY"].reindex(implied.index) - implied).abs()
print("SPY CAD return vs (1+r_usd)(1+r_fx)-1, max abs diff on common days:", float(diff.max()))
print("fx series name / direction: mean", round(float(fx.mean()), 4), "(CAD per USD if ~1.3)")
# asynchronous trading: daily vs weekly correlations
for a, b in (("XIU.TO", "SPY"), ("BTC-USD", "SPY"), ("XBB.TO", "AGG"), ("SPY", "XBB.TO")):
    d = r[[a, b]].dropna().corr().iloc[0, 1]
    w = (1 + r[[a, b]]).resample("W-FRI").prod().sub(1).corr().iloc[0, 1]
    print(f"corr {a}/{b}: daily {d:.2f}, weekly {w:.2f}")
# crypto UTC day vs US close: lead-lag
lag = r["BTC-USD"].corr(r["SPY"].shift(1)); lead = r["BTC-USD"].corr(r["SPY"].shift(-1))
print(f"BTC vs SPY next day {lead:.2f}, vs SPY previous day {lag:.2f}")
# annualisation rows per year
print("rows/year (observed):", round(metrics.periods_per_year(r["SPY"]), 1), "| first/last", r.index[0].date(), r.index[-1].date())
# vol with and without zero days (holiday ffill)
for t in ("XIU.TO", "SPY"):
    x = r[t]; print(t, "vol all rows", round(metrics.ann_vol(x), 4), "| vol trading days only (×√252)", round(float(x[x != 0].std() * np.sqrt(252)), 4))
