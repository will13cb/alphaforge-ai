# Technical doc — market data sections (draft by Joud, for Will to merge into `deliverables/`)

Sources of every statement: `notes/decisions.md` #10–#13, #15, #16, #18; `data/README.md`; the starter pack README;
`notes/audit-2026-11-15.md`. Numbers marked **[audit]** come from the audit scripts (`experiments/data/audit/`) and are
**not in `results.csv` yet** (rule 3): log them or drop them before they go in the final doc. Numbers marked
**[results.csv]** are logged (experiment `threshold-check`).

## 1. Data sources

| Data | Source | Period | Use | Licence / terms |
|---|---|---|---|---|
| Daily prices, 31 assets (`prices_daily.csv`, `adj_close`) | Yahoo Finance, via the organisers' starter pack | 2021-11-12 → 2026-11-12 | every return, risk and stress number | Yahoo terms forbid redistribution: the CSVs are **not in the repo** (#11), shared by hand, rebuilt with `make data` |
| USD/CAD (`fx_usdcad_daily.csv`) | Bank of Canada | same | conversion to CAD (base currency, `harness.toml`) | public, cited |
| Macro rates (`macro_rates.csv`) | Bank of Canada (policy rate, GoC 2y/10y, CPI), FRED (US rates, CPI, unemployment) | monthly/daily | cash reference in `required_return` | public, cited; dated by reference month, not release date (no look-ahead) |
| ETF holdings (SPY) | State Street issuer file, downloaded 2026-11-14 (as of 2026-11-12, 503 lines) | snapshot | look-through exposure only (company, sector) | issuer's public page; not redistributed; non-commercial educational use |

No ESG, news or fundamentals in the data. QQQ, ESGV and XIU holdings must be downloaded by hand (JavaScript pages).

## 2. Processing (one path: `dh.data` → `dh.metrics`)

- **Returns from `adj_close`** (dividends and splits included), converted to CAD with the same-day Bank of Canada
  rate. Conversion checked exact (SPY in CAD = USD price × rate) and no future rate is used **[audit]**.
- **One calendar for the whole universe** (weekdays; crypto weekends dropped, holidays forward-filled as 0% days),
  built before selecting tickers, so every agent and every tool call gets the same numbers (#15).
- **Annualisation with the observed rows per year** (~261), 252 only as a fallback (#12). With a fixed 252, a true
  10%/yr CAGR came out at ~9.6%, and SPY's CAGR differed between agents (14.5% alone vs 14.0% in the universe); with
  the observed frequency it is 14.5% both ways.
- **Market data is deterministic code, never an LLM** (#10, #15): the Strands agents (Critic, Analyst) call its 7
  functions as tools (`market.AGENT_TOOLS`, JSON in/out, errors returned, unknown tickers refused). They read the
  result; they cannot change it.
- **Measures:** annualised return, volatility, Sharpe, max drawdown (`dh.metrics`); historical CVaR 95% on daily
  returns, worst rolling 12 months, calendar 2022 and the 2022-01-03 → 2022-10-12 sell-off window, correlations
  (`dh.quant_toolkit`). Every rate is a fraction, so the Guardian's G12 can match each number in the text.
- **Diversification on 5 dimensions** (#18): asset classes, companies and sectors through the ETFs, currency,
  correlation. Rules C3 (sector ≤ 40%), C4 (≥ 2 classes), C6 (no pair correlated ≥ 0.95).
- **Goal outlook** (#13): block bootstrap of the strategy's own daily returns, fixed seed, shown first as `risk_only`
  (average return replaced by cash, ZST.TO), then `replay`. On 30/30/30/10 XIU/SPY/XBB/GLD, 400k CAD, 4 years:
  1% chance of loss with `replay`, 23% with `risk_only`. Leading with replay would present 2021-2026 as a forecast.

## 3. Validation of the thresholds on 2021-2026 (#13) [results.csv]

20 cases (riskiest mix each level allows, 2 defensive × 2 equity baskets):
- G7 drawdown limits hold in 90% of cases; levels 2–5 always pass.
- Level 1 (8%) fails with an equal-weight defensive basket (−9.5% / −10.5%): AGG, XBB and GLD all fell in 2022.
- G8 volatility targets hold in 50% (G8 is a warning, not a block).
- In CAD, 100% XIU/SPY lost −16% at worst: the USD gain in 2022 cushioned it.

## 4. Data audit (Nov 15) [audit]

- Holidays copied as 0% days: 1.8% of days for SPY, 27% for ZST; effect on volatility negligible (XIU 13.04% vs
  13.21% on trading days only).
- CNQ false split factor (2022-08-22): +2.78% instead of +0.60% that day; minor.
- Crypto is dated in UTC days, stocks at the New York close: BTC/SPY correlation 0.38 daily vs 0.23 weekly. Daily
  correlations involving crypto are biased; other pairs are close (XIU/SPY 0.68 / 0.67).
- Mean returns are not significant over 5 years (t ≤ 2.35 for every risky asset; TSLA, BTC, XBB not distinguishable
  from 0): one more reason never to quote a past return as a forecast.

## 5. Charts (#16)

`market_charts.py` gives five charts as `*_data()` + Altair `*_chart()`: growth of each strategy with 2022 shaded,
range of final values (`risk_only` vs `replay`), correlation heatmap, risk vs return of the 31 assets with the
historical frontier (drawn, not used to build strategies, #1), 2022 return per asset. They use the same numbers as
the trace and the Explainer (tested). PNG/HTML export: `experiments/data/export_charts.py` (figures not in git).

## 6. Limits (say them in the doc)

- **One 5-year window, one bear market (2022).** No fast crash (2020-type) or long crisis (2008-type); the bootstrap
  cannot produce a crisis worse than 2021-2026. All measured risk of the proposals comes from 2022.
- **Survivorship and selection bias:** 20 stocks chosen in 2026; equal-weight they return +21.0%/yr vs +14.5% for
  SPY **[audit]**. Worst drops used for per-company caps (#24) are biased toward winners.
- **Holdings:** only SPY loaded, a current snapshot, used for today's exposure only, never to rebuild past returns.
  Sector and country checks through other ETFs are lower bounds (said in the check).
- No fees, taxes or FX costs. Macro data used only as a reference rate. Nothing predicts future returns.
