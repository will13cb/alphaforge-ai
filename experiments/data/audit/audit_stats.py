"""Audit 3: return distributions, dependence, heteroscedasticity, stationarity, regimes."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
from statsmodels.tsa.stattools import adfuller
from dh import data, metrics
r = data.returns(); P = data.price_panel()
A = ["SPY", "XIU.TO", "XBB.TO", "ZST.TO", "GLD", "TSLA", "BTC-USD"]
port = metrics.portfolio_returns(r, {"XIU.TO": .3, "SPY": .3, "XBB.TO": .3, "ZST.TO": .1})
rows = []
for name, x in [*[(a, r[a]) for a in A], ("60/40 mix", port)]:
    x = x.dropna(); x = x[x != 0] if name != "60/40 mix" else x
    jb = stats.jarque_bera(x); lb = acorr_ljungbox(x, lags=[10]); lb2 = acorr_ljungbox(x ** 2, lags=[10]); arch = het_arch(x, nlags=5)
    t = x.mean() / x.std(ddof=1) * np.sqrt(len(x))
    rows.append(dict(asset=name, skew=round(stats.skew(x), 2), ex_kurt=round(stats.kurtosis(x), 1), JB_p=f"{jb.pvalue:.0e}",
                     LB_r_p=round(float(lb.lb_pvalue.iloc[0]), 3), LB_r2_p=f"{float(lb2.lb_pvalue.iloc[0]):.0e}", ARCH_p=f"{arch[1]:.0e}",
                     t_mean=round(t, 2)))
print(pd.DataFrame(rows).to_string(index=False))
print("\nADF p-values (H0: unit root): log price vs return")
for a in ("SPY", "XIU.TO", "TSLA"):
    print(f"  {a}: log price {adfuller(np.log(P[a].dropna()))[1]:.2f} | returns {adfuller(r[a].dropna())[1]:.0e}")
mid = r.index[len(r) // 2]
h1, h2 = r[r.index < mid], r[r.index >= mid]
print(f"\nRegimes: half1 {h1.index[0].date()}→{h1.index[-1].date()}, half2 {h2.index[0].date()}→{h2.index[-1].date()}")
for a in ("SPY", "XIU.TO", "XBB.TO", "ZST.TO", "GLD", "BTC-USD"):
    print(f"  {a:8s} ann.return h1 {metrics.ann_return(h1[a]):6.1%} h2 {metrics.ann_return(h2[a]):6.1%} | vol h1 {metrics.ann_vol(h1[a]):5.1%} h2 {metrics.ann_vol(h2[a]):5.1%} | MDD h1 {metrics.max_drawdown(h1[a]):6.1%} h2 {metrics.max_drawdown(h2[a]):6.1%}")
print("  stock-bond corr (SPY/XBB.TO) by year:", {y: round(g["SPY"].corr(g["XBB.TO"]), 2) for y, g in r.groupby(r.index.year)})
lev = stats.levene(h1["SPY"], h2["SPY"]); print(f"  Levene (equal variance SPY h1 vs h2) p = {lev.pvalue:.3f}")
