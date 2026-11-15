"""Loaders for the AlphaForge data. Everyone goes through here, so numbers agree.

    from dh.data import universe, returns
    r = returns(["SPY", "XIU.TO", "BTC-USD"])   # daily returns in base currency (harness.toml)

Facts baked in (from the starter README): .TO tickers are CAD, the rest USD; use adj_close for
returns; FX has gaps on Canadian holidays (forward-filled); crypto trades 7 days a week.

Longer histories (decision #31, `scripts/build_long_data.py`): assets start on different days. Before an asset's first
price its returns are NaN (never 0%: a missing day is not a calm day), except for the stand-ins listed in
`harness.toml [data.proxies]`, applied only before the first real price and reported by `proxies_used()`.

More products (branch produit_cadusa): `harness.toml [data] extra = ["cadusa"]` loads data/raw/products_cadusa/
(`make data-products`) next to the starter's files: same columns, same calendar, same CAD conversion. Default: no
extra. Only CAD and USD prices can be converted; any other currency is refused, never left unconverted.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field

from functools import lru_cache
from pathlib import Path

import pandas as pd


def _find_root() -> Path:
    """The project folder (harness.toml, cache/, scripts/). From a source checkout or an editable install it is two
    levels above this file; when a host installs the package as a copy into site-packages (Streamlit Cloud with a
    plain `pip install .`), that path is inside the venv, so look from the working directory up instead."""
    here = Path(__file__).resolve().parents[2]
    if (here / "harness.toml").exists():
        return here
    for p in (Path.cwd(), *Path.cwd().parents):
        if (p / "harness.toml").exists():
            return p
    return here


ROOT = _find_root()
RESULTS = ROOT / "results.csv"
STARTER = ROOT / "Datathon2026Infos" / "alphaforge_starter"
DEFAULT_LABEL = "2021-2026"   # the starter-pack window, used in texts when no data is loaded (tests, fresh clone)


@dataclass(frozen=True)
class Config:
    data_dir: Path = ROOT / "data" / "raw"
    base_currency: str = "CAD"
    calendar: str = "weekdays"
    start: str = ""
    proxies: tuple = field(default_factory=tuple)   # ((ticker, source), ...): hashable, so loads can be cached
    extra: tuple = field(default_factory=tuple)     # extra product catalogues, e.g. ("cadusa",): data/raw/products_<name>/


def load_config(path: Path | str | None = None) -> Config:
    path = Path(path) if path else ROOT / "harness.toml"
    d = tomllib.loads(path.read_text()).get("data", {})
    return Config(
        data_dir=ROOT / d.get("dir", "data/raw"),
        base_currency=d.get("base_currency", "CAD").upper(),
        calendar=d.get("calendar", "weekdays"),
        start=d.get("start", "") or "",
        proxies=tuple(sorted((d.get("proxies") or {}).items())),
        extra=tuple(d.get("extra") or ()),
    )


def _read(name: str, cfg: Config | None = None, **kw) -> pd.DataFrame:
    cfg = cfg or load_config()
    p = cfg.data_dir / name
    if not p.exists():
        raise SystemExit(f"{p} missing: run `make data` first.")
    return pd.read_csv(p, **kw)


def extra_dir(name: str, cfg: Config | None = None) -> Path:
    """Where `scripts/build_products.py` writes a catalogue's files."""
    return (cfg or load_config()).data_dir / f"products_{name}"


def _with_extras(name: str, cfg: Config, **kw) -> pd.DataFrame:
    """The starter's file plus the same file of every catalogue in `extra`. A ticker may appear in one only."""
    frames = [_read(name, cfg, **kw)]
    for e in cfg.extra:
        p = extra_dir(e, cfg) / name
        if not p.exists():
            raise SystemExit(f"{p} missing: run `make data-products` (harness.toml [data] extra = {list(cfg.extra)}).")
        frames.append(pd.read_csv(p, **kw))
    if len(frames) == 1:
        return frames[0]
    if name == "assets_universe.csv":
        seen = pd.concat([f["ticker"] for f in frames])
        dup = sorted(seen[seen.duplicated()].unique())
        if dup:
            raise ValueError(f"ticker(s) in more than one catalogue: {', '.join(dup)}")
    return pd.concat(frames, ignore_index=True)


@lru_cache(maxsize=1)
def universe() -> pd.DataFrame:
    return _with_extras("assets_universe.csv", load_config())


@lru_cache(maxsize=1)
def prices() -> pd.DataFrame:
    return _with_extras("prices_daily.csv", load_config(), parse_dates=["date"])


@lru_cache(maxsize=1)
def fx() -> pd.Series:
    """CAD per 1 USD, indexed by date."""
    return _read("fx_usdcad_daily.csv", parse_dates=["date"]).set_index("date")["usdcad"]


def corporate_actions() -> pd.DataFrame:
    return _with_extras("corporate_actions.csv", load_config(), parse_dates=["ex_date"])


def macro(series_id: str | None = None) -> pd.DataFrame:
    """Long format. Monthly series are dated by reference month, NOT release date: lag them
    before using them in any simulation (no look-ahead)."""
    m = _read("macro_rates.csv", parse_dates=["date"])
    return m[m.series_id == series_id] if series_id else m


@lru_cache(maxsize=4)
def _panel(cfg: Config) -> pd.DataFrame:
    """adj_close of the whole universe in base currency, on one calendar (cached: every agent reuses it)."""
    wide = prices().pivot(index="date", columns="ticker", values="adj_close").sort_index()
    if cfg.calendar == "weekdays":
        wide = wide[wide.index.day_of_week < 5]
    if cfg.start:
        wide = wide[wide.index >= pd.Timestamp(cfg.start)]
    wide = wide.ffill()  # holidays and gaps carry the last price forward; before the first price stays NaN
    # FX: carried forward only. No backward fill: a USD price before the first FX quote has no CAD value (NaN),
    # instead of being converted at a rate from the future.
    rate = fx().reindex(wide.index.union(fx().index)).sort_index().ffill().reindex(wide.index)
    ccy = universe().set_index("ticker")["currency"]
    unknown = sorted({f"{t} ({ccy.get(t)})" for t in wide.columns if ccy.get(t) not in ("CAD", "USD")})
    if unknown:  # never leave a price unconverted: it would be read as CAD
        raise ValueError(f"no CAD conversion for: {', '.join(unknown)} (only CAD and USD are supported)")
    for t in wide.columns:
        if ccy[t] == "USD" and cfg.base_currency == "CAD":
            wide[t] = wide[t] * rate
        elif ccy[t] == "CAD" and cfg.base_currency == "USD":
            wide[t] = wide[t] / rate
    return wide


def price_panel(tickers=None, cfg: Config | None = None) -> pd.DataFrame:
    """adj_close, one column per ticker, converted to base currency, on a common calendar.

    The calendar is always the whole universe's, then the tickers are selected (decision #15): SPY gets the same
    rows, so the same numbers, whether it is loaded alone or with 30 other assets.
    """
    wide = _panel(cfg or load_config())
    if tickers is not None:
        wide = wide.loc[:, wide.columns.isin(list(tickers))]
    return wide.copy()


def _cash_returns(index: pd.DatetimeIndex) -> pd.Series:
    """Daily return of cash at the Bank of Canada overnight target (V39079, % a year), on the given calendar."""
    m = macro("V39079").set_index("date")["value"].sort_index()
    rate = m.reindex(index.union(m.index)).ffill().reindex(index) / 100
    days = index.to_series().diff().dt.days.fillna(1).clip(lower=1)
    return (1 + rate) ** (days / 365.25) - 1


@lru_cache(maxsize=4)
def _returns(cfg: Config) -> tuple[pd.DataFrame, tuple]:
    r = _panel(cfg).pct_change(fill_method=None).iloc[1:]
    used = []
    for t, src in cfg.proxies:
        if t not in r.columns or r[t].notna().all():
            continue
        first = r[t].first_valid_index()
        before = r.index < first if first is not None else slice(None)
        try:
            fill = _cash_returns(r.index) if src == "cash" else r[src] if src in r.columns else None
        except SystemExit:  # macro file missing: no cash stand-in
            fill = None
        if fill is None:
            continue
        r.loc[before, t] = fill[before]
        filled = r.loc[before, t].dropna()
        if len(filled):
            used.append(f"{t} before {first.date()}: {'Bank of Canada overnight rate (cash)' if src == 'cash' else src} "
                        f"stands in ({filled.index[0].date()} to {filled.index[-1].date()})")
    return r, tuple(used)


def returns(tickers=None, cfg: Config | None = None) -> pd.DataFrame:
    """Daily simple returns in base currency. NaN before an asset's first price (unless a harness stand-in applies)."""
    r, _ = _returns(cfg or load_config())
    if tickers is not None:
        r = r.loc[:, r.columns.isin(list(tickers))]
    return r.copy()


def proxies_used(cfg: Config | None = None) -> list[str]:
    """Which stand-ins `returns()` applied, for `market_facts` assumptions and the trace. [] on the starter pack."""
    try:
        return list(_returns(cfg or load_config())[1])
    except SystemExit:
        return []


def period(rets: pd.DataFrame | None = None) -> tuple[str, str] | None:
    """(first, last) date of the returns used: the given ones, else the loaded data; None if no data."""
    try:
        r = price_panel() if rets is None else rets   # prices: the window starts at the first price, not return
    except SystemExit:
        return None
    r = r.dropna(how="all")
    return (r.index[0].date().isoformat(), r.index[-1].date().isoformat()) if len(r) else None


def period_label(rets: pd.DataFrame | None = None) -> str:
    """'2021-2026' style label for texts, from the data actually used (DEFAULT_LABEL without data)."""
    p = period(rets)
    return f"{p[0][:4]}-{p[1][:4]}" if p else DEFAULT_LABEL
