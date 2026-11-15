# guardian/g12-strict — Will

**Goal:** make "every number traced" a guarantee: G12 let 23–36% of invented numbers through (±0.5 tolerance).
**Status:** done, tested offline (94 tests); merged to main. **Demo cache to regenerate on Will's laptop** (prompt v4: no digit at all).

## Done
| Piece | File | What it does |
|---|---|---|
| Ids instead of numbers | `src/dh/agents/explainer.py` | `placeholders` (facts → ids + NUMBERS table), `render`, `strict_problems` (typed number or unknown id → template), exact G12 in `check`; prompt v3; cache stores `raw` |
| Tighter general G12 | `src/dh/agents/guardian.py` | `check_explanation` tolerance 0.5 → 0.05 |
| Tests | `tests/test_explainer.py` | fakes write ids; typed real number rejected; unknown id rejected; a number 0.3 pt off now fails |

## Decisions made here
- The newest decision in `notes/decisions.md` ("Strict G12").

## Contract changes
- Explainer output gains `raw` (text with ids). `loss_limit_cad` / `capital_cad` in the facts are formatted strings ("60,000 $").

## How to check it
```
make test                                  # 78 passed
make explain P=robert SAVE=1               # + amira, mateo, with Bedrock: regenerates cache/explainer/ (commit it)
```
Expected: `source: bedrock`, `verdict: pass`, G12 "every number is one of the computed facts, exactly".

## Notes for other agents
- **Explainer numbers come only from `explainer.facts`.** To let it quote new numbers (e.g. branch 3's side by side),
  add them to `facts`, not to G12's lists.
- **portfolio/requests:** its change to `guardian._known_numbers` (reading every % from the checks' texts) loosens the
  general G12; drop that part. Its decision must take the next free number (#27 is this one).
- Old v2 cache files in `cache/explainer/` no longer replay; delete them once the v3 ones are committed.

## Open questions / blocked on
1. Regenerating the three demo texts on Bedrock (needs Will's `.env`).
