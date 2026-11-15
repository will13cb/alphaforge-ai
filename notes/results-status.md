# What in results.csv is still valid (audit P16, Sun Nov 15)

`results.csv` is append-only (merge=union), so old rows stay. Quote only rows computed by the **final commit** with
the **final data** (rule 3). Status of each experiment:

| Experiment | Status | Why |
|---|---|---|
| `guardian-scenarios` | valid while `make scenarios` is 16/16 | rules test, not data |
| `threshold-check` | **obsolete** | computed with the level table that #17/#19/#24 replaced |
| `cppi-thresholds` | **obsolete** | CPPI removed (#21) |
| `persona-*` from `portfolio/requests` (`persona_numbers.py`) | **obsolete** | duplicate of `make log-personas`; computed before #31–#34 |
| `persona-*` from `make log-personas` | **re-run** | the strategies changed (#32 risk levels, #33) and will change again with the long data (#31) |

**Before quoting any number:** rebuild the data you'll present (`make data` or `make data-long`), then
`make log-personas` once on the final commit, then re-save the Explainer cache (`make explain P=robert SAVE=1`).
