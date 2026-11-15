# Audit scripts (Nov 15) — evidence for `notes/audit-2026-11-15.md`

Read-only analyses; they change nothing in the project. Run from the repo root with the starter CSVs in `data/raw/`
(`audit_stats.py` needs `pip install statsmodels`, analysis only, not a project dependency).

| Script | Section of the audit |
|---|---|
| `audit_raw.py` | 3.1 raw files: duplicates, NaN, OHLC, extreme moves, splits, FX, macro |
| `audit_proc.py` | 3.2 what `dh.data` does: CNQ pseudo-split, holiday zeros, FX conversion, asynchronous correlations |
| `audit_stats.py` | 4.3 distributions (JB), autocorrelation (Ljung-Box), ARCH, ADF, regimes by half |
| `audit_props.py` | 4.1/4.4 proposed strategies: redundancy, bootstrap drawdowns, 2022 concentration, return differences (writes `experiments/data/figures/props.pkl`) |
| `audit_wf.py` | 4.2/5 out of sample: #17 ceiling walk-forward, #24 cap stability, #22 anchor sensitivity, rebalancing, survivorship (run `audit_props.py` first) |
