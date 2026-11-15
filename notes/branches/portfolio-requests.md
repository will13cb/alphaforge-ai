# portfolio/requests — Joud (Will's plan, branch 3 of 4; agreed with Will)

**Goal:** layer 3 blocks G (request handling) and H (selection, pros/cons): the Robert "25% in Tesla" demo case.
**Status:** ready to merge. Built on `main` after branch 2 (`portfolio/checks`) and Will's #24.

## Done

| Piece | File | What it does | LLM? |
|---|---|---|---|
| Side by side (G) | `src/dh/agents/requests.py` `compare` | "as asked" (`overlay`: room from growth first) vs "fits your limits" (`overlay_growth`: at the Profiler's fit, growth part only); both get C-F checks + Guardian; real weight, drop in % and $, failing checks | no |
| Pros/cons (H) | `requests.pros_cons` | templates filled with `stats`/`checks` only; strict comparisons (no tie claims) | no |
| Selection (H) | `src/dh/agents/pipeline.py` | drops a strategy on a Guardian ✘ **or** a C-F ✘, trace says which; adds `request_comparison` to the result and the trace | no |
| G12 | `src/dh/agents/guardian.py` `_known_numbers` | knows C-F check numbers (values + % in reasons) and the side-by-side numbers | no |
| CLI | `src/dh/__main__.py` | `propose` prints pros/cons and the request side by side | no |
| Persona numbers | `experiments/data/persona_numbers.py` | 36 rows in `results.csv` (`proposal-*`, `request-*`) | no |
| Charts | `experiments/data/export_charts.py` | now from `pipeline.run`: Robert's strategies + TSLA as asked / fits, Amira's | no |
| Tests | `tests/test_requests.py` | 7 tests: overlays, Robert side by side, excluded/unknown requests, pros/cons traceable by G12, a C-F ✘ drops | no |

## Decisions made here
- #28 (`notes/decisions.md`, numbered #25 on the branch): where the request is laid, how "fits" is built, selection, pros/cons wording.

## Contract changes
- `strategies[i].pros`, `cons` final. New pipeline output `request_comparison` (see `notes/contract.md` §2), also in
  `limits["request_comparison"]`.

## How to check it
- `make test`: 76 passed. `make scenarios`: 16/16.
- `python -m dh propose robert`: "as asked: TSLA 25.0% | worst drop -26.5% = 106,121 $ vs 60,000 $ | fail | ✘ C1, D1,
  D2, F2, G4, G6, G7, G9, G17" and "fits your limits: TSLA 3.1% | worst drop -9.6% = 38,241 $ vs 60,000 $ | pass".

## Notes for other agents
- **Explainer (Will):** read `res["request_comparison"]` for the request paragraph (as asked vs fits, $ figures); every
  number in it passes G12. Keep the #24 wording: give the numbers, the client decides.
- **Critic (Will):** `requests.compare(...)` and `checks.run(...)` are deterministic tools; a "what if 10% NVDA" is
  `compare` with another `requested_positions`.
- **Selection changed:** a C-F ✘ now drops a strategy even when the Guardian passes it.
- **App:** `experiments/data/export_charts.py` shows how to chart `res["strategies"]` and the two request versions.

## Open questions / blocked on
- The side by side is laid on one strategy ("Broad core"); laying it on each proposal would triple the output.
