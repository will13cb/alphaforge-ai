# claude/jolly-lovelace-yswcsi — Will (app)

**Goal:** the free-text extractor (#29) and the demo app (`make app`) shows the real pipeline: profile and limits with reasons, up to 3 strategies with
the split chart, the Explainer text with its source and G11–G13, and the trace step by step; works without AWS.
**Status:** built, tested offline and on synthetic data; **not yet run on the real starter CSVs** (not in the session
that built it). Merge after the check below looks right on a machine with `data/raw/`.

## Done

| Piece | File | What it does | LLM? |
|---|---|---|---|
| App | `app/app.py` | sidebar client picker (Amira · Mateo · Robert · Robert asks for 25% TSLA) → `pipeline.run` + `explainer.add_to_trace` (cached per client, "Re-run" button); tabs Profile & limits · Strategies · Explanation · Trace; trace JSON download; clear `make data` message when the CSVs are missing | Explainer only (Bedrock or cached text) |
| Demo profiles | `src/dh/agents/scenarios.py` | `DEMO_PROFILES`, `DEMO_LABELS`: one definition for the app and the CLI, so the Explainer cache hash matches | no |
| CLI | `src/dh/__main__.py` | `propose`/`explain` read `DEMO_PROFILES` (`robert` = Robert + 25% TSLA, unchanged) | no |
| Charts | `src/dh/agents/portfolio_charts.py` | `split_curve_data/chart` (growth share vs worst drop, loss-limit line, horizon/defensive band, chosen split) from `strategy["split_curve"]`; `outcome_frame` feeds Joud's `outcome_chart` from `strategy["outlook"]` (no second bootstrap) | no |
| Extractor | `src/dh/agents/extractor.py` | free text → `profile` (contract §0): Strands agent on Bedrock + `check_profile` tool; code checks schema and grounding (every number written by the client); fixed follow-up questions; cache + rule-based parser offline/fallback; `add_to_trace` puts "Extractor → Profiler" first | yes (Bedrock), rules offline |
| App: free text | `app/app.py` | "Describe yourself (free text)": text → what was understood, what the checks dropped, follow-up form → pipeline | |
| CLI | `src/dh/__main__.py`, `Makefile` | `python -m dh extract "..." [--save-demo]`, `make extract T="..." [SAVE=1]` | |
| Rounding fix | `src/dh/agents/portfolio.py` | `build` steps capped lines down after rounding to 0.5% (a 5.8% crypto cap became 6.0% → Guardian dropped the strategy) | no |
| Tests | `tests/test_extractor.py`, `tests/test_portfolio.py` | 7 extractor tests (words/k/commas, Robert's text, questions, grounding, agent checked by code, fallback, trace) + 1 rounding test | no |
| Tests | `tests/test_app.py` | 4 offline: profiles = CLI, split curve, outcome frame, `AppTest` runs (asks for data when missing) | no |
| Dependency | `pyproject.toml` | `streamlit>=1.50` (`width="stretch"` replaces the deprecated `use_container_width`) | |

The app computes no number: everything is read from the pipeline result (G12 stays true on screen).
Joud's `market_charts.py` is untouched (growth chart with the 2022 band and outcome chart are reused as is).

## Decisions made here
- #29 extractor design (`notes/decisions.md`).
- The app needs the starter CSVs (user's choice): "offline" = no AWS, not no data. No snapshot of results committed.

## Contract changes
- New §0 Extractor → Profiler (`notes/contract.md`). No §1 field changed.

## How to check it
- `make test`: 81 passed. `make scenarios`: 16/16.
- With the CSVs: `make app` → "Robert asks for 25% in Tesla": TSLA warning with its numbers, ~15/85 strategies, the
  Explanation tab says "replayed from the cache" (committed Opus text) and G11–G13 ✔. Plain "Robert" has no cached
  text: it shows the template (expected). If Robert + TSLA shows the template too, the data/rules changed since the
  cache was saved: `make explain P=robert SAVE=1` (AWS open until Mon 13:59) and commit `cache/explainer/`.

- Extractor: `make extract T="I'm 59, retiring in about 4 years, I have 400k, I can't lose more than 15%. Put 25% in Tesla."`
  → profile + questions for what's missing (offline: `source: rules`). With `LLM_PROVIDER=bedrock`: `source: bedrock`;
  add `SAVE=1` and commit `cache/extractor/` so the demo replays offline. In the app: "Describe yourself (free text)".


## After the audit (Sun Nov 15, `notes/audit-2026-11-15.md`)

Will's choices: long data on his laptop; S2 option (a) now, bootstrap later; S3 option (a); nothing submitted yet.

| Piece | Files | Decision |
|---|---|---|
| Long history: build script over the official one, missing history = NaN (not 0%), stand-ins before first price, FX not back-filled, 2008/2020 stress, windows from the data | `scripts/build_long_data.py`, `harness.toml`, `data.py`, `metrics.py`, `market.py`, texts everywhere | #31 |
| 3 strategies = 3 risk levels | `portfolio.levels`, `level_limits`; Critic keeps the level | #32 |
| Each split says what set it | `split_search` (`set_by`, `data_ceiling`), Profiler (`min_defensive_source/why`), Explainer, app, deliverables | #33 |
| Technical fixes P6, P9, P10, C1, P11, P8/P13, P15, P21, P16 | `guardian`, `market`, `checks`, `diversification`, `personas`, `requests`, `pipeline`, `notes/results-status.md` | #34 |

Tests: 141 offline (`test_data_long.py`, `test_audit_fixes.py`, risk-level test). Not done: P20 (CNQ, to verify),
S2 bootstrap condition, S4 company caps from two sub-periods, P12 ETF holdings (manual download).
**On the laptop:** `make data-long` → `make test` → `make scenarios` → `python -m dh propose robert` (check the levels
and the "set by" lines) → `make explain P=robert SAVE=1` (and amira, mateo) → `make log-personas` → commit the cache.

## Merged into main (Sun Nov 15, with Will's OK)
Merged after main's Analyst (#35), then `interface` (#36) on top. Main's C1 (per-company caps) kept: same fix as #34.
Follow-ups on main: Analyst texts and year check use the data window (#31; was hardcoded 2021-2026); Analyst no longer
crashes when the Bank of Canada rate isn't loaded (the one failing test); interface cards show what set each split (#33).
`make test`: 200 passed, 3 skipped (need the CSVs).

## App polish (Sun Nov 15, evening)
- `make app` saves each run's trace (`tracestore.save_run_safe`: S3, else a local copy, never breaks the screen); the
  Trace tab and the sidebar say where. Test in `tests/test_app.py`.
- Layout fixes from screenshots (synthetic data): short metric values, split-chart title outside the chart, outcome
  charts with their own theme and height (Streamlit's theme squashed them), cons deduplicated, persona card paragraph.
- Docs: `make app` = the demo (jury view), `make ui` = the client view; README, video script (15 s on the interface),
  one-pager.

## Open questions / blocked on
- `checks.c1_company` compares with `limits["max_single"]` (largest cap), not each company's own `company_caps` (#24):
  the C1 row can say ✔ where G4 is stricter. One-line fix in `checks.py`, not done here.
- Critic and Analyst not built. The extractor has not been run against Bedrock yet (no `.env` here): no demo cache.
- S3 upload of the trace (AWS qualifying requirement) not wired in the app.
