"""Shared rule tables: risk-level thresholds, asset groups, exclusions.

Every number here is a TEAM ASSUMPTION (decided Sat Nov 14, see notes/decisions.md), not a regulatory
figure. Change only with team agreement and log it in the CLAUDE.md decisions log: Profiler, Portfolio and
Guardian all read these tables, so a change moves every result.
"""

from __future__ import annotations

# ---- risk levels -------------------------------------------------------------------------------
# max_drawdown: worst historical peak-to-trough on the 2021-11 → 2026-11 window (includes 2022) the
#               strategy may show.  target_vol: annualised volatility ceiling (warning, not a hard stop).
# min_defensive: share in DEFENSIVE assets.
# max_single / max_crypto: NO LONGER USED by the Profiler (decision #24 computes them from the client and the data,
# see company_cap below); kept only for experiments/data/threshold_check.py (#13).
RISK_LEVELS = {
    1: dict(name="Preserve",   max_drawdown=0.08, target_vol=0.05, min_defensive=0.75, max_single=0.05, max_crypto=0.00),
    2: dict(name="Cautious",   max_drawdown=0.15, target_vol=0.08, min_defensive=0.50, max_single=0.08, max_crypto=0.00),
    3: dict(name="Balanced",   max_drawdown=0.22, target_vol=0.12, min_defensive=0.30, max_single=0.10, max_crypto=0.02),
    4: dict(name="Growth",     max_drawdown=0.30, target_vol=0.16, min_defensive=0.15, max_single=0.12, max_crypto=0.05),
    5: dict(name="Aggressive", max_drawdown=0.40, target_vol=0.22, min_defensive=0.05, max_single=0.15, max_crypto=0.10),
}

# Knowledge score at or below this: no crypto, single-company loss budget halved (KYC: propose only what they understand).
BEGINNER_MAX_KNOWLEDGE = 2

# ---- decision #17/#19: the split comes from the client, not from the level -------------------------
# The level's max_drawdown is used only as the CAPACITY side of the client's loss limit (#19), and its
# min_defensive is NOT used any more: the defensive floor = max(money needed within 3 years, SAFETY_MIN_DEFENSIVE).
SAFETY_MIN_DEFENSIVE = 0.05   # never 100% growth, whoever the client (G6 safety net)

# Horizon cap (system-design A2, decision #22): the sooner the money is needed, the less growth, whatever the data
# say. A DIRECTIVE estimated per client from their own horizon, linear between two team-assumption anchors:
# up to H_NO_GROWTH years almost nothing goes into stocks; from H_FULL_GROWTH years the horizon no longer limits.
# Not fitted on any persona. Why a directive and not the data: 2021-2026 holds one mild bear market (in CAD), so a
# data-only ceiling allowed 80-85% stocks at 4 years.
H_NO_GROWTH = 2.0
H_FULL_GROWTH = 15.0


# Portfolio checks C-F thresholds (decision #20, TEAM ASSUMPTIONS, notes/system-design.md "What each check returns").
MAX_COUNTRY_EQUITY = 0.70     # C2 ⚠: one country above 70% of the equities (country of listing, holdings when known)
SECTOR_WARN = 0.30            # C3 ⚠: one sector above 30% of the portfolio (✘ above 40%, decision #18)
MAX_JOB_SECTOR = 0.15         # C3b ✘: the client's own job sector above 15% (income and savings hit together)
MIN_EFFECTIVE_N = 8           # C5 ⚠: fewer than 8 effective holdings, 1/Σw² on look-through weights
ETF_ASSUMED_LINES = 100       # C5: an ETF (or ETF remainder) without holdings data counts as 100 equal lines
CORR_WARN = 0.85              # C6 ⚠: two holdings correlated above 0.85 (✘ at 0.95, decision #18)
OVERLAP_WARN = 0.50           # C6 ⚠: two ETFs sharing more than half their holdings
TOLERANCE_CLOSE = 0.80        # D1 ⚠: worst drop above 80% of the loss the client said they'd accept


def horizon_max_growth(years: float) -> float:
    """Largest growth (stocks + crypto) share for this horizon: 0% at <= 2 y, ~8% at 3 y, ~23% at 5 y, ~62% at
    10 y, 100% from 15 y (linear in between)."""
    x = (years - H_NO_GROWTH) / (H_FULL_GROWTH - H_NO_GROWTH)
    return round(min(1.0, max(0.0, x)), 4)


# ---- decision #24: one company's (and crypto's) cap comes from the client AND the data, not from a table ----------
# Two diversification principles, each scaled by this client and this asset:
#  1. loss budget: if the company repeated its own worst drop in the data, that alone may cost at most
#     LOSS_SHARE_ONE_COMPANY of the client's loss limit  →  cap = share × loss_limit / |worst drop|
#     (TSLA fell 71%, JNJ 16%: TSLA gets a much smaller cap for the same client).
#  2. spread: no company above 1/MIN_COMPANIES of what the client can hold in stocks (horizon, liquidity, #22),
#     so the stock part is always at least MIN_COMPANIES companies' worth.
# Crypto (BTC + ETH) is one bet: same formula with the worse of the two drops. No data → assume it can lose 100%.
LOSS_SHARE_ONE_COMPANY = 0.25
MIN_COMPANIES = 5


def company_cap(loss_limit: float, worst_drop: float | None, max_growth: float, share: float) -> tuple[float, str]:
    """(cap, which principle binds). worst_drop is <= 0 (e.g. -0.709); None = no data, assume -100%."""
    dd = abs(worst_drop) if worst_drop else 1.0
    by_loss = share * loss_limit / dd if dd > 0 else 1.0
    by_spread = max_growth / MIN_COMPANIES
    return (round(by_loss, 4), "loss") if by_loss <= by_spread else (round(by_spread, 4), "spread")


GOAL_MIN_PROB = 0.50          # R4: "reachable" = at least a 50% chance at the target (central assumption)
GOAL_LOW_PROB = 0.25          # R4: below 25% even at the ceiling → "impossible within your limits", else "insufficient"

# ---- quantitative audit, phase 2 (notes/risk-architecture.md, decisions R1-R9) ---------------------------------
# R1: the growth ceiling is the largest share whose SIMULATED drawdown over the client's horizon breaks the loss limit
# with a probability of at most LOSS_ALPHA (stationary bootstrap, central assumption), not the one past drawdown.
LOSS_ALPHA = 0.10
# R3: central assumption = the growth part earns cash + this premium a year (the defensive part earns cash).
# Order of magnitude of the long-run equity premium over bills (Dimson, Marsh & Staunton, Global Investment Returns
# Yearbook, world 1900-present: about 3-4% a year geometric). Verify against the current edition before quoting it.
CENTRAL_PREMIUM = 0.03
# R9: goals are shown in nominal dollars and in today's dollars at the Bank of Canada's 2% inflation-control target.
INFLATION = 0.02
# R2: window sensitivity of the ceiling = the ceiling recomputed on 3-year sub-windows, one year apart.
SENSITIVITY_YEARS, SENSITIVITY_STEP_YEARS = 3.0, 1.0

# ---- asset groups (starter universe, 31 assets) ----------------------------------------------
STOCKS = {
    "RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "SHOP.TO", "CSU.TO",
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM",
}
EQUITY_ETFS = {"XIU.TO", "SPY", "QQQ", "ESGV"}
BOND_ETFS = {"XBB.TO", "ZST.TO", "AGG", "TLT"}
CRYPTO = {"BTC-USD", "ETH-USD"}
GOLD = {"GLD"}
COMMODITIES: set[str] = set()   # commodity funds other than gold: none in the starter


def _extra_groups() -> dict:
    """Branch produit_cadusa: with harness.toml [data] extra = ["cadusa"], the catalogue's products join the groups
    below, derived from its columns by dh.products.asset_groups (which gives exactly these sets on the starter).
    Without extra (the default), nothing changes."""
    from ..data import load_config
    groups: dict = {}
    for name in load_config().extra:
        from ..products import asset_groups, catalogue
        for k, v in asset_groups(catalogue(name)).items():
            groups[k] = groups.get(k, frozenset()) | v
    return groups


_EXTRA = _extra_groups()
STOCKS |= _EXTRA.get("stocks", set())
EQUITY_ETFS |= _EXTRA.get("equity_etfs", set())
BOND_ETFS |= _EXTRA.get("bond_etfs", set())
CRYPTO |= _EXTRA.get("crypto", set())
GOLD |= _EXTRA.get("gold", set())
COMMODITIES |= _EXTRA.get("commodities", set())
UNIVERSE = STOCKS | EQUITY_ETFS | BOND_ETFS | CRYPTO | GOLD | COMMODITIES
ETFS = EQUITY_ETFS | BOND_ETFS | GOLD | COMMODITIES

# Defensive = what is meant to hold up when stocks fall. TLT is a bond ETF but NOT defensive here:
# 20+ year Treasuries are very rate-sensitive (check its 2022 drawdown with `make check`).
# From a catalogue: short/aggregate/government bonds, cash, gold (dh.products.DEFENSIVE_SUB_CLASSES).
DEFENSIVE = {"ZST.TO", "XBB.TO", "AGG", "GLD"} | _EXTRA.get("defensive", set())

# Dividend payers held for income (F1 income objective, the "income" strategy's single names): one list (audit P10).
DIVIDEND_PAYERS = {"RY.TO", "TD.TO", "FTS.TO", "ENB.TO", "JNJ", "PG"}

# Client exclusion keywords → tickers held directly. Through ETFs it needs holdings data (look-through).
EXCLUSIONS = {
    "crypto": CRYPTO,
    "fossil_fuels": {"ENB.TO", "CNQ.TO", "XOM"},
    "single_stocks": STOCKS,
}

# KYC essentials (modelled on NI 31-103 s.13.2): without these the Profiler asks, it doesn't guess.
ESSENTIAL_FIELDS = ["age", "horizon_years", "objective", "loss_reaction", "max_loss_pct",
                    "emergency_fund_months", "income_stability", "knowledge_level"]


def excluded_tickers(exclusions) -> set[str]:
    out: set[str] = set()
    for e in exclusions or []:
        out |= EXCLUSIONS.get(e, {e} if e in UNIVERSE else set())
    return out
