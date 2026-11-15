# claude/jolly-gauss-vrakn3 — Will

**Goal:** (1) no crypto by default (#26); (2) the Critic: investigates with tools, objects with evidence, one
recomputed fix per strategy (#30).
**Status:** ready to merge (crypto part merged to main in `37380d4`; Critic not yet run on Bedrock)

## Done (round 3, Sun evening: #40, from Markowitz keep what describes risk)
- `src/dh/metrics.py`: `risk_contributions` (covariance only) — shared file, Joud to review.
- `src/dh/agents/critic.py`: 11th tool `risk_contributions`; trace line "X% of the money, Y% of the risk". Prompt unchanged.
- `src/dh/kyc.py`: Joud's, copied unchanged from `optimisation-markowitz` (identical file: no conflict if it merges).
- `src/dh/agents/profiler.py`: `kyc_check` (A vs tolerance, flag only) + `expected_value_check` (wrong → knowledge ≤ 3);
  `limits["kyc"]`; `trace.describe_limits` shows it. Personas get fictional bets + EV answers that agree (no limit change).
- Tests: `tests/test_kyc_check.py` (4), +1 in `tests/test_critic.py`. 209 pass, 16/16 scenarios.

## Done (earlier rounds)
- `src/dh/agents/portfolio.py`: `asked_crypto()`, `crypto_decision()` (#26); `assemble()` = the whole per-strategy
  calculation, now shared by `propose` and `revise`; strategies keep their `baskets`; `tighten()` + `revise()`
  turn a Critic fix into a stricter input and rerun everything.
- `src/dh/agents/critic.py`: facts, 9 tools behind a `Recorder` (call ids, budget 6), validator (backed numbers,
  ≤ 3), mock critic, Strands agent on Bedrock, demo/local cache, `add_to_trace` (fix → recompute → Guardian
  re-check → keep or revert; `cons` filled).
- `src/dh/agents/pipeline.py`: runs the Critic after the Guardian (`critic=False` to skip).
- `src/dh/__main__.py`: `explain` prints the Critic's source/calls; `--save-demo` also saves `cache/critic/`.
- Tests: `tests/test_critic.py` (10), 3 crypto tests in `tests/test_portfolio.py`. 85 pass.
- Notes: `notes/critic-plan.md`, decisions #26, #30, contract §2c + `baskets`/`cons`, README row.

## In progress / next
1. First Bedrock run: `make explain P=amira` with `LLM_PROVIDER=bedrock` → `critic: bedrock`, tool calls in the trace.
2. If slow: set `BEDROCK_CRITIC_MODEL_ID` to a faster model (no code change).
3. `make explain P=amira|mateo|robert SAVE=1`, commit `cache/critic/` **and** `cache/explainer/` (the Critic's fixes
   change the strategies, so the Explainer's hash changes) — before Mon 11:00.
4. Check on the real starter data: what the mock and Bedrock critics object to for each persona.

## Decisions made here
- #40 Markowitz: risk contributions + KYC cross-check, no optimiser
- #26 Crypto only if asked AND allowed AND the model suggests it
- #30 Critic (numbered #27 on the branch) design: evidence-backed objections, fixes tighten inputs, whole calculation rerun, Guardian re-check

## Contract changes
- §1: optional `kyc_bets`, `ev_answer_pct` in the profile; `kyc` in the limits (cross-check only).
- §2c new (`res["critic"]`); strategies gain `baskets`, `cons` filled by the Critic.

## How to check it
- `make test` → 85 pass; `make scenarios` → 16/16
- `make explain P=mateo` (mock): trace shows "Critic → Portfolio" with tool calls, then any recompute step

## Open questions / blocked on
- No starter data in this session: persona results on real data not checked here.
