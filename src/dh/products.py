"""More products, same data path (branch produit_cadusa): a catalogue, its checks, and a data-quality report.

    from dh import products
    cat = products.catalogue()                     # 60 products listed in Canada or the U.S., starter-style columns
    products.validate_catalogue(cat)               # [] when clean; each issue says what and why
    products.asset_groups(data.universe())         # stocks / ETFs / bonds / defensive... derived from the data

How a catalogue reaches the agents: `scripts/build_products.py` (`make data-products`) downloads its prices into
data/raw/products_<name>/ with the organizers' own build function, then `harness.toml [data] extra = ["<name>"]`
makes `dh.data` load them next to the starter's 31, converted to CAD on the same calendar. Default: no extra, so
nothing changes for the app, the tests or the numbers in the deliverables.

Scope: CAD or USD listings only (no new FX, same North American calendar), the starter's asset classes only. Foreign
listings are branch univers_produit. Nothing here decides what a client may hold: the Portfolio's baskets are unchanged.
With `extra` on, rules.py adds the catalogue to its groups through `asset_groups` (which gives exactly rules.py's sets
on the starter), so the checks classify a new product the same way as the starter's.
"""

from __future__ import annotations

import ast
from functools import lru_cache

import numpy as np
import pandas as pd

from .data import ROOT

COLUMNS = ["ticker", "name", "asset_class", "sub_class", "market", "currency", "sector", "exposure", "currency_exposure",
           "gap"]
STARTER_COLUMNS = ["asset_id", "ticker", "name", "asset_class", "market", "currency", "sector"]

ASSET_CLASSES = {"equity", "etf_equity", "etf_bond", "etf_commodity", "crypto"}   # the starter's, nothing new
CURRENCIES = {"CAD", "USD"}                       # what dh.data converts today (fx_usdcad_daily.csv)
CURRENCY_EXPOSURES = {"CAD", "USD", "Other"}      # the currency risk a CAD investor carries (hedged → hedge currency)
GICS_SECTORS = {"Energy", "Materials", "Industrials", "Consumer Discretionary", "Consumer Staples", "Health Care",
                "Financials", "Information Technology", "Communication Services", "Utilities", "Real Estate"}
NOT_A_SECTOR = ("Broad market", "Bonds", "Gold", "Commodities")   # labels the sector checks skip (diversification)
MARKETS = {"TSX", "NYSE", "NASDAQ", "NYSE Arca", "Cboe BZX", "NYSE American"}

# Sub-classes of the starter's assets (the organizers' file has none). Needed to derive DEFENSIVE from data.
STARTER_SUB_CLASS = {"XBB.TO": "aggregate", "ZST.TO": "short_term", "AGG": "aggregate", "TLT": "long_government",
                     "GLD": "gold", "XIU.TO": "broad", "SPY": "broad", "QQQ": "broad_growth", "ESGV": "esg"}

# What "defensive" means in rules.py (meant to hold up when stocks fall): short or aggregate investment-grade bonds,
# cash, gold. Long bonds (TLT: rate risk), corporate, high yield, preferred shares and inflation-linked bonds are NOT.
DEFENSIVE_SUB_CLASSES = {"aggregate", "short_term", "cash", "government", "gold"}

MIN_YEARS = 5.0              # below this, a product is "short history": kept, but outside the main analyses
BIG_MOVE = 0.40              # one-day adjusted move flagged (same threshold as the organizers' check)
STALE_RUN = 5                # consecutive 0% days WITH zero volume = stale quote, not a calm market


# ---- catalogue -------------------------------------------------------------------------------------------------

def catalogue(name: str = "cadusa") -> pd.DataFrame:
    """The catalogue as a DataFrame: the starter's universe columns (asset_id P001..) + sub_class, exposure, gap."""
    from . import product_catalogue as pc
    if name != pc.CATALOGUE_NAME:
        raise ValueError(f"unknown catalogue {name!r}; known: {pc.CATALOGUE_NAME!r}")
    df = pd.DataFrame(pc.PRODUCTS, columns=COLUMNS)
    df.insert(0, "asset_id", [f"P{i:03d}" for i in range(1, len(df) + 1)])
    df["source"] = f"{pc.SOURCE}; checked {pc.AS_OF}"
    return df


def starter_universe() -> pd.DataFrame:
    """The starter's 31 assets, read from the organizers' script (works without the CSVs, e.g. in tests)."""
    src = (ROOT / "Datathon2026Infos" / "alphaforge_starter" / "build_dataset.py").read_text()
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) == "UNIVERSE" for t in n.targets))
    df = pd.DataFrame(ast.literal_eval(node.value), columns=STARTER_COLUMNS[1:])
    df.insert(0, "asset_id", [f"A{i:02d}" for i in range(1, len(df) + 1)])
    return df


def _issue(ticker, check, status, reason) -> dict:
    return dict(ticker=ticker, check=check, status=status, reason=reason)


def validate_catalogue(df: pd.DataFrame, starter_tickers=None) -> list[dict]:
    """Every problem that would make the data path or an agent quote a wrong number. [] = clean.
    status 'fail' blocks the build; 'warn' is reported."""
    issues: list[dict] = []
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        return [_issue(None, "columns", "fail", f"missing columns: {', '.join(missing)}")]
    starter = set(starter_universe().ticker if starter_tickers is None else starter_tickers)
    for t, n in df.ticker.value_counts().items():
        if n > 1:
            issues.append(_issue(t, "unique", "fail", f"listed {n} times"))
    for _, r in df.iterrows():
        t = r.ticker
        if not isinstance(t, str) or not t.strip() or t != t.strip():
            issues.append(_issue(t, "ticker", "fail", "empty ticker or surrounding spaces"))
            continue
        for c in COLUMNS:
            if not isinstance(r[c], str) or not r[c].strip():
                issues.append(_issue(t, c, "fail", f"{c} is empty or not text ({r[c]!r})"))
        if t in starter:
            issues.append(_issue(t, "starter", "fail", "already in the starter's 31 (one price series per ticker)"))
        if r.asset_class not in ASSET_CLASSES:
            issues.append(_issue(t, "asset_class", "fail", f"unknown class {r.asset_class!r}"))
        if r.currency not in CURRENCIES:
            issues.append(_issue(t, "currency", "fail", f"{r.currency!r}: dh.data converts only CAD and USD"))
        if r.market not in MARKETS:
            issues.append(_issue(t, "market", "fail", f"unknown market {r.market!r}"))
        tsx = t.endswith(".TO")
        if tsx != (r.currency == "CAD"):
            issues.append(_issue(t, "currency", "fail", f"listing {'TSX' if tsx else 'U.S.'} but currency {r.currency}"))
        if tsx != (r.market == "TSX"):
            issues.append(_issue(t, "market", "fail", f"ticker {'ends' if tsx else 'does not end'} in .TO, market {r.market}"))
        if r.asset_class == "equity" and r.sub_class not in ("stock", "reit"):
            issues.append(_issue(t, "sub_class", "warn", f"a single company with sub_class {r.sub_class!r}"))
        if r.currency_exposure not in CURRENCY_EXPOSURES:
            issues.append(_issue(t, "currency_exposure", "fail", f"{r.currency_exposure!r} not in {sorted(CURRENCY_EXPOSURES)}"))
        # sector convention: the checks count any label as a sector unless it starts with a NOT_A_SECTOR prefix
        sec = str(r.sector)
        if r.asset_class == "equity" and sec not in GICS_SECTORS:
            issues.append(_issue(t, "sector", "fail", f"a stock needs its GICS sector, not {sec!r}"))
        elif r.asset_class == "etf_equity" and sec not in GICS_SECTORS and not sec.startswith("Broad market"):
            issues.append(_issue(t, "sector", "fail", f"{sec!r}: a sector ETF takes its GICS sector, else 'Broad market (...)'"))
        elif r.asset_class == "etf_bond" and not sec.startswith("Bonds"):
            issues.append(_issue(t, "sector", "fail", f"{sec!r}: a bond ETF's label starts with 'Bonds'"))
        elif r.asset_class == "etf_commodity" and not sec.startswith(("Gold", "Commodities")):
            issues.append(_issue(t, "sector", "fail", f"{sec!r}: a commodity label starts with 'Gold' or 'Commodities'"))
        if r.asset_class == "equity" and sec == "Energy":
            issues.append(_issue(t, "exclusions", "warn", "an energy company: add it to rules.EXCLUSIONS['fossil_fuels'] "
                                                          "if it produces or carries fossil fuels"))
    return issues


@lru_cache(maxsize=16)
def column_map(col: str, name: str = "cadusa") -> dict[str, str]:
    """{ticker: value} of one catalogue column, without loading any data (used by the checks and market tools)."""
    cat = catalogue(name)
    return dict(zip(cat.ticker, cat[col]))


# ---- groups derived from data (what rules.py hard-codes for the starter) ----------------------------------------

def asset_groups(universe: pd.DataFrame) -> dict[str, frozenset]:
    """Asset groups from the universe's columns. On the starter's 31 this equals rules.py's sets exactly
    (tests/test_products.py); rules.py adds a catalogue's groups to its own when the catalogue is in `extra`."""
    u = universe.copy()
    sub = u["sub_class"].astype("object") if "sub_class" in u.columns else pd.Series(np.nan, index=u.index, dtype="object")
    u["sub"] = sub.fillna(u.ticker.map(STARTER_SUB_CLASS))
    commodity = u.asset_class == "etf_commodity"
    gold = commodity & ((u["sub"] == "gold") | (u.sector.astype(str).str.lower().str.startswith("gold")))

    def pick(mask) -> frozenset:
        return frozenset(u.loc[mask, "ticker"])

    g = dict(stocks=pick(u.asset_class == "equity"), equity_etfs=pick(u.asset_class == "etf_equity"),
             bond_etfs=pick(u.asset_class == "etf_bond"), crypto=pick(u.asset_class == "crypto"), gold=pick(gold),
             commodities=pick(commodity & ~gold),
             defensive=pick(u["sub"].isin(DEFENSIVE_SUB_CLASSES) & u.asset_class.isin(["etf_bond", "etf_commodity"])))
    g["etfs"] = g["equity_etfs"] | g["bond_etfs"] | g["gold"] | g["commodities"]
    g["universe"] = pick(u.ticker.notna())
    return g


# ---- data quality -----------------------------------------------------------------------------------------------

def quality_report(prices: pd.DataFrame, catalogue_df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """One row per catalogue product: history, coverage of [start, end], currency, big moves, stale quotes, gaps,
    and the toolkit's own diagnostic (quant_toolkit.data_quality). status: ok / warn / fail, reasons say why.
    Flags never delete data (a +44% day can be real); 'fail' means the series can't be used as is."""
    from .quant_toolkit import data_quality

    rows = []
    p = prices.copy()
    p["date"] = pd.to_datetime(p["date"], errors="coerce")
    for _, c in catalogue_df.iterrows():
        t, reasons, fail = c.ticker, [], False
        g = p[p.ticker == t].sort_values("date")
        row = dict(ticker=t, asset_class=c.asset_class, currency=c.currency)
        if g.empty:
            rows.append({**row, "status": "fail", "reasons": "no prices downloaded"})
            continue
        adj = pd.to_numeric(g["adj_close"], errors="coerce")
        bad_num = int(adj.isna().sum() - g["adj_close"].isna().sum())
        if bad_num:
            fail = True; reasons.append(f"{bad_num} non-numeric price(s)")
        if g["date"].isna().any():
            fail = True; reasons.append(f"{int(g['date'].isna().sum())} unreadable date(s)")
        if g["date"].duplicated().any():
            fail = True; reasons.append("duplicate dates")
        if (adj <= 0).any():
            fail = True; reasons.append(f"{int((adj <= 0).sum())} price(s) <= 0")
        if "currency" in g.columns and set(g["currency"].dropna()) - {c.currency}:
            fail = True; reasons.append(f"prices in {sorted(set(g['currency'].dropna()))}, catalogue says {c.currency}")
        s = pd.Series(adj.to_numpy(), index=g["date"]).dropna()
        s = s[s.index.notna() & ~s.index.duplicated()]
        s = s[s > 0]
        if s.empty:
            rows.append({**row, "status": "fail", "reasons": "; ".join(reasons + ["no usable price"])})
            continue
        first, last = s.index[0], s.index[-1]
        years = (last - first).days / 365.25
        covers = first <= pd.Timestamp(start) + pd.Timedelta(days=7)
        history = "full_window" if covers else ("short_history" if years < MIN_YEARS else "late_start")
        if not covers:
            reasons.append(f"starts {first.date()}, after {start} ({history.replace('_', ' ')}, {years:.1f} y)")
        if last < pd.Timestamp(end) - pd.Timedelta(days=7):
            reasons.append(f"last price {last.date()}, before {end}")
        r = s.pct_change().dropna()
        big = r[r.abs() > BIG_MOVE]
        if len(big):
            reasons.append("one-day move " + ", ".join(f"{v:+.0%} on {d.date()}" for d, v in big.items())
                           + " (check split / data error; kept)")
        one = g.dropna(subset=["date"]).drop_duplicates("date").set_index("date")   # duplicates already reported
        vol = pd.to_numeric(one["volume"], errors="coerce").reindex(r.index) if "volume" in g else None
        stale = (r == 0) & (vol == 0) if vol is not None else pd.Series(False, index=r.index)
        run = int(stale.groupby((stale != stale.shift()).cumsum()).cumsum().max()) if len(stale) else 0
        if run >= STALE_RUN:
            reasons.append(f"{run} days in a row unchanged with no volume (stale quote)")
        gap = int(s.index.to_series().diff().dt.days.max()) if len(s) > 1 else 0
        if gap > 5 and c.asset_class != "crypto":
            reasons.append(f"{gap}-day gap in the dates")
        dq = data_quality(s, kind="prices")
        if not dq.get("utilisable", True):
            fail = True
        recent = g.tail(252)
        adv = float((pd.to_numeric(recent["close"], errors="coerce") * pd.to_numeric(recent["volume"], errors="coerce")).mean()) \
            if {"close", "volume"} <= set(g.columns) else np.nan
        rows.append({**row, "first": str(first.date()), "last": str(last.date()), "years": round(years, 1),
                     "history": history, "rows": len(s), "max_1d_move": round(float(r.abs().max()), 4) if len(r) else 0.0,
                     "stale_run": run, "max_gap_days": gap, "adv_local_m": round(adv / 1e6, 2) if adv == adv else np.nan,
                     "toolkit_alerts": len(dq.get("alertes", [])),
                     "status": "fail" if fail else ("warn" if reasons else "ok"), "reasons": "; ".join(reasons)})
    return pd.DataFrame(rows)
