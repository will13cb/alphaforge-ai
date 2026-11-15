# produit_cadusa — Joud

**Goal:** add products listed in Canada or the U.S. through the same data path as the starter's 31, so every existing
tool and check measures them the same way; plus company data to judge a dividend (payout, coverage by earnings).
**Status:** built and tested; merged into `main` at the user's request (Sun Nov 15, before the 23:59 freeze).
**Off by default** (`harness.toml [data] extra = []`): app, demo caches, results and deliverables unchanged.
Decision #41.

## Done
### 60 products, chosen for the simplest integration (`src/dh/product_catalogue.py`)
Rules for the cut from 181 to 60: the starter's asset classes only (no multi-asset, no new class), prices back to
2021-11-12, physically backed or equity products only (no futures funds: roll costs), no crypto ETF, no near-duplicate
of a starter asset (C6 would flag holding both: IAU/GLD 1.000, VTI/SPY, ZAG/XBB), no fossil-fuel producer (the
exclusion list stays exact), sector labels that the checks read correctly.
- **Canada-listed ETFs (16):** XEF.TO (developed ex-NA), XEC.TO (emerging), XEI.TO (high dividend), ZLB.TO (low vol),
  XESG.TO (ESG), XMA.TO, XGD.TO (materials, gold miners), XRE.TO, ZRE.TO (REITs), XUT.TO (utilities), XSB.TO (short
  bonds), XCB.TO (corporate), XRB.TO (real return), XHY.TO (high yield, CAD-hedged), PSA.TO (cash), CGL.TO (gold, CAD-hedged).
- **U.S.-listed ETFs (14):** EWJ, INDA, EWZ (Japan, India, Brazil), IWM (small caps), SCHD (dividend), USMV (low vol),
  XLV, XLP, XLI (health care, staples, industrials), COPX (copper miners), BNDX (international bonds), TIP, EMB, SLV (silver).
- **Canadian stocks (15):** NTR.TO, ABX.TO, AEM.TO, FNV.TO, WPM.TO, BCE.TO, T.TO, SLF.TO, IFC.TO, CP.TO, WCN.TO, L.TO,
  DOL.TO, GIB-A.TO, CAR-UN.TO.
- **U.S. stocks (15):** UNH, LLY, ABBV, BRK-B, V, KO, PEP, WMT, COST, HD, MCD, CAT, NEE, PLD, LIN.
- Real download (2021-11-12..2026-11-12): **60/60 ok** in the quality report.

### Errors and inconsistencies found while building it, and fixed
| Found | Fix |
|---|---|
| A new ETF was class "other" in `diversification.report` (XEF.TO), in no group for C1/C5/G4/defensive floor | `rules.py` adds the catalogue to its groups when `extra` is set, derived by `products.asset_groups` (= rules.py's sets on the starter, tested); new group `COMMODITIES` (SLV), empty for the starter |
| C2 counted XEF.TO as Canada (country of listing) | `market.exposures()`: where the holdings are (catalogue `exposure`), else listing; C2's text says which basis it used |
| Currency split counted XEF.TO as CAD, a CAD-hedged ETF as foreign | `diversification.currency_of()`: catalogue `currency_exposure` (CAD / USD / Other), else listing; C2 uses the same function (it had its own `.TO` rule) |
| Labels like "Dividend (U.S.)" or "Real Estate (Canada REITs)" would count as separate sectors in C3 | Sector convention, enforced by `validate_catalogue`: GICS sector for stocks and sector ETFs; "Broad market / Bonds / Gold / Commodities (...)" otherwise ("Commodities" added to the labels C3 skips) |
| A currency other than CAD/USD was silently left unconverted (read as CAD) | `dh.data` raises an explicit error |
| Duplicate dates crashed the quality report instead of being reported | Fixed (test) |
| A new research tool would have changed the Critic's tool count quoted in the deliverables (11) | `market.agent_tools()`: research tools only when `extra` is set |

### Dividends: payout ratio and coverage by earnings (`src/dh/fundamentals.py`, `scripts/build_fundamentals.py`)
- `make data-fundamentals` → `data/raw/fundamentals/` (annual.csv, info.csv, sources_metadata.csv): per fiscal year,
  net income to common shareholders, dividends paid to common shareholders, free and operating cash flow, in the
  statements' currency (Yahoo Finance via yfinance). 50/50 stocks (starter 20 + catalogue 30) complete on 2026-11-15.
- `fundamentals.dividend_facts(ticker)` and the agent tool `market.dividend_facts([...])`:
  status covered / thin / not covered / loss / no dividend / fund / no data, with the reason; payout = dividends paid /
  net income (last fiscal year and last 3 together); earnings and free-cash-flow coverage; dividends per share over
  12 months, yield, yearly dividends, growth, cuts, special dividends (from our own corporate_actions + prices);
  sector caveats (REITs: FFO/AFFO not available; utilities; no FCF for banks/insurers); currency note when statements
  and shares differ (SHOP.TO, ATD.TO, WCN.TO report in USD).
- Found and fixed while building it:
  - Yahoo's `payoutRatio` is unreliable (152.08 for CAR-UN.TO): ratios computed from the statements only.
  - "Common Stock Dividend Paid" kept but empty for recent years (L.TO, V → "no data"): labels taken year by year.
  - Special dividends (COST 15 USD in Dec 2023) and monthly ex-date timing showed false cuts: cuts and growth use each
    year's last regular payment; specials listed apart.
- **Results (real data, last fiscal year):** not covered by earnings: ENB.TO 116%, T.TO 146%, ABBV 279%, PLD 113% and
  CAR-UN.TO 121% (REITs: caveat); thin: PEP 93%; cuts: BCE.TO 2025, ABX.TO 2023; covered: RY.TO 44%, TD.TO 38%,
  FTS.TO 46%, JNJ 46%, PG 65%. Snapshot, not in results.csv yet: re-run before quoting (rule 3).

### Checks
- `make test`: 254 passed, 1 skipped (`test_products.py`, `test_fundamentals.py`, `test_research_mode.py`, offline).
- Real data, two processes (extra off / on): proposals, verdicts and checks C–F for Robert, Amira, Mateo identical.
  With extra on, {XEF.TO 25%, XIU.TO 25%, XSB.TO 30%, SLV 10%, LLY 10%} → classes equity 60% / bonds 30% /
  commodities 10%; C2 "Developed ex-North America 42%…; currency CAD 55%, Other 25%, USD 20%".

### Solutions applied (user's OK, decision #41; research mode only)
- Baskets: ESG → XIU.TO replaced by XESG.TO; horizon ≤ 5 y → XBB.TO replaced by XSB.TO; one country > 70% of the
  equities (C2) → smallest 5%-step share to XEF.TO/XEC.TO (3:1). Never by persona name.
- Dividend status on 3 fiscal years; free-cash-flow shortfall in the reason; REITs not measurable without FFO.
- Income names ≤ 80% payout over 3 years (ENB.TO out by the rule); new check F7 ⚠.
- Real data, extra on: Robert core 15% growth, worst drop −4.8% (ZST/XSB); income: ENB.TO out, Canada 78% → 10% to
  XEF/XEC; Amira growth: U.S. 100% → 30% to XEF/XEC; Mateo: ESGV + XESG.TO. All three verdicts pass.
  Extra off: identical to before. Tests: 254 passed, 1 skipped.

### S3 (Sun Nov 15)
- `make data-up` uploads `products_<name>/` and `fundamentals/` too (same keys under `raw/`); `dh.bootstrap` fetches
  them only when `extra` is set (statements optional), and rebuilds a missing catalogue with `build_products.py`.
  Tested with a fake S3 (`tests/test_s3_data.py`). The upload itself needs the event credentials (`.env`): not run here.

### Dividends across the architecture (decision #41, extended)
- Guardian G18 (⚠, research mode only), F1 on covered payers + dividend ETFs, Explainer facts and template line,
  funds' distribution yield. Real data (extra on): Robert income F1 98%, G18 pass, Explainer text passes G11–G13.
  Extra off: proposals, verdicts, checks, 17 rules and the Explainer cache key unchanged. Tests 261 passed.

## In progress / next
1. Will: review the changes in his lane (`rules.py`, `checks.py`, `diversification.py`, `portfolio.py`, `critic.py`).
2. Issuer holdings files for the main new ETFs (C1/C3 exact instead of lower bounds; fossil exclusion through XESG.TO).
3. Turn research mode on for the demo only after re-running `make log-personas`, `make warm` and the deliverables' numbers.

## Decisions made here (technical)
- Catalogue as a Python module (`.csv` is gitignored repo-wide; metadata is not market data).
- Prices through the organizers' `build_prices` (no second downloader). CAD/USD only. Same window as the starter.
- Defensive = short/aggregate/government bonds, cash, gold (`products.DEFENSIVE_SUB_CLASSES`): XSB.TO, PSA.TO, BNDX,
  CGL.TO. Not: corporate, high yield, real return (XRB.TO lost 2.6%/yr over 2021-2026), EM bonds, silver.
- Dividend ratios from statements only; snapshot, never in a backtest.

## Decisions for the user / Will (not taken)
- D1–D4 settled by the user (decision #41). Open: when to turn research mode on for the demo (Next 3).

## Contract changes
- None to `notes/contract.md`. Universe gains optional columns (catalogue only): `sub_class, exposure,
  currency_exposure, gap, source`. `harness.toml [data] extra` (default `[]`). New group `rules.COMMODITIES`.

## How to check it
- `python -m pytest -q tests/test_products.py tests/test_fundamentals.py`, then `make test`.
- `make data-products`, set `extra = ["cadusa"]`, `make data-fundamentals`, then
  `python -c "from dh.agents import market; print(market.dividend_facts(['ENB.TO','RY.TO']))"`.

## Open questions / blocked on
- D1–D4.
