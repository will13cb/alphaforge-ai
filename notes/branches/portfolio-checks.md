# portfolio/checks — Joud (Will's plan, branch 2 of 4; agreed with Will)

**Goal:** layer 3 blocks C–F: diversification, risk vs the client, goal fit and profile fit, as checks with one
shape, reused by the Portfolio and the Guardian.
**Status:** ready to merge. Built on `main` after branch 1 (`lane/portfolio`) and the horizon directive (#22).

## Done

| Piece | File | What it does | LLM? |
|---|---|---|---|
| Checks | `src/dh/agents/checks.py` | 17 checks C1–C6, C3b, D1–D3, E, F1–F6, shape `{check, value, limit, status, reason, source}`; `run`, `summary` | no |
| Thresholds | `src/dh/agents/rules.py` | `MAX_COUNTRY_EQUITY` 70%, `SECTOR_WARN` 30%, `MAX_JOB_SECTOR` 15%, `MIN_EFFECTIVE_N` 8, `ETF_ASSUMED_LINES` 100, `CORR_WARN` 0.85, `OVERLAP_WARN` 50%, `TOLERANCE_CLOSE` 80% | no |
| Portfolio | `src/dh/agents/portfolio.py` | `strategies[i]["checks"]`; `fix_diversification` (C6 merge duplicate, C3 trim sector → core ETF, undone if it breaks the loss limit) | no |
| Guardian | `src/dh/agents/guardian.py` | G14 geography, G15 sector + job sector, G16 concentration, G17 drawdown in $, all via `checks.py` | no |
| Diversification | `src/dh/agents/diversification.py` | `report(..., correlations=False)`: no data needed (Guardian on hand-made strategies) | no |
| CLI | `src/dh/__main__.py` | `propose` prints the C–F summary and every ⚠/✘ with its reason | no |
| Tests | `tests/test_checks.py` | 10 tests, each check on its ✔ and ✘/⚠ paths, offline | no |

## Decisions made here
- #20 thresholds and the ✘/⚠ split (`notes/decisions.md`). C3 has two levels: ⚠ above 30% (this plan), ✘ above 40%
  (#18). C6 has two too: ⚠ above 0.85 or ETF overlap above 50%, ✘ at 0.95 or more (#18).

## Contract changes
- `profile.employment_sector` final (also named in `notes/intake-form.md`).
- `strategies[i].checks` final: ids C1–C6, C3b, D1–D3, E, F1–F6.

## How to check it
- `make test`: 61 passed. `make scenarios`: 16/16.
- With the CSVs: `python -m dh propose robert` prints "checks C-F: 17 ✔, 0 ⚠, 0 ✘" for Broad core, and ⚠ C2
  (Canada 79%) for Income / dividends.

## Notes for other agents
- **C1 fixed (Sun):** each company vs its own `company_caps` (#24), same verdict as G4 (was `max_single`).
- **Will: the C-F thresholds are FIXED numbers, the same for every client (Joud, to revisit).** Some checks already
  follow the client: C1 (company cap, #24), D1/D2 (their own loss limit, in $), E (their target), F2 (their horizon,
  #22), F3 (their withdrawals), F4 (their knowledge). But these are constants in `rules.py`, whatever the situation:
  C2 country ≤ 70% · C3 sector 30% ⚠ / 40% ✘ · C3b job sector 15% · C4 ≥ 2 classes · C5 ≥ 8 effective holdings ·
  C6 correlation 0.85 ⚠ / 0.95 ✘, ETF overlap 50% · D1 "close" at 80% of tolerance · E 50% chance · F1 income 50%.
  Ideas if we make them move with the client: C3/C5 looser for a high risk level or a long horizon (Amira) and
  tighter for a cautious one (Robert); C2 home bias allowed when the client spends in CAD and the horizon is short
  (currency risk); C3b tighter when income is "variable"/"uncertain"; E's 50% higher when the goal is essential
  (retirement, major project) than when it is nice-to-have. Any change = a team assumption logged under #20.
- **Don't re-implement a check:** call `checks.run(strategy, profile, limits, rets, holdings)` or one `checks.cX_…`.
  The Critic can use them as tools (each returns JSON).
- **Guardian has 4 more rules (G14–G17):** a hand-made strategy with all-Canadian equities now gets ⚠ G14.
  Scenario `ROBERT_OK` was changed for it (XIU 5, SPY 5, RY 5).
- **Branch 3 (requests):** the "as asked" version should run `checks.run` too, so the side-by-side shows the same
  checks; pros/cons can be written from `checks[i]["reason"]`.

## Open questions / blocked on
- ETF holdings: only SPY's file exists and it has no sector or country, so C2/C3/C3b are lower bounds for ETFs.
  Loading QQQ/XIU/ESGV files (issuer pages) would make them exact.
