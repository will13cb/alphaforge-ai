# univers_produit — Joud (touches Will's files: see "Lanes")

**Goal:** let every existing tool (data, metrics, toolkit, market tools, checks C–F, Guardian, agents) analyse 30
foreign ordinary shares (15 Europe, 15 Asia) in CAD and in local currency, without weakening any existing rule, and
so that a new market or product class is a data row, not new code.
**Status:** PLAN ONLY, awaiting approval. No code changed on this branch yet (branched from `main` @ `674a016`).

Facts below marked **[measured]** were computed on Sun Nov 15 from Yahoo Finance (yfinance, prices to 2026-11-13)
and Bank of Canada Valet (FX), with a scratch script (not committed: prices can't go in git, decision #11).

---

## 1. What the current architecture assumes (and where it breaks)

| Area | File (lane) | Today | With foreign shares |
|---|---|---|---|
| Fetching | `scripts/get-data.sh`, `scripts/build_long_data.py`, official `build_dataset.py` (Joud) | 31 Yahoo tickers, USD/CAD only (BoC, FRED before) | Reuse the same path (yfinance + BoC + FRED). Needs 9 more currencies |
| Universe / identification | `data/raw/assets_universe.csv` (organizers), `src/dh/data.py:61` | Organizers' CSV, columns `market, currency, sector` | Add our own reference file (metadata only, committed): exchange, country, region, quote currency, price scale, timezone |
| Asset groups | `src/dh/agents/rules.py:81-104` (Will) | `STOCKS`, `EQUITY_ETFS`, `BOND_ETFS`, `DEFENSIVE`, `DIVIDEND_PAYERS`, `EXCLUSIONS["fossil_fuels"]` hard-coded | A new share is in no group → silently not a "stock" for C1/G4, not excluded for a fossil-fuel exclusion. **Must be derived from universe columns** |
| Country | `market.country_of` (`market.py:95`), `checks.py:94`, `diversification.py:70` | Guessed from suffix: `.TO` → Canada, else United States | `AZN.L` would be "United States". Read country/currency from the universe instead |
| Currency conversion | `data.py:98-106` | Only USD↔CAD, one file `fx_usdcad_daily.csv` | Generalise to any currency with a CAD rate; handle quotes in minor units (GBp) |
| Calendar | `data.py:_panel` + `metrics.periods_per_year` | One weekday calendar, holidays forward-filled as 0% days (#12, #15) | Each market has its own holidays → more artificial 0% days; Asian closes happen ~13 h before New York |
| Correlations | `market.correlations`, `diversification.corr_matrix`, C6 (`checks.py`), toolkit `correlation_report` | Daily, except crypto pairs weekly (#34) | **Daily correlations across time zones are biased low** (see §4.B) |
| Quality | toolkit `data_quality`, organizers' `data_quality_warnings.txt` | Generic checks | Add market-specific checks (minor units, stale vs tick size, history class, FX coverage) |
| Agent tools | `market.AGENT_TOOLS`, `_check_tickers` (`market.py:330`) | Refuse anything outside the 31 | Accept the enlarged universe automatically; error text no longer says "starter" |
| Proposals | `portfolio.STRATEGY_DEFS` (Will) | Fixed baskets of the 31 | **Unchanged in phase 1** (decision S3 below) |
| Backtests / risk | toolkit: `bt_mix`, `walk_forward`, `probability_backtest_overfitting`, `bootstrap_paths`, `ledoit_wolf_cov`, `evt_var_es`, `jarque_bera`, `variance_ratio`, `ljung_box`, `deflated_sharpe` | Work on any return frame | Reused as is; inputs must be synchronised first (§4) |

**Reused without change:** `metrics.py` (return, vol, Sharpe, drawdown, `risk_contributions`, `look_through`),
almost all of `quant_toolkit.py` (`convert_currency` already does (1+r_local)(1+r_fx)−1; `resample_returns` already
compounds to weekly), Profiler, Guardian G1–G17 logic, per-asset caps (#24: computed from each asset's own worst drop,
so they adapt by themselves), tracestore, Explainer/G12.

## 2. Proposed universe: 30 ordinary shares [measured]

Screen applied: ordinary share on its home exchange (no ADR/GDR/ETF), market cap ≥ 10 bn CAD, average daily traded
value (last 12 months) ≥ 5 M CAD, history ≥ 10 years target / 5 years minimum, one line per company, sectors and
countries spread. Market cap = Yahoo `fast_info` (point in time = today, see bias §5), converted with the latest BoC rate.

| Ticker (Yahoo) | Company | Country | Exchange | Quote ccy | Sector (GICS-like, to verify) | First price | Cap bn CAD | ADV M CAD | 0%-days % |
|---|---|---|---|---|---|---|---|---|---|
| AZN.L | AstraZeneca | UK | LSE | GBp (pence) | Health Care | 2016-01-04 | 409 | 675 | 0.5 |
| SHEL.L | Shell | UK | LSE | GBp | Energy | 2016-01-04 | 397 | 655 | 0.4 |
| HSBA.L | HSBC Holdings | UK | LSE | GBp | Financials | 2016-01-04 | 437 | 585 | 0.7 |
| ULVR.L | Unilever | UK | LSE | GBp | Consumer Staples | 2016-01-04 | 203 | 399 | 0.8 |
| RIO.L | Rio Tinto | UK | LSE | GBp | Materials | 2016-01-04 | 193 | 378 | 0.5 |
| MC.PA | LVMH | France | Euronext Paris | EUR | Consumer Discretionary | 2016-01-04 | 311 | 401 | 0.6 |
| AIR.PA | Airbus | France | Euronext Paris | EUR | Industrials | 2016-01-04 | 257 | 348 | 0.5 |
| SAP.DE | SAP | Germany | XETRA | EUR | Information Technology | 2016-01-04 | 388 | 692 | 0.8 |
| SIE.DE | Siemens | Germany | XETRA | EUR | Industrials | 2016-01-04 | 336 | 452 | 0.8 |
| ALV.DE | Allianz | Germany | XETRA | EUR | Financials | 2016-01-04 | 281 | 353 | 1.5 |
| DTE.DE | Deutsche Telekom | Germany | XETRA | EUR | Communication Services | 2016-01-04 | 200 | 309 | 1.8 |
| ASML.AS | ASML | Netherlands | Euronext Amsterdam | EUR | Information Technology | 2016-01-04 | 812 | 1392 | 0.5 |
| NOVN.SW | Novartis | Switzerland | SIX | CHF | Health Care | 2016-01-04 | 436 | 625 | 1.3 |
| NOVO-B.CO | Novo Nordisk (B) | Denmark | Nasdaq Copenhagen | DKK | Health Care | 2016-01-04 | 259 | 382 | 0.8 |
| IBE.MC | Iberdrola | Spain | BME | EUR | Utilities | 2016-01-04 | 248 | 319 | 1.7 |
| 7203.T | Toyota Motor | Japan | TSE | JPY | Consumer Discretionary | 2016-01-04 | 357 | 718 | 1.6 |
| 6758.T | Sony Group | Japan | TSE | JPY | Consumer Discretionary | 2016-01-04 | 226 | 604 | 1.6 |
| 8306.T | Mitsubishi UFJ | Japan | TSE | JPY | Financials | 2016-01-04 | 349 | 1142 | 1.6 |
| 8035.T | Tokyo Electron | Japan | TSE | JPY | Information Technology | 2016-01-04 | 191 | 1577 | 1.3 |
| 4502.T | Takeda | Japan | TSE | JPY | Health Care | 2016-01-04 | 99 | 220 | 1.9 |
| 6501.T | Hitachi | Japan | TSE | JPY | Industrials | 2016-01-04 | 196 | 597 | 1.6 |
| 0700.HK | Tencent | China (HK listing) | HKEX | HKD | Communication Services | 2016-01-04 | 627 | 2268 | 1.7 |
| 1299.HK | AIA Group | Hong Kong | HKEX | HKD | Financials | 2016-01-04 | 144 | 415 | 2.3 |
| 0883.HK | CNOOC | China (HK listing) | HKEX | HKD | Energy | 2016-01-04 | 195 | 435 | 3.5 |
| 005930.KS | Samsung Electronics | South Korea | KRX | KRW | Information Technology | 2016-01-04 | 1390 | 6025 | 4.7 |
| 005380.KS | Hyundai Motor | South Korea | KRX | KRW | Consumer Discretionary | 2016-01-04 | 74 | 708 | 8.1 |
| 2330.TW | TSMC | Taiwan | TWSE | TWD | Information Technology | 2016-01-04 | 2624 | 2794 | 7.5 |
| RELIANCE.NS | Reliance Industries | India | NSE | INR | Energy | 2016-01-01 | 272 | 300 | 0.2 |
| HDFCBANK.NS | HDFC Bank | India | NSE | INR | Financials | 2016-01-01 | 186 | 409 | 0.2 |
| D05.SI | DBS Group | Singapore | SGX | SGD | Financials | 2016-01-04 | 219 | 342 | 2.2 |

- **Spread:** 15 Europe / 15 Asia; 14 countries (largest: Japan 6 = 20%, UK 5 = 17%); 10 of 11 sectors (largest:
  Financials 6 = 20%, IT 5 = 17%; no Real Estate). 10 quote currencies (GBp, EUR, CHF, DKK, JPY, HKD, KRW, TWD, INR, SGD), GBp in pence (minor unit).
- **Thresholds don't bind:** smallest cap 74 bn CAD (Hyundai), smallest ADV 220 M CAD (Takeda). Your 10 bn / 5 M
  filters keep their value as gates for future additions.
- **All 30 have ≥ 10 years** (first price ≤ 2016-01-04). Short-history class is therefore empty in this list.
- **Screened out [measured]:** `ROG.SW` (Roche's liquid non-voting line) **not found on Yahoo**; `RO.SW` (bearer)
  exists but trades only ~18 M CAD/day, so Roche is out. `9988.HK` (Alibaba HK) starts 2019-11-26 (7 years: kept as
  the test case for the short-history class, not in the 30). Also screened and left as alternates: BP.L, GSK.L,
  LSEG.L, TTE.PA, SAN.PA, OR.PA, BNP.PA, SU.PA, NESN.SW, UBSG.SW, SAN.MC, ENEL.MI, ISP.MI, 6861.T, 9984.T, 9432.T,
  8058.T, 0941.HK, 000660.KS, 2317.TW, INFY.NS.
- **Overlap with the starter 31:** HSBC is also listed in HK (0005.HK, not taken). Shell/CNOOC/Reliance add to the
  energy names ENB/CNQ/XOM (fossil-fuel tagging = decision S5).

## 3. Data providers (decision 7: compare, subscribe to nothing)

| Provider | Europe/Asia coverage | History | Reliability / quality | Cost | Reachable from here |
|---|---|---|---|---|---|
| **Yahoo Finance (yfinance)** | All 30 (suffixes .L .PA .DE .AS .SW .CO .MC .T .HK .KS .TW .NS .SI) | ≥ 10 y for all 30 [measured] | Unofficial API; known traps: GBp quotes **and GBp market caps** [measured: caps ×100], missing lines (ROG.SW) [measured], occasional bad splits | Free; terms forbid redistribution (#11) | **Yes** via yfinance (raw HTTP gets 429) |
| Stooq | Broad (UK, DE, JP, HK…) | Long | Good for cross-checks; adjustment method to verify | Free CSV | **No** (blocked by the network policy) |
| EOD Historical Data | 70+ exchanges | 30+ y | Commercial, adjusted series | Paid (free tier ~20 calls/day) — to verify | Not tested |
| Alpha Vantage | Partial international | Long | Adjusted daily now premium (to verify) | Free tier very small | Not tested |
| Twelve Data / FMP | International mostly on paid plans | Varies | Commercial | Paid for this use | Not tested |
| Bloomberg / Refinitiv | Complete | Complete | Reference quality, point-in-time caps | Institutional (school terminal?) | No |
| **Bank of Canada Valet** (FX) | 26 currencies incl. GBP EUR CHF JPY HKD KRW TWD INR SGD; **no DKK** | Current series **from 2017-01-03** [measured] | Official | Free, open terms | **Yes** |
| **FRED H.10** (FX) | USD crosses incl. DKK, JPY, GBP, EUR… | Decades | Official (noon NY rates) | Free | **Yes** |

**Recommendation (technical):** Yahoo as primary (same source and code path as the organizers' data, so the 61
assets stay comparable); FX from BoC, with FRED crosses via USD for the days before 2017-01-03 and for DKK (same
pattern as `build_long_data.py` for USD/CAD, decision #31). A paid provider only for a later cross-check, with your OK.

## 4. Market specifics: what the code will do

**A. Currencies.** One FX table `data/raw/fx_daily.csv` (date, currency, CAD per unit, source). Quotes in minor units
are scaled by a per-exchange `price_scale` (GBp → GBP × 0.01). Every analysis gets both series:
`returns(..., currency="local")` and the default CAD. Decomposition per asset and per portfolio:
r_CAD = r_local + r_fx + r_local·r_fx; FX contribution to portfolio variance by Euler decomposition on the stacked
local and FX components (covariance-based, same family as `metrics.risk_contributions`). Reference case unhedged
(your decision 6). Conversion cost = a parameter `fx_cost_bps` applied only when a backtest trades (value: S6).
Forward-fill FX only forward (never back-fill, as today).

**B. Calendars and time zones [measured].** Asian closes come ~13 h before New York's on the same date, so daily
returns are not synchronous. Correlation with SPY, 2016-11 → 2026-11:

| | daily | SPY yesterday vs stock today | weekly |
|---|---|---|---|
| Toyota (7203.T) | 0.10 | 0.26 | 0.33 |
| TSMC (2330.TW) | 0.11 | 0.38 | 0.42 |
| Tencent (0700.HK) | 0.13 | 0.16 | 0.22 |
| SAP (SAP.DE) | 0.35 | 0.12 | 0.53 |
| AstraZeneca (AZN.L) | 0.10 | 0.06 | 0.13 |

Daily correlations understate co-movement 3–4× for Asia, so C6, risk contributions and any covariance would show
diversification that isn't there. **Rule:** any cross-asset statistic (correlation, covariance, risk contribution,
portfolio volatility) on a set whose sessions don't overlap uses weekly (Friday-close, compounded) returns; single-asset
statistics use each asset's own trading days (no artificial 0% holidays). The starter-only computations stay as today
(regression test) unless you decide otherwise (S8).

**C. Data quality.** New `dh.validation` (wraps toolkit `data_quality`) per asset: history class (≥ 10 y / 5–10 y /
< 5 y), first/last date, gaps vs the exchange's own calendar, minor-unit detection (price level ×100 jump vs FX),
stale prices = 0% return **and** zero volume (TSMC has 7.5% 0%-days but with volume: tick size, not stale
[measured]), outliers flagged and cross-checked with corporate actions, **never deleted** (Rolls-Royce +43.8% on
2020-11-09 is real [measured]), FX coverage for every price date, Close vs Adj Close ratio jumps (dividends/splits).

**D. Comparability.** Same annualisation rule (#12: observed rows per year, per series), same CAD base, same window
for any comparison (common window stated in every output), weekly for cross-market dependence, local vs CAD side by side.

## 5. Methods: compatibility check and bias tests

| Method (existing) | Valid as is? | Adaptation |
|---|---|---|
| Return, vol, Sharpe, drawdown | Yes per asset, on its own calendar | Own-calendar option |
| Correlation, covariance, Ledoit-Wolf | **No on daily mixed sessions** | Weekly; report condition number (N = 61 vs T ≈ 520 weeks over 10 y) |
| Normality (Jarque-Bera), skew, kurtosis | Yes | Report on daily local and CAD; FX changes the tails |
| Stationarity (variance ratio, Ljung-Box) | Yes; no ADF in the project | ADF needs `statsmodels` (dependency: S9) |
| Extreme risk (CVaR, EVT, worst 12 months, 2022 stress) | Yes | Window stated; add each market's own crash dates (e.g. 2020-03) |
| Optimisers (Markowitz etc.) | Kept off the demo (#37) | Research only, Ledoit-Wolf, weekly |
| Backtests (`bt_mix`, `walk_forward`, PBO) | Yes | Rebalance on dates all markets traded; FX cost parameter |
| Predictive models | **Not in the project** (#9: no return forecasts) | See S4 |

**Bias tests (each one a test or an experiment logged in `results.csv`):**
- Selection/survivorship: the 30 are today's large caps. Compare their equal-weight 10-year return with each market's
  index (^FTSE, ^FCHI, ^GDAXI, ^N225, ^HSI, ^KS11, ^TWII, ^NSEI, ^STI) as benchmarks only → estimated survivorship premium.
- Time zones: synthetic lagged-factor series (daily corr must come out low, weekly must recover the true value) + the measured table above.
- Missing data: random holes and a closed week (Golden Week, Lunar New Year) → no 0% returns invented on own-calendar stats.
- Currency: identity (1+r_CAD) = (1+r_local)(1+r_fx) to 1e-12; a CAD asset's FX component is exactly 0; GBp scaled.
- Leakage: FX and prices only forward-filled; selection date logged; walk-forward splits only past data.
- Overfitting: PBO and deflated Sharpe on any strategy comparison; no threshold tuned on the same window.
- Concentration: country / sector / currency shares of the 61-asset universe and of any portfolio (C2, C3 unchanged).
- Different history lengths: pairwise statistics on the common window only, with the window printed.
- Bad inputs: strings in prices, None/NaN, wrong date format, unknown currency (explicit error), < 5 y history (separate class), negative prices.

## 6. Files

**New**
- `reference/universe_international.csv`: our metadata only (ticker, name, country, region, exchange, quote_ccy,
  price_scale, sector, asset_class, tags, selection_date, source). Committed: no prices.
- `src/dh/markets.py`: exchange registry (code → country, region, currency, price_scale, timezone, Yahoo suffix).
  A new market = one row.
- `src/dh/validation.py`: checks of §4.C, one report shape {asset, check, value, limit, status, reason, source}
  (same shape as `checks.py`).
- `src/dh/currency.py`: FX table loader, local ↔ CAD, decomposition, FX contribution to risk.
- `scripts/build_international.py` + `make data-intl`: prices (yfinance), FX (BoC + FRED), quality report into `data/raw/`.
- `experiments/data/intl/`: the bias tests and the research report; numbers through `log_run`.
- `tests/test_international.py`, `tests/test_validation.py`, `tests/test_currency.py`.

**Adapted** (behaviour on the starter 31 must stay identical: regression tests)
- `harness.toml` (shared): `[data] universes = ["starter"]` (default) or `["starter", "international"]`; `corr_freq_cross_market = "W-FRI"`; `fx_cost_bps`.
- `src/dh/data.py` (Joud): merge universes; any currency; `currency="local"`; own-calendar option.
- `src/dh/agents/market.py` (Joud): country/currency from the universe, registry instead of `COUNTRY_OF_MARKET`, generic `_check_tickers` message, tool `fx_decomposition`.
- `src/dh/agents/rules.py` (Will): asset groups derived from universe columns; a test asserts they equal today's sets on the starter.
- `src/dh/agents/checks.py`, `diversification.py` (Will): country/currency from the universe; weekly correlations across sessions. Thresholds unchanged.

**Not touched in phase 1:** `portfolio.py` baskets, Profiler, Guardian thresholds, Explainer, Critic, Analyst, apps,
demo caches, deliverables.

## 7. Decisions

**I can take them (technical):** file layout and registry; yfinance + BoC + FRED; GBp handling; weekly Friday-close for
cross-market statistics; flags never delete data; no new dependency except if S9 is approved; tests listed above.

**Need your validation (justified changes):**
- V1. Own-calendar single-asset statistics for the new assets (avoids fake 0% days; the starter stays as is).
- V2. Asset groups in `rules.py` derived from data (same result on the starter, proven by a test).
- V3. Market indices used as benchmarks only (not investable, not in the 30) for the survivorship test.

**Strategic (your approval required before I start):**
- **S1. Timing vs the 23:59 freeze.** Devpost: "no change after 23:59" on the repo. Options: (a) phase 1 on this
  branch before 23:59, (b) push nothing after 23:59 and continue locally / in a separate repository until judging
  ends (finals Nov 20). My recommendation: (b) unless only this plan is pushed today.
- **S2. The 30 names** above (swap list in §2). Open points: China/HK names (Tencent, CNOOC) carry controversy and US
  list history (to verify; matters for Mateo); India/Taiwan/Korea are hard to buy directly for a Canadian (your point 11,
  studied separately); Australia counted as Asia or not (excluded for now).
- **S3. Research only in phase 1:** the new shares are visible to the market tools, Analyst and backtests, but not in the
  client strategies (`STRATEGY_DEFS`) nor in the demo. Including them in proposals = phase 2.
- **S4. "Trading" and predictive models:** the project is decision support, simulation only, no return forecasts
  (#9, brief). I propose risk models only (vol, tails, dependence), no return prediction.
- **S5. Fossil-fuel / ESG tags** for the new names (Shell, CNOOC, Reliance; utilities with gas plants?).
- **S6. FX conversion cost** default (0 bps in statistics, cost only in backtests; value to choose) and **dividend
  withholding tax** (adj_close = gross dividends; a haircut or a stated limit).
- **S7. Lanes:** `rules.py`, `checks.py`, `diversification.py` are Will's; `harness.toml` is shared → Will's OK.
- **S8. Daily vs weekly for the starter too?** The same time-zone bias exists for crypto vs TSX in a smaller form; kept as today unless you decide.
- **S9. Add `statsmodels`** for ADF / KPSS stationarity tests.

## 8. Order of work (after approval)

1. Registry + reference CSV + `make data-intl` + validation report (no change to existing behaviour).
2. `data.py` multi-currency + local/CAD + regression tests on the starter.
3. Country/currency from the universe in market/checks/diversification; groups from data in `rules.py`.
4. Weekly cross-market dependence; FX decomposition tool.
5. Bias experiments + research report (`experiments/data/intl/README.md`), numbers in `results.csv`.

## Done
- Architecture review, provider reachability, 54-candidate screen, time-zone measurement (this document).

## In progress / next
- Waiting for S1–S9 and V1–V3.

## Decisions made here
- None yet (proposals above; when approved they go to `notes/decisions.md`).

## Contract changes
- None yet. Planned: universe columns `country, region, quote_ccy, price_scale, tags` (additive).

## How to check it
- Plan only. After step 1: `make data-intl && python -m dh check` and `pytest tests/test_validation.py`.

## Open questions / blocked on
- S1 (freeze) before any push of code.
