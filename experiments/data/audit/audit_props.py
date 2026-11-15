"""Audit 4: the strategies the pipeline actually proposes."""
import warnings, pickle, time; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from dh import data, metrics
from dh import quant_toolkit as qt
from dh.agents.pipeline import run
from dh.agents.scenarios import AMIRA, MATEO, ROBERT
P = {"amira": AMIRA, "mateo": MATEO, "robert": {**ROBERT, "requested_positions": {"TSLA": 0.25}}}
out = {}
for k, prof in P.items():
    t = time.time(); res = run(prof); out[k] = res; print(f"{k}: pipeline {time.time() - t:.1f}s, {len(res['strategies'])} kept, {len(res['dropped'])} dropped, loss limit {res['limits']['loss_limit']:.0%}")
pickle.dump({k: {"strategies": v["strategies"], "limits": v["limits"], "cmp": v.get("request_comparison")} for k, v in out.items()},
            open("experiments/data/figures/props.pkl", "wb"))
r = data.returns()
rng = np.random.default_rng(0)
print("\n— Redundancy: correlation of daily returns between a persona's strategies")
for k, v in out.items():
    ports = {s["name"]: metrics.portfolio_returns(r[list(s["weights"])], s["weights"]) for s in v["strategies"]}
    df = pd.DataFrame(ports); c = df.corr().values; n = len(df.columns)
    pairs = [round(c[i, j], 3) for i in range(n) for j in range(i + 1, n)]
    print(f"  {k}: {list(df.columns)} pairwise corr {pairs}; growth shares {[s['split']['growth'] for s in v['strategies']]}")
print("\n— Drawdown: in-sample vs block-bootstrap (5-year paths, 2000 paths) and where it happened")
for k, v in out.items():
    L = v["limits"]["loss_limit"]
    for s in v["strategies"]:
        x = metrics.portfolio_returns(r[list(s["weights"])], s["weights"]).dropna()
        n = len(x); a = x.to_numpy()
        idx = qt._stationary_indices(n, n, 2000, n ** (1 / 3), rng)
        paths = np.cumprod(1 + a[idx], axis=1); mdd = (paths / np.maximum.accumulate(paths, axis=1) - 1).min(axis=1)
        eq = (1 + x).cumprod(); dd = eq / eq.cummax() - 1; trough = dd.idxmin(); peak = eq[:trough].idxmax()
        no22 = metrics.max_drawdown(x[x.index.year != 2022])
        top10 = np.log1p(x).nlargest(10).sum() / np.log1p(x).sum()
        print(f"  {k:6s} {s['name']:18s} hist MDD {metrics.max_drawdown(x):6.1%} ({peak.date()}→{trough.date()}) | boot median {np.median(mdd):6.1%}, 5% worst {np.percentile(mdd, 5):6.1%}, P(MDD>{L:.0%}) {np.mean(-mdd > L):.0%} | MDD w/o 2022 {no22:6.1%} | best 10 days = {top10:.0%} of log-growth")
print("\n— Is 'highest return' between Robert's strategies meaningful? (bootstrap CI of the difference, annualised)")
rs = out["robert"]["strategies"]
if len(rs) >= 2:
    a = metrics.portfolio_returns(r[list(rs[0]["weights"])], rs[0]["weights"]); b = metrics.portfolio_returns(r[list(rs[1]["weights"])], rs[1]["weights"])
    d = (a - b).dropna().to_numpy(); n = len(d); idx = qt._stationary_indices(n, n, 2000, n ** (1 / 3), rng)
    m = d[idx].mean(axis=1) * 261
    print(f"  {rs[0]['name']} − {rs[1]['name']}: {d.mean() * 261:+.2%}/yr, 95% CI [{np.percentile(m, 2.5):+.2%}, {np.percentile(m, 97.5):+.2%}]")
