# Contract between agents (DRAFT, edit together)

What each agent hands to the next. Plain dicts / JSON, never shared classes, so each lane can work with fake data
in this format until the other side is ready. The same JSON goes into the trace store (and S3).

Rule: the Profiler outputs two separate parts.
- `profile` = **facts**, what the client said (entered or extracted).
- `limits` = **conclusions**, what the Profiler derives from the facts. Portfolio respects ONLY `limits`
  (plus the goal fields for Monte Carlo). Guardian and Explainer read both.

## 0. Extractor → Profiler (`extractor.extract(text)`, decision #29)

Free text → the same `profile` dict as the guided form (§1), so nothing downstream cares which was used.

| Field | Type |
|---|---|
| `profile` | §1 fields, only those that passed the checks (schema, values, every number written in the client's words); `name` defaults to "Client", `request` to the text |
| `missing` | list of `rules.ESSENTIAL_FIELDS` still unknown |
| `questions` | list of {`field`, `question`}: one fixed question per missing essential (code, not the LLM) |
| `notes` | list of str: what the checks dropped and why ("capital: 500000 is not written in the client's words") |
| `source` | `bedrock` · `cache (cache/extractor)` · `cache (.cache/extractor)` · `rules` (offline parser / fallback) |
| `model`, `check_calls`, `hash`, `note` | Bedrock model id ("" for rules), `check_profile` calls, cache key, why the fallback was used |

`extractor.add_to_trace(res, ex, answered)` puts "Extractor → Profiler" (and "Client → Profiler" for answered questions)
at the start of the pipeline trace and stores `res["extraction"]`.

## 1. Profiler → everyone

### `profile` (facts)

| Field | Type | Example (Robert) | Used by |
|---|---|---|---|
| `name` | str | "Robert" | Explainer |
| `age` | int | 59 | Profiler |
| `horizon_years` | float | 4 | Portfolio, Monte Carlo |
| `objective` | `growth` · `retirement` · `major_project` · `income` · `legacy` · `safety_cushion` | "retirement" | Portfolio |
| `capital` | float, CAD | 400000 | Monte Carlo, risk of ruin |
| `monthly_contribution` | float, CAD | 0 | Monte Carlo |
| `target_amount` | float or null | null | risk of ruin |
| `emergency_fund_months` | float | 12 | Guardian |
| `income_stability` | `stable` · `variable` · `uncertain` | "stable" | Profiler |
| `employment_sector` | str, a sector name as in `assets_universe.csv` (e.g. "Energy", "Health Care") or null | "Health Care" | Portfolio (C3b job-sector cap, ✘ above 15%, decision #20) |
| `withdrawal_share_3y` | 0–1 | 0.2 | Profiler |
| `loss_reaction` | `sell_all` · `sell_some` · `hold` · `buy_more` | "hold" | Profiler |
| `knowledge_level` | `none` · `basic` · `intermediate` · `advanced` | "advanced" | Profiler |
| `years_experience` | float or null | 20 | Profiler |
| `products_held` | list of str (`stocks`, `etfs`, `bonds`, `crypto`…) | ["stocks", "etfs", "bonds"] | Profiler |
| `quiz_correct` | 0–3 or null | null | Profiler (caps knowledge) |
| `kyc_bets` | {`bet_small`, `bet_large`, `bet_savings`}: the guaranteed return chosen instead of each `dh.kyc` bet, or null | null | Profiler (cross-check only, #40) |
| `ev_answer_pct` | number or null: expected average return of the +25% / −5% bet (right: 10) | null | Profiler (wrong → knowledge ≤ 3, #40) |
| `max_loss_pct` | 0–100 | 15 | Profiler |
| `interests` | list of str | ["dividends", "canada"] | Portfolio |
| `exclusions` | list of str | ["crypto"] | Portfolio, Guardian |
| `request` | str | "Put 25% in TSLA" | Critic, Guardian, Explainer |
| `requested_positions` | dict ticker → weight (what they asked, a fact) | {"TSLA": 0.25} | Profiler, Guardian |
| `existing_positions` | dict ticker → dollars the client already holds (a fact; funds without data use a labelled stand-in, #42) | {"TSLA": 60000, "XIU.TO": 30000} | Portfolio (`existing.review`), interface |
| `missing` | list of str | ["target_amount"] | Profiler follow-up questions |

### `limits` (conclusions)

| Field | Type | Example (Robert) |
|---|---|---|
| `risk_tolerance` | 1–5 | 2 |
| `risk_capacity` | 1–5 | 2 |
| `risk_level` | 1–5, the lower of the two | 2 |
| `knowledge_score` | 1–5, computed by rules (declared level, experience, quiz cap, expected-value question) | 5 |
| `kyc` | null, or {`A`, `band`, `A_by_bet`, `implied_tolerance` [lo, hi], `tolerance`, `agrees`, `expected_value`, `flags`, `message`, `reasons`}: cross-check only, no limit reads it (#40) | … |
| `max_drawdown` | 0–1, = `loss_limit` (kept for older code) | 0.15 |
| `loss_limit` | 0–1, the client's loss limit = min(tolerance `max_loss_pct`/100, capacity: `RISK_LEVELS[risk_capacity].max_drawdown`) (#17, formula #19); G7 reads it | 0.15 |
| `loss_limit_cad` | int or null, `capital × loss_limit` | 60000 |
| `liquidity_floor` | 0–1, `withdrawal_share_3y` | 0.20 |
| `target_vol` | 0–1 | 0.08 |
| `min_defensive` | 0–1, max(`liquidity_floor`, `rules.SAFETY_MIN_DEFENSIVE` 5%) (#19); G6 reads it | 0.20 |
| `horizon_max_growth` | 0–1 | 0.15 (4 years: decision #22 directive; 1 from 15 years) |
| `loss_limit_source` | `tolerance` · `capacity` (which one set the loss limit) | "tolerance" |
| `company_caps` | dict ticker → 0–1: each company's own cap, counted through ETFs (#24): min(¼ × loss limit / its worst 2021–2026 drop, ⅕ × stock room) | {"TSLA": 0.031, "JNJ": 0.031, …} |
| `max_single` | 0–1, the largest of `company_caps` (kept for display; G4 and Portfolio use `company_caps`) | 0.031 |
| `max_crypto` | 0–1, same rule with BTC + ETH as one bet; 0 if excluded or knowledge ≤ 2 (#24) | 0.0 |
| `allowed_assets` | list of tickers | […] |
| `reasons` | list of str | ["horizon 4 years → capacity 2", …] |
| `flags` | list of str | ["request TSLA 25%: TSLA's worst drop in 2021-2026 was -70.9%; at 25% that alone would be -17.7% of the portfolio, more than your whole 15% loss limit; …; it fits up to 3.1%"] |
| `request_checks` | list of {`ticker`, `asked`, `worst_drop`, `loss_at_asked`, `fits_up_to`, `reason`} for requests not included (#24); the Explainer quotes these | [{"ticker": "TSLA", "asked": 0.25, …}] |
| `min_defensive_source`, `min_defensive_why` | which floor binds (`liquidity` · `horizon` · `safety`) and a sentence for the trace (#33) | "horizon" |
| `missing` | list of str (non-empty → no limits, ask first) | [] |

Rules:
- **The knowledge score acts through the limits.** A beginner gets a halved loss budget per company (lower `company_caps`),
  `max_crypto` = 0 and a flag. Portfolio doesn't need to know why; Guardian and Explainer read the flag and say no, with the reasons.
- **`reasons` is mandatory.** Every limit says where it came from. The Explainer quotes it.
- **Thresholds are team assumptions**, set in `src/dh/agents/rules.py` (table and reasons: `notes/decisions.md` #5).
  Implemented by `derive_limits` in `src/dh/agents/profiler.py`.

## 1b. Market data → Portfolio, Critic, Guardian, Explainer (DRAFT — proposed by Joud on `lane/market-data`, Will to confirm)

Deterministic, no LLM. Code: `src/dh/agents/market.py` → `market_facts(tickers)`. One JSON dict, written to the trace as is.
All rates and returns are **fractions** (0.12 = 12%), so the Guardian's G12 can trace them. Existing fields above and
below are unchanged; this section only adds what the market-data agent hands over.

### `market_facts` (top level)

| Field | Type | Example |
|---|---|---|
| `agent` | str | "Market data" |
| `base_currency` | `CAD` · `USD` (from `harness.toml`) | "CAD" |
| `period` | {`start`, `end`} ISO dates of the returns used | {"start": "2021-11-15", "end": "2026-11-12"} |
| `assets` | list of asset rows (below), one per ticker | […] |
| `correlations` | object (below), or null if only one asset | {…} |
| `quality` | {ticker: {`usable`: bool, `alerts`: list of str}} | {"XIU.TO": {"usable": true, "alerts": []}} |
| `macro` | list of {`series_id`, `date`, `value`, `unit`, `frequency`, `label`, `source`}, latest value per series, or null | […] |
| `sources` | list of {`data`, `source`, `window`, `terms`} | Yahoo Finance, Bank of Canada, FRED |
| `assumptions` | list of str | ["Daily simple returns on adj_close …", …] |
| `limits` | list of str | ["Past returns do not predict future returns …", …] |

### Asset row (`assets[i]`)

| Field | Type | Meaning |
|---|---|---|
| `ticker` | str | starter-pack ticker, e.g. "XIU.TO" |
| `name`, `asset_class`, `currency`, `sector` | str or null | from `assets_universe.csv` (null when the CSVs are absent, e.g. tests) |
| `country` | `Canada` · `United States` · `Global (crypto)` | country of **listing**, from the `market` column (TSX → Canada); for an ETF, where it is listed, not its holdings. `market.countries(tickers)` gives it without the CSVs (C2 geography) |
| `start`, `end`, `n_obs` | str, str, int | window and number of daily returns |
| `ann_return` | float | annualised compound return (`dh.metrics.ann_return`) |
| `ann_vol` | float | annualised volatility (`dh.metrics.ann_vol`) |
| `sharpe` | float | Sharpe, risk-free 0% (`dh.metrics.sharpe`); a ratio, not a % |
| `max_drawdown` | float ≤ 0 | worst peak-to-trough on the window (`dh.metrics.max_drawdown`), e.g. -0.32 |
| `cvar_95` | float ≥ 0 | average daily loss on the worst 5% of days, a positive number |
| `worst_12m` | float or null | worst return over any rolling 252-day window (null if < 1 year of data) |
| `return_2022` | float or null | calendar-year 2022 return |
| `stress_2022` | float or null | return over the 2022 stress window (2022-01-03 → 2022-10-12) |
| `stress_2022_drawdown` | float or null | deepest drop inside that window |
| `stress_2008`, `stress_2008_drawdown`, `stress_2020`, `stress_2020_drawdown` | float, **only present when the history covers the window** (long build, #31) | 2007-10-09 → 2009-03-09, 2020-02-19 → 2020-03-23 |

### `correlations`

| Field | Type |
|---|---|
| `pearson` | {ticker: {ticker: correlation}}, rounded to 3 decimals |
| `average` | float, mean of the off-diagonal correlations |
| `top_pairs` | list of {`a`, `b`, `correlation`}, most correlated first (5 by default) |
| `n_obs` | int, days with data for every asset |

### Proposed keys for `strategies[i].stats` (§2) — to agree with Will, §2 not edited

`market.strategy_stats(weights)` returns exactly the asset-row measures for the weighted portfolio (daily
rebalanced): `ann_return`, `ann_vol`, `max_drawdown`, `cvar_95`, `worst_12m`, `return_2022`, `stress_2022`,
`stress_2022_drawdown`. The Guardian already reads `max_drawdown` (G7) and `ann_vol` (G8) under these names.
Risk of ruin is not in it yet: it needs the goal fields (`capital`, `monthly_contribution`, `target_amount`).

## 2. Portfolio → Critic, Guardian, Explainer

`portfolio.propose(profile, limits)` → `strategies`: list of at most 3 (most growth first), each:

| Field | Type |
|---|---|
| `key`, `name` | unique id (`core`, `income`, `growth`, or `core-3` when a flavour is used twice) and "Broad core: more prudent" style name |
| `flavour` | `core` · `income` · `growth`: the baskets (`STRATEGY_DEFS`) (#32) |
| `level` | {`rank` 1–3, `label`, `delta` (0, 0.10, 0.20), `target_growth`}: level 1 = the most growth the limits allow (#32) |
| `risk_level` | 1–5, the client's level (label) |
| `weights` | dict ticker → weight, 0.5% steps, sums to exactly 1 (G2) |
| `split` | {`growth`, `defensive`}, sums to 1; growth = everything not in `rules.DEFENSIVE` |
| `split_range` | {`floor` (float or null), `ceiling`, `liquidity_floor`, `conflict`: bool, `conflict_message`: str or null, `set_by` (worst_drop · horizon · liquidity · safety · level), `set_by_text`, `data_ceiling` (what the worst-drop test alone allows)} (#17, #33) |
| `split_curve` | list of {`growth`, `max_drawdown`, `stress_2022`, `return_2022`, `ann_vol`} per 5% step, 0–100%, for the chart |
| `stats` | `market.strategy_stats` keys (`ann_return`, `ann_vol`, `max_drawdown`, `cvar_95`, `worst_12m`, `return_2022`, `stress_2022`, `stress_2022_drawdown`) + `prob_loss` (risk-only), fractions only |
| `outlook` | full `market.goal_outlook` (CAD amounts), or null without `capital` |
| `diversification` | `diversification.report` + `checks` (C3/C4/C6, #18) |
| `adjustments` | list of str: why offered, what it holds, swaps, exclusions, caps, trims (for the trace) |
| `pros`, `cons` | list of str, written by `requests.pros_cons` from the strategy's own `stats` and `checks` (never the LLM); every % is traceable by G12 (decision #28) |

**Pipeline output `request_comparison`** (decision #28, None without a request): `base` (strategy name), `request`, `why` {ticker: Profiler reason}, `not_assessable` [tickers without data], `as_asked` and `fits` (absent when nothing fits), each {`label`, `weights`, `real_weight` {ticker: weight through ETFs}, `max_drawdown`, `drawdown_cad`, `loss_limit`, `loss_limit_cad`, `return_2022`, `ann_vol`, `growth`, `verdict`, `fails` [{`id`, `reason`}], `warnings` [...]}; `fits` adds `request_at` {ticker: weight}; `summary` (trace line). Also copied into `limits["request_comparison"]` so G12 knows its numbers.
| `baskets` | {`growth`, `defensive`}: {ticker: share} the split was computed from (the Critic's fixes rerun from these) |
| `pros`, `cons` | list of str; `cons` gets the Critic's objections that were disclosed or kept (§2c) |
| `guardian` | added by the pipeline: {`verdict`, `checks`} |
| `checks` | `checks.run` (decision #20): list of {`check`, `value`, `limit`, `status` pass/warn/fail, `reason`, `source`}, ids C1–C6, C3b, D1–D3, E, F1–F6 |

`pipeline.run` returns `strategies` (kept: Guardian not ✘) and `dropped` (with the failing rules in the trace).

## 2c. Critic → Portfolio → Guardian (`critic.add_to_trace`, decision #30)

`res["critic"]`:

| Field | Type |
|---|---|
| `objections` | ≤ 3 kept, each {`id` K1…, `strategy` (key), `claim`, `evidence` [call_id], `action`, `status`} |
| `action` | {`type`: `merge` (a, b) · `trim` (ticker, to) · `shift` (pct ≤ 0.20) · `disclose`} |
| `status` | `revised: …` · `kept, justified: the fix would break …` · `disclosed …` · `dropped: …` (code decided) |
| `tool_calls` | [{`call_id`, `tool`, `args`, `result`}] in order, ≤ 6 |
| `source`, `model`, `note`, `facts_hash` | `bedrock` · `cache (demo)` · `cache (critic)` · `mock`; as §2b |

Strategies gain `baskets` {`growth`, `defensive`} (what the split was computed from) and `cons` (objections not
fixed). A revised strategy replaces the original in `res["strategies"]`, recomputed by `portfolio.assemble`.

## 2b. Explainer → Guardian → client (`explainer.explain` / `explainer.add_to_trace`)

| Field | Type |
|---|---|
| `text` | str, the client text (ends with `personas.DISCLAIMER`) |
| `raw` | str or null: the agent's text with `{nK}` ids before code fills in the values (null for the template) |
| `source` | `bedrock` · `cache (demo)` · `cache (explainer)` · `template` |
| `model` | Bedrock model id, or "" for the template |
| `check_calls` | int, how many times the agent ran `check_text` on its draft |
| `checks`, `verdict` | Guardian G11–G13 on the final text (all strategies at once) |
| `facts_hash` | key of the cache entry (changes with any number) |
| `note` | why the template was used, if it was |

`add_to_trace` stores it in `res["explanation"]` and appends two trace steps (Explainer → Guardian, Guardian → Client).

## 3. Every agent → trace store

One entry per hand-off: `agent`, `to`, `timestamp`, `summary` (plain-language description of what is passed and
why, e.g. "risk level 2 (Cautious; tolerance 2, capacity 2) … Flags: request TSLA 25%: above the cap 8%"), `output`,
`checks`, `sources`. Guardian checks: `rule`, `status` (pass / warn / fail), `detail`. Code: `src/dh/agents/trace.py`.

**`res["followups"]`** (Analyst, decision #35): list of {`question`, `answer` (with the disclaimer), `status`
(`valid` or `replaced: …`), `evidence` [call_ids], `tool_calls` [{`call_id`, `tool`, `args`, `result`}], `source`,
`model`, `note`, `facts_hash`}. Two trace steps per question: Client → Analyst, Analyst → Client.


## Held-to-maturity fixed-income path (2026-11-15)

Optional profile fields: `investment_mode` (`market` default, `fixed_rate`),
`fixed_rate_pct` (requested annual rate, 0–100), `fixed_income_market` (`both`, `canada`, `us`).
A fixed-rate request routes to `dh.agents.fixed_income`, before market history/portfolio simulation.
Result adds `fixed_income_scenario` containing status (`quote_required` or `unavailable`),
requested rate/term, selected sourced instrument when available, allocation, dated references,
pricing assumptions and deterministic payment schedule. Currency is explicit; CAD capital is
converted using dated USD/CAD for a USD security. USD cashflows carry FX risk.
`strategies` is empty because these contractual cashflows are not bond-fund backtests;
`limits.scenario_only` is true and verdict is `warn`, never a zero-loss certification.
The explainer uses deterministic headings/text (`source=fixed_rate`), with no Bedrock call or
claim that an LLM/Guardian approved a guarantee. The sidecar is persisted in run traces.
See `data/README.md` for catalogue validation, coverage and S3 keys.
