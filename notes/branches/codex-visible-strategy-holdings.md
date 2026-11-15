# codex/visible-strategy-holdings

**Goal:** show each strategy's actual holdings and weights directly in its comparison card.
**Status:** verified and ready to merge (2026-11-15).

## Done
- Added an always-visible holdings table to each strategy card, before the split explanation and pros/cons.
- All holdings shown, largest allocation first, with readable percentage weights and a total row.
- Shows CAD allocation amounts from profile capital times each engine weight; USD-listed holdings still use CAD budget amounts.
- Retained detailed checks/holdings tab, existing strategy weights and metrics.

## Decisions made here
- Holdings should be visible where users compare strategies, rather than hidden in evidence expanders.
- Display-only change, no allocation recalculation or investment-model change.

## Client-facing simplification
- Added plain investment names beside tickers, with Share/Amount columns under How your money is split.
- Shortened strategy titles and replaced internal split-rule prose with plain timeframe/loss-check explanations.
- Renamed tabs Your options / In plain words / Details and removed approval jargon from the opening message.
- Put detailed check IDs, model charts and rule explanations inside an explicit technical expander.
- Retained warnings, all original figures and the full review record.

## Contract changes
- card accepts optional capital for display amounts; no engine schema changes.

## How to check it
- PYTHONPATH=src LLM_PROVIDER=mock python -m pytest -q tests/test_visible_holdings.py tests/test_interface_app.py

## Validation
- 46 focused tests passed: holdings/card/detail rendering, existing guided UI, fixed income and accessibility.
- Fatal lint and whitespace checks passed.

## Open questions / blocked on
- User will copy datathon2026 changes into AlphaForge.
