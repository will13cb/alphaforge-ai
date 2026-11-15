# claude/relaxed-edison-ihsi38 — Joud (with Claude)

**Goal:** fix the bugs a full code audit found when running the pipeline on the three personas.
**Status:** ready to merge (needs `make warm` afterwards, see below)

## Done
- `src/dh/agents/critic.py`: validator also accepts FACTS numbers (client, limits, the strategy's weights/split/stats,
  sum of two weights) and ignores durations; correlations rounded onto a rule threshold are written back exactly;
  prompt `critic-v2`.
- `src/dh/agents/portfolio.py`: levels 2/3 named "less in stocks" / "least in stocks" (was "more/most prudent").
- 3-decimal correlations: `checks.py` C6, `diversification.py`, `portfolio.py` merge note, `analyst.py`, `market.py`.
- `src/dh/llm.py`: `DEFAULT_MODEL_ID` = Opus 5.5, imported by the Explainer and Extractor (Critic via Explainer).
- Wording: `interface/views/results.py`, Explainer template, README, TECHNICAL_DOC, VIDEO_SCRIPT.
- Tests: `tests/test_critic.py` (3 new).

## In progress / next
- **`make warm` with valid AWS keys, then commit `cache/`** (the Critic/Explainer caches no longer match: names and
  prompt changed). Check `make explain P=robert|amira|mateo` shows `source: cache` for both.

## Decisions made here
- #45 in notes/decisions.md.

## Contract changes
- Strategy `name` / `level.label` for levels 2 and 3 changed (display strings only, no field change).

## How to check it
- `make test` → 279 passed. `make explain P=robert`: the Critic's TSLA objection is kept, not "dropped: unbacked".

## Open questions / blocked on
- Will's OK (agents lane).
