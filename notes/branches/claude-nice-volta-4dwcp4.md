# claude/nice-volta-4dwcp4 — Joud (with Claude)

**Goal:** a resolution architecture for the quantitative audit's anomalies (A1-A16), phase 1 = skeleton, phase 2 = fixes.
**Status:** phase 1 and phase 2 done (decisions R0-R10 approved by Joud, #46). Integrated into codex/release-integration on Nov 15, before the freeze, under the user's merge authorization.

## Done
- Phase 1 (2ac3c2f): `src/dh/risk/` (contracts, loss_model, goals, levels, kyc_validation, frontier, sync,
  controls), not wired yet; tests `tests/risk_markets.py` (known-parameter markets, 7 stress regimes) and
  `tests/test_risk_*.py`, with 5 xfail strict tests for the anomalies (all fixed and unmarked in phase 2).
- Design and decisions: `notes/risk-architecture.md` (root causes, target architecture, diagram, interfaces,
  methods, anomaly → module matrix, test plan, regression risks, decisions R0-R10).
- Phase 2 (c019584): dh.risk wired into portfolio, checks, guardian, critic, requests, market, kyc, charts,
  interface wording; results.csv re-logged on real data (01e9671). Details and before/after table in
  `notes/risk-architecture.md`.

## In progress / next
- Will's review; then update deliverables, demo caches (`make warm`) and the app copy outside the freeze.

## Decisions made here
- #46 (R0-R10).

## Contract changes
- strategy: `risk` (simulated loss rule on the final weights), `stamps` (dh.risk.sync);
  `split_range`: `exceedance`, `alpha`, `horizon_years`, `range`, `goal` (status, min_share, best probabilities);
  `split_curve` rows: `exceedance`, `sim_drop`; outlook: `central`, `prob_target_real`, `premium_used`, `inflation_used`.
- Guardian rules: G7 redefined (simulated), G17 removed (merged into G7), G18 added. D1 never fails.
- KYC bet options changed (common A grid): old answers like 0.08 are refused by `kyc.check`.

## How to check it
- `make data` then `make test` → 280 passed, 2 skipped (with data); `LLM_PROVIDER=mock python -m pytest -q tests`.
- `make log-personas` reproduces the results.csv rows of 01e9671.

## Open questions / blocked on
- Will's approval (agent files are his lane); deliverables cannot change after the Devpost freeze.
