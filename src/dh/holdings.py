"""ETF holdings (issuer files) → data/raw/etf_holdings.csv → {etf: {holding: weight}} for look-through.

    python scripts/build_holdings.py      # raw issuer files in data/raw/holdings/ → etf_holdings.csv + checks
    from dh.holdings import holdings
    holdings()["SPY"]["NVDA"]             # fraction of SPY in NVIDIA

Raw files are untrusted data: parsed as tables only, nothing in them is executed.
Limits: a snapshot of CURRENT holdings (as_of column). Use it for exposure only, never to rebuild past returns.
Own file (not data.py) on purpose: data.py is the market-data lane (notes/decisions.md #8).
"""

from __future__ import annotations

import csv
import re
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .data import load_config

COLUMNS = ["etf", "holding", "name", "weight", "sector", "country", "as_of", "source"]
OTHER = "other"  # cash, futures, FX lines: kept in the file, skipped by holdings()

# ETF (our universe spelling) → filename keyword + where the file comes from (issuer only).
SOURCES = {
    "SPY": dict(key="spy", url="https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"),
    "QQQ": dict(key="qqq", url="https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=QQQ"),
    "ESGV": dict(key="esgv", url="https://investor.vanguard.com/investment-products/etfs/profile/esgv"),
    "XIU.TO": dict(key="xiu", url="https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf"),
}

# Header aliases, matched exactly after lower-casing (first alias found wins).
ALIASES = {
    "ticker": ["holding ticker", "ticker", "symbol", "ticker symbol"],
    "name": ["name", "security name", "holdings", "holding", "description", "security"],
    "weight": ["weight", "weight (%)", "% of funds", "% of fund", "% of net assets", "percent of fund",
               "% of market value", "weight %", "% weight"],
    "sector": ["sector", "gics sector", "sector classification"],
    "country": ["location", "country", "location of risk"],
    "asset_class": ["asset class", "security type", "asset type"],
    "date": ["date", "as of date", "as of"],
}
DATE_PATTERNS = [r"\d{1,2}-[A-Za-z]{3}-\d{4}", r"[A-Za-z]{3,9}\.? \d{1,2},? \d{4}", r"\d{4}-\d{2}-\d{2}",
                 r"\d{1,2}/\d{1,2}/\d{4}"]
NON_EQUITY = re.compile(r"cash|future|currenc|\bfx\b|money market|derivative|margin", re.I)
# Only currency-line names ("US DOLLAR", "CAD CASH"): a bare "dollar" would catch Dollar General / Dollar Tree.
NON_EQUITY_NAME = re.compile(r"^(?:US|USD|CAD|CANADIAN)\s+(?:DOLLAR|CASH)\b|^CASH\b|\bFUTURES?\b|\bCOLLATERAL\b", re.I)


# ---- reading a raw issuer file ---------------------------------------------------------------

def _rows(path: Path) -> list[list[str]]:
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, header=None, dtype=str)
        return [["" if pd.isna(v) else str(v).strip() for v in r] for r in df.itertuples(index=False)]
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return [[c.strip() for c in r] for r in csv.reader(text.splitlines())]


def _find(header: list[str], field: str) -> int | None:
    low = [h.lower().strip() for h in header]
    for a in ALIASES[field]:
        if a in low:
            return low.index(a)
    return None


def _as_of(texts: list[str]) -> str:
    for t in texts:
        for p in DATE_PATTERNS:
            m = re.search(p, t)
            if m:
                try:
                    return pd.to_datetime(m.group(0).replace(".", "")).strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    continue
    return ""


def _num(s: str) -> float | None:
    s = s.replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_file(path: Path) -> tuple[pd.DataFrame, str]:
    """Raw issuer file → (table with ticker, name, weight, sector, country, asset_class; as_of)."""
    rows = _rows(path)
    hi = next((i for i, r in enumerate(rows) if _find(r, "ticker") is not None and _find(r, "weight") is not None), None)
    if hi is None:
        raise ValueError(f"{path.name}: no header row with a ticker and a weight column")
    header = rows[hi]
    idx = {f: _find(header, f) for f in ALIASES}
    recs = []
    for r in rows[hi + 1:]:
        cell = lambda f: r[idx[f]] if idx[f] is not None and idx[f] < len(r) else ""  # noqa: E731
        w = _num(cell("weight"))
        if w is None:
            if recs:  # end of the table (footer / disclaimers)
                break
            continue
        recs.append(dict(ticker=cell("ticker"), name=cell("name"), weight=w, sector=cell("sector"),
                         country=cell("country"), asset_class=cell("asset_class"), date=cell("date")))
    df = pd.DataFrame(recs)
    preamble = [" ".join(r) for r in rows[:hi]]
    as_of = _as_of(preamble) or (_as_of([df.date.iloc[0]]) if len(df) else "")
    return df, as_of


# ---- normalising to our universe spelling ----------------------------------------------------

def normalise(df: pd.DataFrame, etf: str, as_of: str, source: str) -> pd.DataFrame:
    df = df.copy()
    total = df.weight.sum()
    df["weight"] = df.weight / 100 if total > 1.5 else df.weight  # percent → fraction
    t = df.ticker.fillna("").astype(str).str.strip().str.upper()
    other = (t.isin(["", "-", "NAN", "N/A"]) | df.asset_class.fillna("").str.contains(NON_EQUITY)
             | df.name.fillna("").str.contains(NON_EQUITY_NAME))
    if etf.endswith(".TO"):  # TSX listings: RY → RY.TO, class shares BBD.B → BBD-B.TO (Yahoo spelling)
        t = t.where(t.str.endswith(".TO"), t.str.replace(".", "-", regex=False) + ".TO")
    t = t.replace({"GOOG": "GOOGL"})  # two share classes of the same company
    df["holding"] = t.where(~other, OTHER)
    df["name"] = df.name.where(~other, "cash / futures / FX")
    df["sector"] = df.sector.replace({"-": ""})
    out = (df.groupby("holding", as_index=False, sort=False)
             .agg(name=("name", "first"), weight=("weight", "sum"), sector=("sector", "first"),
                  country=("country", "first")))
    out.insert(0, "etf", etf)
    out["as_of"], out["source"] = as_of, source
    return out[COLUMNS].sort_values("weight", ascending=False)


def build(raw_dir: Path, out: Path) -> pd.DataFrame:
    """Parse every recognised issuer file in raw_dir, write the combined CSV, return it."""
    parts, files = [], sorted(p for p in raw_dir.glob("*") if p.suffix.lower() in (".csv", ".xlsx", ".xls"))
    for etf, s in SOURCES.items():
        match = [p for p in files if s["key"] in p.name.lower()]
        if not match:
            print(f"  {etf}: no raw file in {raw_dir} (look-through for {etf} stays 'direct only')")
            continue
        df, as_of = parse_file(match[-1])
        parts.append(normalise(df, etf, as_of, s["url"]))
    allh = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLUMNS)
    out.parent.mkdir(parents=True, exist_ok=True)
    allh.to_csv(out, index=False)
    return allh


# ---- loading for the pipeline ----------------------------------------------------------------

def download(raw_dir: Path) -> list[str]:
    """Fetch the issuer files that are direct downloads (SPY's .xlsx from State Street) into raw_dir. The others
    (QQQ, ESGV, XIU.TO) are web pages: their files are saved by hand (data/README.md). Returns what was fetched;
    never raises (the look-through falls back to "direct only", and says so)."""
    import urllib.request
    raw_dir.mkdir(parents=True, exist_ok=True)
    got = []
    for etf, s in SOURCES.items():
        if not s["url"].lower().endswith((".xlsx", ".xls", ".csv")):
            continue
        dest = raw_dir / s["url"].rsplit("/", 1)[-1]
        try:
            req = urllib.request.Request(s["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                dest.write_bytes(r.read())
            got.append(etf)
        except Exception as e:  # noqa: BLE001
            print(f"[dh.holdings] {etf}: download failed ({type(e).__name__}: {e})")
    return got


def status(path: Path | str | None = None) -> dict:
    """What the look-through can open: {etfs: {etf: as_of}, missing: [...]} — shown to the client, never hidden."""
    p = Path(path) if path else default_path()
    if not p.exists():
        return {"etfs": {}, "missing": sorted(SOURCES), "file": False}
    df = pd.read_csv(p)
    have = {e: str(g["as_of"].iloc[0]) for e, g in df.groupby("etf")}
    return {"etfs": have, "missing": sorted(set(SOURCES) - set(have)), "file": True}


def default_path() -> Path:
    return load_config().data_dir / "etf_holdings.csv"


@lru_cache(maxsize=4)
def holdings(path: Path | str | None = None) -> dict[str, dict[str, float]]:
    """{etf: {holding: weight}}, cash/futures lines excluded. Empty dict if the file is missing."""
    p = Path(path) if path else default_path()
    if not p.exists():
        print(f"[dh.holdings] {p} missing: look-through is 'direct only'. Run scripts/build_holdings.py.",
              file=sys.stderr)
        return {}
    df = pd.read_csv(p)
    df = df[df.holding != OTHER]
    return {etf: dict(zip(g.holding, g.weight.astype(float))) for etf, g in df.groupby("etf")}
