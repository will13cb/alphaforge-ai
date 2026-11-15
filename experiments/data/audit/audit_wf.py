"""Audit 5: out-of-sample validity of the rules (split ceiling #17, company caps #24, horizon #22), rebalancing."""
import warnings, pickle; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from dh import data, metrics
from dh.agents.rules import DEFENSIVE, STOCKS, horizon_max_growth, company_cap
props = pickle.load(open("experiments/data/figures/props.pkl", "rb"))
r = data.returns(); mid = r.index[len(r) // 2]; H = {"h1": r[r.index < mid], "h2": r[r.index >= mid]}
p = data.prices().pivot(index="date", columns="ticker", values="adj_close").sort_index()
loc = p[p.index.dayofweek < 5].ffill().pct_change(fill_method=None).iloc[1:]
def mix(g, d, s): return {**{t: v * s for t, v in g.items()}, **{t: v * (1 - s) for t, v in d.items()}}
print("— Walk-forward of the #17 ceiling (largest growth share whose worst drop ≤ loss limit), Broad core baskets")
for k in ("amira", "mateo", "robert"):
    s0 = next(s for s in props[k]["strategies"] if s["name"] == "Broad core"); w = s0["weights"]
    g = {t: v for t, v in w.items() if t not in DEFENSIVE}; d = {t: v for t, v in w.items() if t in DEFENSIVE}
    g = {t: v / sum(g.values()) for t, v in g.items()}; d = {t: v / sum(d.values()) for t, v in d.items()}
    L = props[k]["limits"]["loss_limit"]; grid = [i / 20 for i in range(21)]
    def ceil(rr): return max([s for s in grid if abs(metrics.max_drawdown(metrics.portfolio_returns(rr, mix(g, d, s)))) <= L], default=0)
    def mdd(rr, s): return metrics.max_drawdown(metrics.portfolio_returns(rr, mix(g, d, s)))
    c1, c2, cf, cl = ceil(H["h1"]), ceil(H["h2"]), ceil(r), ceil(loc)
    print(f"  {k:6s} L={L:.0%}: ceiling on full CAD {cf:.0%} | on half1 {c1:.0%} → MDD on half2 {mdd(H['h2'], c1):.1%} | on half2 {c2:.0%} → MDD on half1 {mdd(H['h1'], c2):.1%} | local currency {cl:.0%}")
print("\n— #24 company caps: worst drop per stock, half1 vs half2 (cap = ¼ × 25% loss limit / |drop|, before the stock-room cap)")
rows = []
for t in sorted(STOCKS):
    d1, d2, df = metrics.max_drawdown(H["h1"][t]), metrics.max_drawdown(H["h2"][t]), metrics.max_drawdown(r[t])
    rows.append((t, d1, d2, df, 0.25 * 0.25 / abs(d1), 0.25 * 0.25 / abs(d2)))
df = pd.DataFrame(rows, columns=["t", "dd_h1", "dd_h2", "dd_full", "cap_h1", "cap_h2"]).set_index("t")
df["ratio"] = df[["cap_h1", "cap_h2"]].max(axis=1) / df[["cap_h1", "cap_h2"]].min(axis=1)
print(df.sort_values("ratio", ascending=False).head(8).round(3).to_string())
print(f"  median cap ratio between halves {df.ratio.median():.2f}, max {df.ratio.max():.2f}; rank corr of drops h1 vs h2 {df.dd_h1.rank().corr(df.dd_h2.rank()):.2f}")
print("\n— Horizon directive #22: growth cap at 4 y (Robert) and 10 y (Mateo) for other anchors")
import dh.agents.rules as R
for a in (1, 2, 3):
    for b in (10, 15, 20):
        R.H_NO_GROWTH, R.H_FULL_GROWTH = a, b
        print(f"  anchors ({a} y, {b} y): 4 y → {horizon_max_growth(4):.0%}, 10 y → {horizon_max_growth(10):.0%}, 15 y → {horizon_max_growth(15):.0%}")
print("\n— Daily vs monthly rebalancing (portfolio_returns rebalances daily, no costs)")
for k in ("amira",):
    s = next(s for s in props[k]["strategies"] if s["name"] == "Growth tilt"); w = s["weights"]
    x = r[list(w)].dropna(); daily = metrics.portfolio_returns(x, w)
    vals, cur = [], None
    wv = pd.Series(w); h = wv.copy(); V = 1.0; eq = []
    for i, (dt, row) in enumerate(x.iterrows()):
        if i % 21 == 0: h = wv * V
        h = h * (1 + row[wv.index]); V = h.sum(); eq.append(V)
    m = pd.Series(eq, index=x.index).pct_change().fillna(eq[0] - 1)
    print(f"  {k} Growth tilt: daily-rebalanced CAGR {metrics.ann_return(daily):.1%} MDD {metrics.max_drawdown(daily):.1%} | monthly CAGR {metrics.ann_return(m):.1%} MDD {metrics.max_drawdown(m):.1%}")
print("\n— Survivorship: equal-weight of the 20 stocks chosen in 2026 vs SPY/XIU (2021-2026, CAD)")
ew = r[sorted(STOCKS)].mean(axis=1)
print(f"  EW 20 stocks CAGR {metrics.ann_return(ew):.1%} vs SPY {metrics.ann_return(r['SPY']):.1%}, XIU {metrics.ann_return(r['XIU.TO']):.1%}")
