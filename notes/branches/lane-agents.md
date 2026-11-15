# Branch `lane/agents` (owner: Will)

What this lane built, how it fits together, and what is still open. Reasons behind each choice: `notes/decisions.md`.
Contract between agents: `notes/contract.md`. Merged into main at `4ec0811`.

## What's built

| Piece | File | What it does | LLM? |
|---|---|---|---|
| Rule tables | `src/dh/agents/rules.py` | Risk levels 1–5 and their thresholds, asset groups, exclusion keywords, KYC essentials | no |
| Profiler | `src/dh/agents/profiler.py` | `profile` (facts) → `limits` (conclusions, each with a written reason) | no |
| Guardian | `src/dh/agents/guardian.py` | Rules G1–G13 "modelled on NI 31-103 KYC/suitability", ✔ / ⚠ / ✘, any ✘ sends the step back | no |
| Trace | `src/dh/agents/trace.py` | One plain-language line per hand-off between agents, plus the checks | no |
| Pipeline | `src/dh/agents/pipeline.py` | Profiler → Guardian → [Portfolio] → Guardian → [Explainer] → Guardian | no |
| Test profiles | `src/dh/agents/scenarios.py` | 16 fictional profiles with expected verdicts (`make scenarios`) | no |
| ETF holdings | `src/dh/holdings.py`, `scripts/build_holdings.py` | Issuer files → `data/raw/etf_holdings.csv` → `{etf: {holding: weight}}` | no |
| Look-through | `dh.metrics.look_through`, `overlap` (shared file) | Real exposure per company = direct + through ETFs | no |

## How a request flows

```
profile (facts) ──► Profiler (rules) ──► limits + reasons + flags
                                   │
                                   ▼
                       Guardian G1 (KYC complete?) ── missing → ask the client, stop
                                   │
                       [Portfolio: not built yet] ──► strategy (weights + stats from dh.metrics)
                                   │
                       Guardian G2–G10 (limits, exclusions, look-through) ── ✘ → back to Portfolio
                                   │
                       [Critic (LLM), Explainer (LLM): not built yet] ──► client text
                                   │
                       Guardian G11–G13 (disclaimer, every % traced, refusals explained) ── ✘ → back to Explainer
                                   │
                                   ▼
                                 client
```

Each arrow writes a trace step, e.g. "Profiler → Portfolio: risk level 2 (Cautious; tolerance 2, capacity 2) … Flags:
request TSLA 25%: above the single-company cap 8%", followed by its ✔/⚠/✘ list.

## Key design choices (details in `notes/decisions.md`)

- **The LLM argues, code enforces.** Profiler and Guardian are deterministic, so the same answers always give the same
  limits and verdicts, and they can be tested. The LLM only extracts facts from free text (extractor), judges (Critic)
  and writes (Explainer). (#2, #4)
- **"Modelled on" NI 31-103, never "compliant".** (#3)
- **Risk level = lower of tolerance and capacity.** Thresholds are team assumptions in `rules.py`. (#5)
- **Templates, not an optimiser, for strategies.** The efficient frontier is a chart. (#1)
- **Single-company cap counts ETF look-through.** Exclusions found only inside ETFs are a ⚠ to disclose. (#6)

## Validation

- `make test`: 22 tests, offline (scenarios use ILLUSTRATIVE holdings or `{}`, never the real file).
- `make scenarios`: 16/16 profiles behave as expected, logged in `results.csv` (commit `ad927df`).
- Limits of that number (#7): it tests the rules, not real portfolios (strategy stats in the scenarios are made up);
  G12 checks that each number exists among the computed outputs, not that it has the right label.

## ETF holdings status

| ETF | Status |
|---|---|
| SPY | Loaded from State Street, as of 2026-11-12, 503 holdings, sums to 99.97% |
| QQQ, ESGV, XIU | Download by hand (pages need JavaScript), see `data/README.md`; then rerun `scripts/build_holdings.py` |

Real look-through today (SPY only): Amira's "Growth tilt" holds NVDA at 13.23% (12% direct), under her 15% cap.
QQQ's real NVDA weight decides whether it crosses. ESGV fossil-fuel exclusion: not verified.

## Still open in this lane

1. **Portfolio** (decision #17, tree in `notes/system-design.md`): up to 3 strategies defined by what they hold
   (growth + defensive baskets from `limits.allowed_assets`); for each, compute the split between the goal floor and the
   risk ceiling (largest growth share whose 2021–2026 worst drop ≤ the client's loss limit), liquidity floor, conflict
   message; stats from `market.strategy_stats`; then diversification checks C1–C6, risk D1–D3, fit E–F, request G.
2. **Critic** (LLM, one round, written guide) and **Explainer** (LLM, quotes only traced numbers and `limits.reasons`).
3. **Free-text extractor** (LLM → `profile` fields, follow-up questions for `missing`).
4. ~~Validate thresholds on the 2022 data~~ done by Joud (#13). **New (#17):** Profiler computes the client's loss limit
   (min of tolerance and capacity in $) and the liquidity floor; Guardian G6 = liquidity floor + level safety net,
   G7 = client's own loss limit; update the ~8 scenarios whose expected values change; contract fields `split`,
   `split_range`, `split_curve`, `loss_limit_source`, `employment_sector` (drafts in `notes/contract.md`).
5. **Show the trace in the app** (`app/app.py`), and save it as JSON to S3.
6. Load QQQ, ESGV, XIU holdings; rerun the real look-through numbers.
