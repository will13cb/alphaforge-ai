# lane/market-data — Joud

**Goal:** a deterministic market-data agent that turns the starter data into traced facts (per-asset return,
volatility, max drawdown, correlation, 2022 behaviour, macro context) and portfolio stats the Portfolio, Guardian,
Critic and Explainer can quote without recomputing anything.
**Status:** in progress. Code and tests done on fake data; not yet run on the real starter CSVs (not on this machine).
main merged in at `4f588a0` (no conflicts).

## Done

| Piece | File | What it does | LLM? |
|---|---|---|---|
| Quant toolkit | `src/dh/quant_toolkit.py` | erk.py + evaluation.py, fixed and extended: 86 functions (risk, tails, stress, correlation, frontier, Monte Carlo, goal probability…), `ProductEvaluator`, `list_tools()` | no |
| Market-data agent | `src/dh/agents/market.py` | `asset_summary`, `strategy_stats`, `correlations`, `data_quality`, `macro_snapshot`, `market_facts` (one JSON for the trace), `describe` (hand-off line), `tools` (catalogue) | no |
| Tests | `tests/test_market.py` | 7 tests on synthetic returns: stats equal `dh.metrics`, portfolio stats, plugs into Guardian G7/G8, correlated twins detected, JSON-ready output, English alerts, catalogue | no |
| Annualisation fix | `src/dh/metrics.py` (shared) | `periods_per_year()`: annualise with observed rows/year (~261), 252 only as fallback; test in `tests/test_market.py` (decision #12) | no |
| Threshold check | `experiments/data/threshold_check.py` | riskiest mix allowed per level vs G7/G8 limits, `--log` → `results.csv` (decision #13) | no |
| Goal outlook | `src/dh/agents/market.py` `goal_outlook` | prob. of loss / of target + p5/p50/p95, `replay` and `risk_only` (decision #13) | no |
| Tools for LLM agents | `src/dh/agents/market.py` `AGENT_TOOLS` | 6 deterministic functions the Strands Critic/Analyst may call: JSON in/out, errors as `{"error"}`, unknown tickers refused (decision #15) | no |
| One calendar | `src/dh/data.py` `price_panel` | calendar of the whole universe, then select tickers: same numbers however loaded (decision #15) | no |
| Charts | `src/dh/agents/market_charts.py` | growth + 2022 band, outcome range, correlations, risk/return + frontier, 2022 bars: `*_data()` + Altair `*_chart()` (decision #16) | no |
| Chart export | `experiments/data/export_charts.py` | PNG + HTML into `experiments/data/figures/` (gitignored) for the video | no |
| Country | `src/dh/agents/market.py` `country_of`, `countries` | country of listing per asset (Canada / United States / Global crypto) for C2 geography; in every asset row (#15 addendum) | no |
| Persona numbers | `experiments/data/persona_numbers.py` | logs every proposal's drop, 2022, risk-only chance of loss, growth share + Robert's TSLA side by side in `results.csv` (rule 3) | no |
| Analyst | `src/dh/agents/analyst.py`, `tests/test_analyst.py`, `python -m dh ask` | follow-up questions in French or English: names → tickers, several requests at once, 8 question types; tools re-run the pipeline; answer checked by code: numbers, counts by kind, years, attribution, advice wording FR/EN (#35) | Strands (mock offline) |
| Dependency | `pyproject.toml` | `scipy>=1.11` (the toolkit), `altair>=5` (charts; already in Streamlit), dev: `vl-convert-python` (PNG) | |

How it fits: `dh.data` (load, convert to CAD, calendar) → `market.py` (facts) → Portfolio reads `assets` and calls
`strategy_stats(weights)` for each candidate → Guardian G7/G8 read `strategy["stats"]` → Explainer cites `sources`,
`assumptions`, `limits`.

- Sun: tests no longer write traces to S3 or to `outputs/traces/` (`tests/conftest.py`, autouse fixture): a test run
  is not evidence, and `make test` loads `.env` (S3_BUCKET). Branch restarted from `main` (previous work merged).

## In progress / next

1. ~~Run on the real starter data~~ **Done:** 31 assets × 1304 rows, 2021-11-15 → 2026-11-12, all 30 tests pass.
   `describe`: deepest drawdown SHOP.TO −83%, most correlated pair ESGV/SPY (0.99). Annualisation check in decision #12.
2. ~~Validate the risk-level thresholds on 2022~~ **Done (decision #13):** G7 holds in 90% of 20 cases, L1 fails with an
   equal-weight defensive basket. Proposal to Will in #13 (ZST-heavy L1 template or 10% limit).
3. ~~Risk of ruin / goal probability~~ **Done:** `goal_outlook(weights, capital=, horizon_years=, monthly_contribution=,
   target_amount=)`. Portfolio should show `risk_only` first.
4. **Macro context with publication lag:** `macro_snapshot` gives the latest value per series dated by reference month;
   add the "as published on date X" view before anything uses macro in a simulation.
5. ~~Charts for the app and the video~~ **Done (decision #16):** `market_charts.py` + `export_charts.py`.
6. ~~Persona numbers in `results.csv`~~ **Done:** `experiments/data/persona_numbers.py --log` (36 rows).
7. ~~Replace the illustrative strategies~~ **Done:** `export_charts.py` now charts `pipeline.run` strategies (Robert incl. TSLA as asked / fits, Amira).
8. ~~Requested by Will (#17)~~ **Done (Sun):** `market.required_return(capital, horizon_years, target_amount,
   monthly_contribution)` → yearly return the goal needs (start-of-month contributions, as `goal_outlook`), next to
   cash (ZST.TO last 12 months, Bank of Canada overnight rate with its date) and a one-line reading; also in
   `AGENT_TOOLS` (7 tools). `split_curve` already exists on the Portfolio side (`split_search` → `split_curve`).

## Decisions made here

- #21 CPPI tested, then set aside (judges' scope: decision-support, simulation only).
- #16 Charts = `*_data()` + Altair `*_chart()`, same numbers as the trace.
- #15 Tools for the Strands agents (#14) + one universe-wide calendar.
- #13 Thresholds checked (L1 too tight with an equal-weight defensive basket); goal outlook leads with `risk_only`.
- #12 Annualisation: observed rows per year from the dates, not fixed 252 (`notes/decisions.md` #12). Chosen over
  261 hard-coded, dropping holidays, or documenting only.
- #10 Market data: base stats from `dh.metrics` (same numbers as `make check`), tail and stress measures from
  `dh.quant_toolkit`; 2022 shown as calendar year + stress window; CVaR 95% historical daily; every rate a fraction;
  `strategy_stats` keys = what the Guardian already reads.

## Contract changes

- **Added (draft) `notes/contract.md` §1b "Market data → …"**: exact fields of `market_facts` (top level, asset row,
  `correlations`). Nothing existing was changed. **Will to confirm.**
- **Proposed, not applied:** keys for `strategies[i].stats` in §2 = `ann_return`, `ann_vol`, `max_drawdown`, `cvar_95`,
  `worst_12m`, `return_2022`, `stress_2022`, `stress_2022_drawdown` (output of `strategy_stats`). §2 still says
  "return, volatility, max drawdown, 2022 return, risk of ruin"; Will decides.
- **Proposed:** `strategies[i].stats` gets `goal` = output of `goal_outlook` (risk of ruin = `risk_only.prob_loss`).
- Sign conventions Portfolio/Guardian must know: `max_drawdown` and `stress_2022_drawdown` are ≤ 0; `cvar_95` is a
  positive loss. `sharpe` is a ratio, not a %.

## Notes for other agents
- **`aws/architecture.md` + README aligned with what runs (Sun):** AgentCore not deployed; Guardian G1–G17; the Analyst's
  answer is checked by code, its what-ifs go through the Guardian; the app does not save runs to S3 yet (only `explain`).
- **Analyst built (#35) and in the app** ("Follow-up (Analyst)" tab, `app/app.py`; `analyst.ask`, not
  `add_to_trace`, so the cached run is never mutated). Will: first Bedrock run: `LLM_PROVIDER=bedrock python
  -m dh ask robert "what if I put 25% in TSLA?" --save-demo`, commit `cache/analyst/`; it uses `BEDROCK_CRITIC_MODEL_ID`
  or `BEDROCK_MODEL_ID`. Results land in `res["followups"]`.
- **`required_return` (Will's request #17):** e.g. Robert 400,000 $ → 450,000 $ in 4 y needs 2.99%/yr vs cash 2.51%
  (ZST, last 12 months) and a 2.50% policy rate. Tool for the Critic/Analyst; JSON, errors returned.

- Portfolio (Will, `lane/portfolio`): call `market.countries(tickers)` for C2 geography; don't rebuild it from tickers.
  Pass `rets=data.returns()` once to `strategy_stats` / `goal_outlook` inside loops (avoids reloading).
- Asset rows (`asset_summary`, `list_assets`, `asset_facts`, `market_facts["assets"]`) now have a `country` field.
- **No CPPI (decision #21, set aside):** don't look for `protection.py`; it was removed.
- **`goal_outlook` is ~5× faster** (0.8 s → 0.15 s at 2000 paths, 0.04 s at 500), results identical to the digit:
  `quant_toolkit._as_frame` now validates float tables in one vectorised pass (was 2000 column-by-column checks).
  Your B2 goal-floor search (21 × 500 paths) now costs about 1 s per strategy. No change needed on your side.
- **Robert's 80/20 (resolved by decision #22, pushed to `lane/portfolio` in `e6825ec`):** the data-only ceiling allowed
  85% stocks at 4 years (in CAD the USD cushioned 2022; without that cushion 65%). The horizon directive
  (`rules.horizon_max_growth`, 0% up to 2 y → 100% from 15 y) now caps him at 15/85; Mateo 60/40, Amira 95/5.
- `src/dh/agents/portfolio.py` exists here only as the skeleton commit `49a1411` shared with `lane/portfolio`; Will's
  branch owns it. Merging either branch first is fine (same commit).

## How to check it

Windows (no `make`), from the repo root:

```
$env:LLM_PROVIDER='mock'; python -m pytest -q tests/test_market.py     # 7 passed
$env:LLM_PROVIDER='mock'; python -m pytest -q                          # 35 passed (whole suite)
```

With the starter CSVs in `data/raw/` (`make data`):

```
$env:PYTHONPATH='src'; python -c "from dh.agents.market import asset_summary; print(asset_summary().round(3).to_string())"
$env:PYTHONPATH='src'; python -c "from dh.agents.market import market_facts, describe; print(describe(market_facts()))"
```

You should see one row per asset (31) with `ann_return`, `ann_vol`, `max_drawdown`, `cvar_95`, `worst_12m`,
`return_2022`, `stress_2022`; the `ann_return`/`ann_vol`/`sharpe`/`max_drawdown` columns must equal `make check`.
`describe` prints one line: number of assets, window, deepest drawdown, most correlated pair.

## Open questions / blocked on

1. ~~Starter CSVs are not on this machine~~ (resolved: shared by hand, decision #11). `make data` rebuilds them by downloading from Yahoo, Bank of Canada and
   FRED (needs internet + yfinance), or Will sends the CSVs. Blocks "Next" items 1 and 2.
2. ~~Calendar vs annualisation~~ **Done (decision #12)**: `dh.metrics` now annualises with the observed rows per
   year. Shared file: **Will to confirm**; `make check` numbers shift slightly.
3. **Lane table:** `src/dh/quant_toolkit.py` is a new file in my lane but not listed in the `CLAUDE.md` lane table
   (shared file). Propose adding it next to `src/dh/agents/market.py`.
4. **Wiring (Will, #14):** wrap `market.AGENT_TOOLS` with strands `@tool` for the Critic/Analyst. `pipeline.py` doesn't call the agent yet. Suggested line:
   `tr.step("Market data", "Portfolio", market.describe(facts), output=facts, sources=facts["sources"])`.
5. **Language:** the repo is in English. The data-quality `alerts` (the only toolkit text that reaches the agent's JSON)
   are now English. The toolkit's own docstrings and internal dict keys are still French (it was written for the EDHEC
   course); `market.py` maps the keys it uses to English names. Translate the rest only if Will wants it.
