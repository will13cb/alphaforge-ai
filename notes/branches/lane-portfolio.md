# lane/portfolio — Will (taken over from Joud, Sat Nov 14)

**Goal:** layer 3 blocks A (strategies by what they hold) + B (stocks/bonds split computed from the client and the
data, decision #17) + wiring, so the pipeline proposes strategies end to end. Branch 1 of 4 (then
`portfolio/checks`, `portfolio/requests`, `portfolio/critic`).
**Status:** done, tests green offline; **not yet run on the real starter CSVs** (not in the session that built it).
Merge into main after `python -m dh propose robert` looks right on real data.

## Done

| Piece | File | What it does | LLM? |
|---|---|---|---|
| Takeover | — | merged main; Joud's diversification decision renumbered **#18**; rules renamed D1→**C3** (sector ≤ 40%), D2→**C6** (no pair ≥ 0.95), D3→**C4** (≥ 2 classes) | — |
| Profiler | `src/dh/agents/profiler.py` | `loss_limit` (+ `_source`, `_cad`), `liquidity_floor`; `min_defensive` = max(withdrawals 3y, 5%); `max_drawdown` = loss limit (#19) | no |
| Rules | `src/dh/agents/rules.py` | `SAFETY_MIN_DEFENSIVE` 5%, `GOAL_MIN_PROB` 50% | no |
| Portfolio | `src/dh/agents/portfolio.py` | A: `STRATEGY_DEFS` (core, income, growth tilt), `offered`, `baskets` (allowed only, ESG swap, short-heavy defensive if loss limit ≤ 10%); B: `split_search` (curve 0–100%, ceiling, goal floor, conflict), `build` (crypto cap, P5 single names net of ETFs, rounding, G6 after rounding); minimal H (dedupe, ≤ 3); `describe` | no |
| Diversification | `src/dh/agents/diversification.py` | Joud's report + C3/C4/C6, attached to each strategy | no |
| Guardian | `src/dh/agents/guardian.py` | G7 vs `loss_limit`, G6 vs the new floor (text updated) | no |
| Pipeline | `src/dh/agents/pipeline.py` | no strategy → Market data step (`market.describe`, sources) → Portfolio step → Guardian per strategy; ✘ strategies dropped with the reason (P10); `propose=False` keeps the old hand-made-strategy mode | no |
| CLI | `src/dh/__main__.py` | `python -m dh propose amira\|mateo\|robert` (Robert with the 25% TSLA request) | no |
| Tests | `tests/test_portfolio.py` | 11 offline tests on synthetic returns: ceiling ≤ loss limit and is the largest, liquidity floor, conflict, beginner = ETFs only, ESG/fossil, Robert no crypto, pipeline proposals pass the Guardian | no |

Dropped from Joud's skeleton: `SLEEVE_SHARES` (level → split table) and P1/P4 (levels L, L-1, L-2; fit loop), replaced
by #17. Kept: P2, P3, P5, P7, P9, P10.

## Decisions made here
- #18 Diversification (Joud's, renumbered, rule ids C3/C4/C6).
- #19 Loss limit, defensive floor, goal floor, strategy definitions.

## Contract changes
- `limits`: + `loss_limit`, `loss_limit_source`, `loss_limit_cad`, `liquidity_floor`; `max_drawdown` = loss limit;
  `min_defensive` = max(liquidity floor, 5%).
- §2 `strategies`: finalised (`key`, `split`, `split_range`, `split_curve`, `stats` + `prob_loss`, `outlook`,
  `diversification`, `adjustments`, `guardian`); `pros`/`cons` empty until branch 3; `checks` from branch 2.

## How to check it
```
make test                      # 47 passed (11 portfolio)
make scenarios                 # 16/16, no expected value had to change
python -m dh propose robert    # needs data/raw: 2–3 strategies, split, ceiling, stats, trace
```

## Notes for other agents
- **Horizon directive (#22, Joud):** `limits["horizon_max_growth"]` caps growth from the client's horizon (0% ≤ 2 y →
  100% at 15 y); `min_defensive` = max(withdrawals, 1 − that cap, 5%). Robert is now 15/85 (was 80/20). Scenario
  `ROBERT_OK` (85% defensive) and `big-withdrawal` (horizon 8 y) were updated for it; 16/16 pass.
- **Rule ids renamed:** diversification rules are **C3, C4, C6** (were D1–D3); decision **#18** (was #17 on this branch).
- **Limits changed:** use `limits["loss_limit"]` and `limits["min_defensive"]` (= max(withdrawals 3y, 5%)), not the
  level table; `RISK_LEVELS[...]["min_defensive"]` is no longer read anywhere.
- **Don't rebuild strategies:** call `portfolio.propose` (or `pipeline.run(profile)`); `pipeline.run(..., propose=False)`
  for a hand-made strategy. Proposals come back in `res["strategies"]`, rejected ones in `res["dropped"]`.
- **Joud:** `market.goal_outlook` is ~1.4 s per call at 2000 paths, mostly `qt.goal_probability` → `_as_frame`
  re-validating every path column; the Portfolio calls it once per strategy (+ up to 21× at 500 paths for the goal
  floor). A faster path (validate once, or skip on bootstrap output) would make `propose` ~5× faster.
- `export_charts.py` can now take real strategies from `pipeline.run(...)["strategies"]` (`split_curve` is the
  growth-share vs worst-drop chart).

## Open questions / blocked on
1. **Real-data run** (`python -m dh propose robert|amira|mateo`) on a machine with the CSVs, before merging.
2. Income strategy holds ENB.TO: dropped automatically for fossil-fuel exclusions; for Mateo it's renormalised.
3. ETF holdings: only SPY loaded, so P5 and C3 are lower bounds for QQQ/XIU/ESGV.
