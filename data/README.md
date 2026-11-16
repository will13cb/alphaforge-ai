Raw challenge data lives in `data/raw/` and is **never committed**.
Get it with `scripts/get-data.sh` (from S3) or drop the files here by hand,
then record the file names, row counts, and date ranges under "Verified live" in CONTEXT.md.

## ETF holdings (extra public data, for look-through)

Raw issuer files go in `data/raw/holdings/` (keep the original filenames). `scripts/build_holdings.py` turns them into
`data/raw/etf_holdings.csv` (columns: etf, holding, name, weight as a fraction, sector, country, as_of, source) and
prints sanity checks. Code: `src/dh/holdings.py`. Bond ETFs and GLD are skipped because they don't hold companies.

| ETF | Issuer | Page / file | Downloaded | Status |
|---|---|---|---|---|
| SPY | State Street | https://www.ssga.com/us/en/intermediary/etfs/spdr-sp-500-etf-trust-spy → "Download All Holdings: Daily" = https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx (`holdings-daily-us-en-spy.xlsx`) | 2026-11-14, script | as of 2026-11-12, 503 holdings, sums to 99.97% |
| QQQ | Invesco | https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=QQQ | — | **download by hand**: holdings load with JavaScript, no static link |
| ESGV | Vanguard | https://investor.vanguard.com/investment-products/etfs/profile/esgv | — | **download by hand**: the page is a JavaScript shell |
| XIU | BlackRock iShares Canada | https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf ("Detailed Holdings and Analytics" / download) | — | **download by hand**: holdings load with JavaScript |

Processing: weights converted from % to fractions; XIU tickers get `.TO` (class shares `BBD.B` → `BBD-B.TO`, Yahoo
spelling); GOOG + GOOGL merged into GOOGL (same company); cash, futures and FX lines kept as one `other` row per ETF
and ignored by look-through; all holdings kept, not only our 31 assets. SPY's file has no sector (shown as "-") and no
country column, so those fields are empty for SPY.

Limits: a **snapshot of current holdings** (as_of date). Used only to measure what a portfolio is exposed to today,
**never to rebuild past returns** (that would be look-ahead). Weights move daily with prices and rebalancing.

Terms of use: these are files the issuers publish on their public fund pages. We use them for a non-commercial
educational prototype, cite the issuer and date, and don't redistribute the raw files (not in git). No terms-of-use
page was found on the SPY fund page; check the issuer's site terms before any wider use.

## Longer history (optional, decision #31)

`make data-long` (or `make data-long START=2007-01-02`) rebuilds the **same 31 assets and the same 6 files** from
2004-11-18 instead of 2021-11-12, by running the organizers' `Datathon2026Infos/alphaforge_starter/build_dataset.py`
unchanged with an earlier start (`scripts/build_long_data.py`). Needs internet and `yfinance`; run it on a laptop
(the cloud session can't reach Yahoo, FRED or the Bank of Canada). Output in `data/raw/` (never committed), plus
`BUILD_INFO.txt` with the window and sources.

| Item | Source | Note |
|---|---|---|
| Prices, dividends, splits | Yahoo Finance (yfinance), adj_close | Assets start when they listed: ZST.TO 2011, SHOP.TO 2015, BTC-USD 2014, ETH-USD 2017, ESGV 2018 (check `data_quality_warnings.txt`) |
| USD/CAD | Bank of Canada FXUSDCAD; **FRED DEXCAUS** (Federal Reserve H.10, CAD per USD) before the Bank of Canada series starts | Same unit; the script prints where the splice is |
| Rates, CPI | Bank of Canada Valet, FRED | As far back as each series goes |

How the code treats it (`dh.data`): returns are NaN before an asset's first price (never 0%); a strategy's numbers use
only days when every asset it holds traded; stand-ins **only before the first price**, from `harness.toml
[data.proxies]`: ZST.TO ← Bank of Canada overnight rate (V39079) accrued daily, ESGV ← SPY (listed in the
assumptions of every run). FX is carried forward, never backward. `harness.toml start` can cut the window.

Limits: survivorship bias is unchanged (2026's names over a longer past, which flatters past returns even more);
2008 enters the worst drops, so company caps and splits get stricter; the cached Explainer texts must be re-saved
(`make explain P=robert SAVE=1`) after the rebuild. Terms: Yahoo forbids redistribution (decision #11), Bank of Canada
https://www.bankofcanada.ca/terms/, FRED https://fred.stlouisfed.org/legal/.

## March 2020 replay (decision #50)

`make data-stress` writes `data/raw_stress/` (never committed): the same 31 assets and 6 files, 2019-12-02 →
2020-06-30, built by the organizers' `build_dataset.py` through `scripts/build_long_data.py` (Yahoo Finance adj_close,
Bank of Canada FXUSDCAD, Bank of Canada Valet and FRED macro). Used only by `dh.stress` to replay a strategy through
the COVID crash (2020-02-19 → 2020-03-23); every other number stays on `data/raw/` (2021-2026). On a host,
`AF_AUTO_DATA=1` builds it at the first results page. Known data note: ETH-USD −42% on 2020-03-12 (real, "Black
Thursday"). Terms as for the longer history above.

## Extra products listed in Canada or the U.S. (optional, branch produit_cadusa)

`make data-products` writes `data/raw/products_cadusa/` for the 60 products of `src/dh/product_catalogue.py`
(ETFs, stocks, gold, silver; CAD or USD only). Then `harness.toml [data] extra = ["cadusa"]` loads them next to the
starter's 31. Off by default.

| | |
|---|---|
| Source | Yahoo Finance via yfinance, with the organizers' own `build_prices` (adj_close, dividends, splits) |
| Date | ticker, currency and exchange checked 2026-11-15; prices 2021-11-12..2026-11-12 by default (`START=` for longer) |
| Processing | catalogue checked before download; `quality_report.csv` after (history, coverage, one-day moves > 40%, stale quotes, gaps); a failed series is left out and listed |
| Limits | unofficial API; adjusted history can be revised; names, sectors and exposure labels are the team's; no ETF holdings yet (look-through = lower bound) |
| Licence | Yahoo: personal use, no redistribution (nothing goes in git, decision #11) |

## Company statements for dividends (optional, branch produit_cadusa)

`make data-fundamentals` writes `data/raw/fundamentals/` for every stock of the loaded universe: per fiscal year, net
income to common shareholders, dividends paid to common shareholders, free and operating cash flow.

| | |
|---|---|
| Source | Yahoo Finance via yfinance (`income_stmt`, `cashflow`, `info` for the statements' currency) |
| Date | downloaded 2026-11-15; the latest 4-5 fiscal years as published that day |
| Processing | for each year the first filled label (common dividends, else all cash dividends); dividends stored positive; no dividend row = 0 |
| Limits | snapshot, not point-in-time (never in a backtest); Yahoo's labels and restatements; no FFO/AFFO for REITs; Yahoo's own `payoutRatio` is not used (unreliable) |
| Licence | Yahoo: personal use, no redistribution |

**To S3 (for the hosted app, research mode):** after `make data-products` and `make data-fundamentals`, `make data-up`
also uploads `products_cadusa/` and `fundamentals/` to `s3://$S3_BUCKET/raw/`. A hosted copy fetches them at start
only when its `harness.toml` has `extra = ["cadusa"]` (statements optional); with `extra = []` it fetches the starter
files only, as before.

## ETF fees (existing-portfolio review, decision #44)

`src/dh/fees.json`, written by `scripts/build_fees.py`: Yahoo Finance `netExpenseRatio` for our ETFs and every stand-in
fund (`dh.standins`), fetched 2026-11-15. It is Yahoo's copy of the issuer's figure: check the fund's own page before
quoting one in a deliverable. Shown as "fund fees: about X $ a year"; never taken out of the returns (ETF adjusted
prices are already net of the fund's own fees). A fund without a figure is listed as unknown, never assumed free.

On a host without S3, `bootstrap.ensure_holdings()` downloads SPY's issuer file (State Street, direct .xlsx) and
builds `etf_holdings.csv` at start (AF_AUTO_DATA=1). QQQ, ESGV and XIU.TO come from web pages: saved by hand only.


## Canada/U.S. fixed income: held-to-maturity catalogue

Run `make data-fixed-income` (or `python scripts/build_fixed_income.py`). This builds
`data/raw/fixed_income/{instruments.csv,reference_snapshot.json,sources_metadata.csv,quality_report.csv}`.
Upload all four files to `s3://YOUR_BUCKET/raw/fixed_income/`; `make data-up` includes this folder.
On the hosted app, `S3_BUCKET`, AWS read credentials and `AF_AUTO_DATA=1` enable loading it independently
of market-history files. Restart the app after replacing a catalogue; an existing local copy is reused.
Raw datasets remain outside git. No upload to AWS is performed by the builder.

The initial download includes Government of Canada nominal fixed-rate issues and U.S. nominal Treasury
notes/bonds. Bank of Canada benchmark yields are dated mid-market references; TreasuryDirect
yields are dated auction results, **not current secondary-market offers**. Neither proves inventory or an
executable price. This is not every Canadian/U.S. bond or deposit: dealer inventory, corporate, provincial,
municipal, GIC and CD offers require their own dated issuer/broker records. Public pages/API access is used
for this educational prototype; no commercial redistribution licence is asserted.

Sources (retrieval time and observation dates are saved in the generated files):
- [Bank of Canada outstanding issues](https://www.bankofcanada.ca/markets/government-securities-auctions/goc-t-bills-bonds-outstanding/)
- [Bank of Canada benchmark yields and bond terms](https://www.bankofcanada.ca/rates/interest-rates/canadian-bonds/)
- [TreasuryDirect auction query](https://www.treasurydirect.gov/auctions/auction-query/), nominal Note/Bond search API
- [Bank of Canada USD/CAD observations](https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=5)

To extend coverage, pass `--extra path/to/sourced_records.csv` (repeatable). Required columns:

| Column | Meaning |
|---|---|
| instrument_id | Unique ISIN/CUSIP or source identifier |
| issuer, country | Named issuer; country `Canada` or `United States` |
| issuer_type | `sovereign`, `provincial`, `municipal`, `corporate`, `deposit` |
| instrument_type | `bond`, `gic`, `cd`, `bill`, `strip`, `floating_rate`, `inflation_linked` |
| currency | `CAD` or `USD` |
| maturity | ISO date YYYY-MM-DD |
| coupon_pct | Annual coupon/deposit rate in percentage points |
| coupon_frequency | 1, 2, 4 or 12 for fixed-coupon bonds |
| terms_source, terms_as_of | HTTPS source URL and ISO date |

Optional `offer_price` is a positive **clean price per 100 face value**, never a dollar investment amount.
`offer_yield_pct` is a dated offer yield. Supplying either requires `quote_source` (HTTPS) and `quote_as_of`
(ISO date). `benchmark_yield_pct` requires `yield_as_of`; `auction_yield_pct` remains historical reference.
`available_to_buy=false` and `callable=true` records are excluded from held-to-maturity matching.
GIC/CD records require `cashflow_type=annual_payout` or `compound_at_maturity` plus a dated HTTPS offer source;
issuer repayment is assumed and CDIC/FDIC coverage is not certified. Zero-loss requests only match sovereigns.

Bills, strips, inflation-linked and floating-rate records can be catalogued but are not selected by this
fixed-coupon cashflow model. Invalid/duplicate rows are excluded and listed in `quality_report.csv`.
The app prefers CAD, matches maturity near the horizon, and shows a sourced income candidate or explains
that no verified match exists in the loaded catalogue. A coupon alone never certifies the requested return:
without a current price it uses an explicitly assumed par price plus accrued interest. Bond coupon dates
are derived backwards from maturity, using a simplified day-based accrued-interest convention; actual
broker settlement conventions, fees, taxes, minimum lots and payment calendars need a purchase quote.
Deposit schedules assume a new purchase today and use the explicitly supplied payout/compounding type.
The UI displays the exact maturity and stops cashflows there, rather than inventing a reinvestment rate.
