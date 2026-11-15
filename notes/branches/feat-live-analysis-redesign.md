# feat/live-analysis-redesign — Will / app

**Goal:** Refresh both app views with light/dark themes and observable live analysis for clients and judges.
**Status:** ready to review (2026-11-15); not merged or deployed

## Done
- Shared responsive teal/slate palette, Light / Dark appearance switch and wide client workspace.
- Optional Trace/pipeline observer streams completed real hand-offs during both client and jury analysis runs.
- Client Activity page and jury Activity & evidence tab show timestamps, hand-offs, checks, sources, outputs,
  explanation source, actual S3/local storage result and downloadable trace JSON.
- Searchable enabled product universe read through dh.data; reflects enabled additions from Joud automatically.
- Jury results cached per browser session; revisits labelled saved, with an explicit Re-run action for fresh activity.
- Observer snapshots prevent display code mutating evidence; display exceptions cannot change engine results.
- Observer callbacks cleared before retaining results. Updated client profile review disclosure about trace storage.

## In progress / next
- Review branch and merge when ready; deployment is unchanged.
- Joud enables and validates the expanded data via the existing dh.data path.

## Decisions made here
- Display observable hand-offs, numbers, sources and verdicts (existing decision #9), no model reasoning.
- Reuse existing engine and financial rules. No simulated progress or invented data/S3 success.
- Replace shared cross-session demo result cache with per-session state, so live UI callbacks are not replayed as fresh work.

## Contract changes
- Optional `on_step` callback added to Trace, pipeline.run and interface services.run_analysis; existing callers unchanged.
- No changes to profile, limits, ingestion, market functions or financial rules.

## How to check it
- `LLM_PROVIDER=mock .venv/bin/python -m pytest -q`: 259 passed on rebuilt starter data; one existing pandas warning in products.py.
- Fatal Python lint checks and git diff whitespace checks pass.
- `make ui` (client), `make app` (jury); Appearance changes persist through navigation.
- Browser: example client → analysis → results → Activity → product search; jury Activity in dark mode; mobile width has no horizontal overflow.
- Activity is live only during a fresh run; completed evidence remains inspectable afterwards.

## Open questions / blocked on
- Actual AWS S3/Bedrock integration was not exercised: this checkout has no configured AWS credentials.
- Starter universe rebuilt successfully (31 assets). Expanded ingestion and S3 data uploads remain Joud’s work;
  the UI reads whichever universe is enabled, and does not promise 60 products are already loaded or selected.
