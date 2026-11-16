# claude/ecstatic-cori-fb3117 — one-page quantified evaluation

## Done
- `scripts/evaluate.py`: 16 scenarios (expected vs obtained), Explainer fidelity (G12 on 10 pipeline runs + cached
  Opus 5.5 drafts + 200 injected invented numbers), 10 trap checks (out-of-profile, invented extractor numbers,
  instruction injection), risk-model calibration (realised breach for nominal alpha 10%, planned correction).
- `deliverables/EVALUATION.md` (French, one page), linked from README; metrics in `results.csv` (experiment `evaluation`).

## Next
- Planned correction (not shipped): ceiling = low end of the 3-year sub-window range → 10.6% realised breach vs 19%.
- Re-run with Bedrock reachable to measure live Explainer drafts, not only the cache.

## How to check
`.venv/bin/python scripts/evaluate.py` (offline, ~4 min).
