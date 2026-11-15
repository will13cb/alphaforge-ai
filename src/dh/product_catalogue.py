"""Catalogue of the 60 products added on branch produit_cadusa: listed in Canada or the U.S. (CAD or USD only).

Data only (the logic is in dh.products). One row per product:
    (ticker, name, asset_class, sub_class, market, currency, sector, exposure, currency_exposure, gap)
Chosen to be the simplest to integrate: the starter's own asset classes only, prices back to the starter's first
day (2021-11-12), no futures-based funds (roll costs), no crypto or multi-asset ETFs, no near-duplicate of a starter
asset (C6 would flag holding both), no fossil-fuel producer (the fossil-fuel exclusion list stays exact).
- ticker: Yahoo Finance spelling (TSX: ".TO", class shares "-A.TO", units "-UN.TO").
- market, currency: checked on Yahoo Finance (fast_info) on 2026-11-15; every ticker had prices to 2026-11-12.
- sector, following the starter's convention so the checks read it right: a stock's GICS sector; a sector ETF's
  GICS sector (100% of it is that sector); "Broad market (...)" for a diversified equity ETF; "Bonds (...)";
  "Gold (...)"; "Commodities (...)". Labels starting with Broad market / Bonds / Gold / Commodities are not sectors.
- exposure: where the holdings are, NOT the country of listing for an international ETF (XEF.TO holds Europe and Japan).
- currency_exposure: the currency risk a CAD investor carries (CAD-hedged → CAD; unhedged foreign holdings → Other).
- gap: what the starter lacked that this product adds.
Names and sectors are ours, from the issuers' and companies' public names; re-verify before quoting.
"""

CATALOGUE_NAME = "cadusa"
AS_OF = "2026-11-15"
SOURCE = "Yahoo Finance via yfinance (prices, currency, exchange); names and classification by the team"

E, B, C, S = "etf_equity", "etf_bond", "etf_commodity", "equity"

PRODUCTS = [
    # ---- Canada-listed ETFs (16) ----
    ("XEF.TO", "iShares Core MSCI EAFE IMI Index ETF", E, "international_developed", "TSX", "CAD", "Broad market (developed ex-North America)", "Developed ex-North America", "Other", "international"),
    ("XEC.TO", "iShares Core MSCI Emerging Markets IMI Index ETF", E, "emerging", "TSX", "CAD", "Broad market (emerging markets)", "Emerging markets", "Other", "emerging_markets"),
    ("XEI.TO", "iShares S&P/TSX Composite High Dividend Index ETF", E, "factor_dividend", "TSX", "CAD", "Broad market (Canada, high dividend)", "Canada", "CAD", "factor"),
    ("ZLB.TO", "BMO Low Volatility Canadian Equity ETF", E, "factor_low_vol", "TSX", "CAD", "Broad market (Canada, low volatility)", "Canada", "CAD", "factor"),
    ("XESG.TO", "iShares ESG Aware MSCI Canada Index ETF", E, "esg", "TSX", "CAD", "Broad market (Canada, ESG-screened)", "Canada", "CAD", "esg"),
    ("XMA.TO", "iShares S&P/TSX Capped Materials Index ETF", E, "sector", "TSX", "CAD", "Materials", "Canada", "CAD", "materials"),
    ("XGD.TO", "iShares S&P/TSX Global Gold Index ETF", E, "sector", "TSX", "CAD", "Materials", "Global", "CAD", "materials"),
    ("XRE.TO", "iShares S&P/TSX Capped REIT Index ETF", E, "sector", "TSX", "CAD", "Real Estate", "Canada", "CAD", "real_estate"),
    ("XUT.TO", "iShares S&P/TSX Capped Utilities Index ETF", E, "sector", "TSX", "CAD", "Utilities", "Canada", "CAD", "utilities"),
    ("XSB.TO", "iShares Core Canadian Short Term Bond Index ETF", B, "short_term", "TSX", "CAD", "Bonds (Canada short term)", "Canada", "CAD", "bonds"),
    ("XCB.TO", "iShares Core Canadian Corporate Bond Index ETF", B, "corporate", "TSX", "CAD", "Bonds (Canada corporate)", "Canada", "CAD", "corporate_bonds"),
    ("XRB.TO", "iShares Canadian Real Return Bond Index ETF", B, "inflation_linked", "TSX", "CAD", "Bonds (Canada real return)", "Canada", "CAD", "inflation_linked"),
    ("XHY.TO", "iShares U.S. High Yield Bond Index ETF (CAD-Hedged)", B, "high_yield", "TSX", "CAD", "Bonds (U.S. high yield, CAD-hedged)", "United States", "CAD", "high_yield"),
    ("PSA.TO", "Purpose High Interest Savings Fund", B, "cash", "TSX", "CAD", "Bonds (cash, high-interest savings)", "Canada", "CAD", "cash"),
    ("CGL.TO", "iShares Gold Bullion ETF", C, "gold", "TSX", "CAD", "Gold (CAD-hedged)", "Global", "CAD", "gold_cad"),
    ("ZRE.TO", "BMO Equal Weight REITs Index ETF", E, "sector", "TSX", "CAD", "Real Estate", "Canada", "CAD", "real_estate"),
    # ---- U.S.-listed ETFs and trusts (14) ----
    ("EWJ", "iShares MSCI Japan ETF", E, "country", "NYSE Arca", "USD", "Broad market (Japan)", "Japan", "Other", "country"),
    ("INDA", "iShares MSCI India ETF", E, "country", "Cboe BZX", "USD", "Broad market (India)", "India", "Other", "country"),
    ("EWZ", "iShares MSCI Brazil ETF", E, "country", "NYSE Arca", "USD", "Broad market (Brazil)", "Brazil", "Other", "country"),
    ("IWM", "iShares Russell 2000 ETF", E, "small_cap", "NYSE Arca", "USD", "Broad market (U.S. small caps)", "United States", "USD", "small_cap"),
    ("SCHD", "Schwab U.S. Dividend Equity ETF", E, "factor_dividend", "NYSE Arca", "USD", "Broad market (U.S., dividend)", "United States", "USD", "factor"),
    ("USMV", "iShares MSCI USA Min Vol Factor ETF", E, "factor_low_vol", "Cboe BZX", "USD", "Broad market (U.S., low volatility)", "United States", "USD", "factor"),
    ("XLV", "Health Care Select Sector SPDR Fund", E, "sector", "NYSE Arca", "USD", "Health Care", "United States", "USD", "health_care"),
    ("XLP", "Consumer Staples Select Sector SPDR Fund", E, "sector", "NYSE Arca", "USD", "Consumer Staples", "United States", "USD", "staples"),
    ("XLI", "Industrial Select Sector SPDR Fund", E, "sector", "NYSE Arca", "USD", "Industrials", "United States", "USD", "industrials"),
    ("COPX", "Global X Copper Miners ETF", E, "sector", "NYSE Arca", "USD", "Materials", "Global", "Other", "industrial_metals"),
    ("BNDX", "Vanguard Total International Bond ETF (USD-hedged)", B, "aggregate", "NASDAQ", "USD", "Bonds (world ex-U.S. aggregate, USD-hedged)", "Global ex-U.S.", "USD", "international_bonds"),
    ("TIP", "iShares TIPS Bond ETF", B, "inflation_linked", "NYSE Arca", "USD", "Bonds (U.S. inflation-protected)", "United States", "USD", "inflation_linked"),
    ("EMB", "iShares J.P. Morgan USD Emerging Markets Bond ETF", B, "emerging", "NASDAQ", "USD", "Bonds (emerging markets, USD)", "Emerging markets", "USD", "international_bonds"),
    ("SLV", "iShares Silver Trust", C, "silver", "NYSE Arca", "USD", "Commodities (silver)", "Global", "USD", "silver"),
    # ---- Canadian stocks (15) ----
    ("NTR.TO", "Nutrien", S, "stock", "TSX", "CAD", "Materials", "Canada", "CAD", "materials"),
    ("ABX.TO", "Barrick", S, "stock", "TSX", "CAD", "Materials", "Canada", "CAD", "materials"),
    ("AEM.TO", "Agnico Eagle Mines", S, "stock", "TSX", "CAD", "Materials", "Canada", "CAD", "materials"),
    ("FNV.TO", "Franco-Nevada", S, "stock", "TSX", "CAD", "Materials", "Canada", "CAD", "materials"),
    ("WPM.TO", "Wheaton Precious Metals", S, "stock", "TSX", "CAD", "Materials", "Canada", "CAD", "silver"),
    ("BCE.TO", "BCE", S, "stock", "TSX", "CAD", "Communication Services", "Canada", "CAD", "telecom"),
    ("T.TO", "TELUS", S, "stock", "TSX", "CAD", "Communication Services", "Canada", "CAD", "telecom"),
    ("SLF.TO", "Sun Life Financial", S, "stock", "TSX", "CAD", "Financials", "Canada", "CAD", "insurance"),
    ("IFC.TO", "Intact Financial", S, "stock", "TSX", "CAD", "Financials", "Canada", "CAD", "insurance"),
    ("CP.TO", "Canadian Pacific Kansas City", S, "stock", "TSX", "CAD", "Industrials", "Canada", "CAD", "industrials"),
    ("WCN.TO", "Waste Connections", S, "stock", "TSX", "CAD", "Industrials", "Canada", "CAD", "industrials"),
    ("L.TO", "Loblaw Companies", S, "stock", "TSX", "CAD", "Consumer Staples", "Canada", "CAD", "staples"),
    ("DOL.TO", "Dollarama", S, "stock", "TSX", "CAD", "Consumer Staples", "Canada", "CAD", "staples"),
    ("GIB-A.TO", "CGI (Class A)", S, "stock", "TSX", "CAD", "Information Technology", "Canada", "CAD", "it_services"),
    ("CAR-UN.TO", "Canadian Apartment Properties REIT", S, "reit", "TSX", "CAD", "Real Estate", "Canada", "CAD", "real_estate"),
    # ---- U.S. stocks (15) ----
    ("UNH", "UnitedHealth Group", S, "stock", "NYSE", "USD", "Health Care", "United States", "USD", "health_care"),
    ("LLY", "Eli Lilly", S, "stock", "NYSE", "USD", "Health Care", "United States", "USD", "health_care"),
    ("ABBV", "AbbVie", S, "stock", "NYSE", "USD", "Health Care", "United States", "USD", "health_care"),
    ("BRK-B", "Berkshire Hathaway (Class B)", S, "stock", "NYSE", "USD", "Financials", "United States", "USD", "financials"),
    ("V", "Visa", S, "stock", "NYSE", "USD", "Financials", "United States", "USD", "payments"),
    ("KO", "Coca-Cola", S, "stock", "NYSE", "USD", "Consumer Staples", "United States", "USD", "staples"),
    ("PEP", "PepsiCo", S, "stock", "NASDAQ", "USD", "Consumer Staples", "United States", "USD", "staples"),
    ("WMT", "Walmart", S, "stock", "NASDAQ", "USD", "Consumer Staples", "United States", "USD", "staples"),
    ("COST", "Costco Wholesale", S, "stock", "NASDAQ", "USD", "Consumer Staples", "United States", "USD", "staples"),
    ("HD", "Home Depot", S, "stock", "NYSE", "USD", "Consumer Discretionary", "United States", "USD", "consumer"),
    ("MCD", "McDonald's", S, "stock", "NYSE", "USD", "Consumer Discretionary", "United States", "USD", "consumer"),
    ("CAT", "Caterpillar", S, "stock", "NYSE", "USD", "Industrials", "United States", "USD", "industrials"),
    ("NEE", "NextEra Energy", S, "stock", "NYSE", "USD", "Utilities", "United States", "USD", "utilities"),
    ("PLD", "Prologis", S, "reit", "NYSE", "USD", "Real Estate", "United States", "USD", "real_estate"),
    ("LIN", "Linde", S, "stock", "NASDAQ", "USD", "Materials", "United States", "USD", "materials"),
]
