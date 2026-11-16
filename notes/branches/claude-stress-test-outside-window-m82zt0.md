# claude/stress-test-outside-window-m82zt0 — Joud (with Claude)

**Goal:** a "What if March 2020 happened again?" screen that replays the COVID crash on the proposed strategies,
while every calculation stays on 2021-2026.
**Status:** ready for review (not merged: the Devpost repo freeze was Sun Nov 15 23:59).

## Done
- `src/dh/stress.py`: `replay`, `sentence` (fr/en), `build`, `ensure`; window = `market.STRESS_MORE["2020"]`
- `src/dh/data.py`: `_panel`/`_returns` read `Config.data_dir` when it is not the harness folder (`_files`, `_files_at`);
  the harness's own loads unchanged (same cache, still patchable in tests)
- `interface/core/services.py` `stress_2020` (error boundary), `interface/views/results.py` `crash_2020` section
  (tab "Your options"), French strings in `src/dh/i18n_fr.py`
- `make data-stress`; `tests/test_stress.py` (synthetic folder), `tests/test_interface_app.py::test_results_show_march_2020_replay`
- results.csv rows `stress-covid-2020` (first option of Amira, Mateo, Robert)

## In progress / next
- Optional: copy `data/raw_stress/` to S3 `raw_stress/` and pull it in `bootstrap.from_s3`
- Optional: expose `replay` as an Analyst tool (would change cached answers, so left out)

## Decisions made here
- #50 (notes/decisions.md)

## Contract changes
- none (new module; no field added to `limits` or strategies)

## How to check it
- `make data && make data-stress`, `make test`, `make ui` → example client → results: section "Et si mars 2020 se
  répétait ?" says Robert's first option would have lost 9.2% (≈ 36 989 $), under his 15% limit (60 000 $)

## Open questions / blocked on
- Merge to `main` only if the team confirms it does not break the Sun 23:59 freeze rule
