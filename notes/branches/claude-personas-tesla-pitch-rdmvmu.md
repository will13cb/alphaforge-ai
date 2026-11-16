# claude/personas-tesla-pitch-rdmvmu — Joud (with Claude)

**Goal:** persona contrast on one screen (same 25% TSLA request for Amira, Mateo, Robert). Video script untouched.
**Status:** ready to merge (draft PR, touches Will's lane `app/`: his OK first)

## Done
- `src/dh/agents/contrast.py`: `contrast(ticker, weight)` runs `pipeline.run` per persona with the request,
  `row()` reads limits / cap / side by side / reason, `markdown()` for the CLI
- `python -m dh contrast [--ticker --weight --log]`, `make contrast` (`LOG=1`)
- `app/app.py`: sidebar option "Same request, three clients: 25% in Tesla" → three columns; FR strings in `dh/i18n_fr.py`
- `results.csv`: `persona-contrast` rows (cap, loss limit, $ drops, failing check counts, chance beyond limit at cap)
- `tests/test_contrast.py` (offline, synthetic returns)

## Decisions made here
- #51 in notes/decisions.md

## Contract changes
- none (reads existing `limits.request_checks`, `request_comparison`)

## How to check it
- `make contrast` → table: Amira 14.1%, Mateo 8.8% (✘ D2, G7 at the cap), Robert 3.1%
- `make app` → sidebar "Même demande, trois clients"
- `.venv/bin/python -m pytest -q tests/test_contrast.py`

## Open questions / blocked on
- Numbers measured with ETF look-through "direct only" (no `data/raw/etf_holdings.csv` here), same as the published
  Robert numbers; re-run `make contrast LOG=1` on the host with holdings if they differ.
