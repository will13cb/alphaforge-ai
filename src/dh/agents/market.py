"""Market data (layer 2): DETERMINISTIC code, not an AI agent. No LLM runs here or touches these numbers.

"Agent" in the folder name = a step of the pipeline. The LLM agents (Will's Strands Critic, Analyst; decision #14)
only CALL the functions in `AGENT_TOOLS` below as tools: same inputs, same numbers, whoever calls them.

Ingestion and cleaning come from `dh.data` (adj_close, base currency, common calendar). This agent turns
them into the facts the other agents read:

- `asset_summary`   one row per asset: return, volatility, Sharpe, max drawdown (same numbers as `make check`,
                    from dh.metrics), plus CVaR 95%, worst 12 months, calendar 2022 and the 2022 stress window
- `strategy_stats`  the same measures for a weighted portfolio, in the `stats` format the Guardian reads
                    (G7 max drawdown, G8 volatility, G12 numbers traced)
- `correlations`    correlation matrix and the most correlated pairs (two assets can be one bet)
- `macro_snapshot`  latest value of each macro series (dated by reference month, not release date)
- `market_facts`    all of the above as one JSON-ready dict, with sources, assumptions and limits
- `describe`        the plain-language hand-off line for the trace

Maths: `dh.quant_toolkit` (erk.py + evaluation.py, fixed and extended). Every function takes `rets`
(daily returns, one column per ticker) so it runs on fake data; with rets=None it loads the starter CSVs.

    from dh.agents.market import market_facts, strategy_stats
    facts = market_facts(["XIU.TO", "SPY", "XBB.TO", "GLD"])
    stats = strategy_stats({"XBB.TO": .5, "XIU.TO": .3, "GLD": .2})   # → strategy["stats"]
"""

from __future__ import annotations

import pandas as pd

from .. import data, metrics
from .. import quant_toolkit as qt

CVAR_LEVEL = 5  # % tail → CVaR 95%
STRESS_2022 = {"rate_hikes_2022": ("2022-01-03", "2022-10-12")}  # S&P 500 peak to trough, indicative
# Other S&P 500 peak-to-trough windows (decision #31), used only when the data covers them (longer history):
# stats get `stress_2008` / `stress_2020` (+ `_drawdown`) keys then, and nothing on the 2021-2026 starter pack.
STRESS_MORE = {"2008": ("2007-10-09", "2009-03-09"), "2020": ("2020-02-19", "2020-03-23")}

_SOURCES = [
    {"data": "daily prices, corporate actions", "source": "Yahoo Finance via yfinance (organizers' build script)",
     "terms": "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html"},
    {"data": "USD/CAD, Canadian rates and CPI", "source": "Bank of Canada Valet API (FRED DEXCAUS for USD/CAD before "
     "the Bank of Canada series starts, if the long build was used)", "terms": "https://www.bankofcanada.ca/terms/"},
    {"data": "U.S. rates, CPI, unemployment", "source": "FRED, Federal Reserve Bank of St. Louis",
     "terms": "https://fred.stlouisfed.org/legal/"},
]


def sources(rets: pd.DataFrame | None = None) -> list[dict]:
    """Data sources with the window actually used (starter pack 2021-2026, or the long build, decision #31)."""
    p = data.period(rets)
    win = f"{p[0]} to {p[1]}" if p else "2021-11-12 to 2026-11-12"
    return [{**s, "window": win} for s in _SOURCES]


ASSUMPTIONS = [
    "Daily simple returns on adj_close (dividends and splits included).",
    "Everything converted to the base currency in harness.toml at the Bank of Canada USD/CAD rate.",
    "Weekday calendar: crypto weekends dropped, holidays carried forward with the last price.",
    "Country = country of listing (TSX → Canada; NYSE, NASDAQ, Cboe → United States); for an ETF, where it is "
    "listed, not a breakdown of its holdings.",
    "Annualised with the rows per year observed in the dates (about 261 on the weekday calendar), not a fixed 252;"
    " Sharpe against cash (ZST.TO's average return over the same data), so cash scores about 0.",
    f"CVaR {100 - CVAR_LEVEL}% = average daily loss on the worst {CVAR_LEVEL}% of days.",
    "Portfolios are rebalanced daily to fixed weights (dh.metrics.portfolio_returns).",
    "2022 stress window = S&P 500 peak to trough, 2022-01-03 to 2022-10-12 (indicative dates); with a longer history"
    " also 2007-10-09 to 2009-03-09 and 2020-02-19 to 2020-03-23.",
    "A strategy's numbers use only the days on which every asset it holds has a price: its window starts at its "
    "youngest holding (stand-ins before an asset's first price are listed below when used).",
]

LIMITS = [
    "Past returns do not predict future returns; these numbers describe the data window only (see period).",
    "Survivorship bias: the universe was picked in 2026 from names that are large today.",
    "Monthly macro data is dated by reference month, not release date: never use a value in a simulation "
    "before it was published.",
    "No ESG, news or fundamentals in the starter data.",
    "Five years of history: tail measures (CVaR, worst 12 months) rest on few crises.",
]


# ---- helpers -------------------------------------------------------------------------------------

def _rets(rets: pd.DataFrame | None, tickers) -> pd.DataFrame:
    if rets is None:
        return data.returns(tickers)
    return rets[list(tickers)] if tickers is not None else rets


# Country of listing, from the `market` column of assets_universe.csv (C2 geography check, system-design).
COUNTRY_OF_MARKET = {"TSX": "Canada", "NASDAQ": "United States", "NYSE": "United States",
                     "NYSE Arca": "United States", "Cboe BZX": "United States", "Crypto (24/7)": "Global (crypto)"}


def country_of(ticker: str, market: str | None = None) -> str:
    """Country of listing: from the exchange when known, else from the ticker (".TO" → Canada, "-USD" → crypto,
    anything else in the starter universe is U.S.-listed). For an ETF this is where it is listed (XIU.TO Canada,
    SPY United States), not a breakdown of its holdings."""
    if market in COUNTRY_OF_MARKET:
        return COUNTRY_OF_MARKET[market]
    if ticker.endswith(".TO"):
        return "Canada"
    if ticker.endswith("-USD"):
        return "Global (crypto)"
    return "United States"


def countries(tickers=None) -> dict[str, str]:
    """{ticker: country of listing}. Works without the starter CSVs (falls back on the ticker)."""
    try:
        u = data.universe().set_index("ticker")["market"]
    except SystemExit:
        u = pd.Series(dtype=object)
    names = list(tickers) if tickers is not None else list(u.index)
    return {t: country_of(t, u.get(t)) for t in names}


def exposures(tickers=None) -> dict[str, str]:
    """{ticker: where the holdings are}: a catalogue's `exposure` (dh.products, e.g. XEF.TO → Developed ex-North
    America) when it has one, else the country of listing. Identical to `countries` for the starter's 31."""
    from .. import products
    exp = products.column_map("exposure")
    return {t: exp.get(t) or c for t, c in countries(tickers).items()}


def _meta() -> pd.DataFrame | None:
    try:
        u = data.universe().set_index("ticker")
        out = u[["name", "asset_class", "currency", "sector"]].copy()
        out["country"] = [country_of(t, m) for t, m in u["market"].items()]
        if "exposure" in u.columns:  # extra catalogues (dh.products): where the holdings are, not where it is listed
            out["exposure"] = u["exposure"].where(u["exposure"].notna(), None)
        return out
    except SystemExit:  # starter CSVs not there (tests, fresh clone)
        return None


def _stats(r: pd.Series) -> dict:
    """All measures for one return series. Fractions only (0.12 = 12%), so the Guardian can trace them."""
    r = r.dropna()
    year = r[r.index.year == 2022]
    stress = qt.scenario_analysis(r, STRESS_2022)
    ppy = round(metrics.periods_per_year(r))
    w12 = qt.worst_rolling_return(r, ppy, horizon_years=1.0) if len(r) > ppy else {}
    return {
        "ann_return": metrics.ann_return(r),
        "ann_vol": metrics.ann_vol(r),
        "max_drawdown": metrics.max_drawdown(r),
        f"cvar_{100 - CVAR_LEVEL}": qt.cvar_historic(r, CVAR_LEVEL) if len(r) > 1 else None,
        "worst_12m": w12.get("pire"),
        "return_2022": float((1 + year).prod() - 1) if len(year) else None,
        "stress_2022": float(stress["rendement_cumule"].iloc[0]) if len(stress) else None,
        "stress_2022_drawdown": float(stress["pire_baisse_dans_fenetre"].iloc[0]) if len(stress) else None,
        **_more_stress(r),
    }


def _more_stress(r: pd.Series) -> dict:
    """2008 and 2020 sell-offs, only when the series covers the whole window (no key at all otherwise)."""
    out = {}
    for name, (a, b) in STRESS_MORE.items():
        if len(r) and r.index[0] <= pd.Timestamp(a) and r.index[-1] >= pd.Timestamp(b):
            sc = qt.scenario_analysis(r, {name: (a, b)})
            if len(sc):
                out[f"stress_{name}"] = float(sc["rendement_cumule"].iloc[0])
                out[f"stress_{name}_drawdown"] = float(sc["pire_baisse_dans_fenetre"].iloc[0])
    return out


# ---- tools ---------------------------------------------------------------------------------------

def cash_rate(rets: pd.DataFrame | None = None) -> float:
    """Annual return of cash = ZST.TO's average over the data (the risk-free rate for Sharpe, audit P9). 0 if absent."""
    try:
        z = rets["ZST.TO"] if rets is not None and "ZST.TO" in rets else data.returns(["ZST.TO"])["ZST.TO"]
        return metrics.ann_return(z.dropna())
    except (KeyError, SystemExit):
        return 0.0


def asset_summary(tickers=None, rets: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per asset: metadata (if the starter CSVs are there), period, Sharpe and every _stats measure.
    Sharpe is measured against cash (ZST.TO's average, `cash_rate`), so cash itself scores ~0 (was 6.03 with rf = 0)."""
    rf = cash_rate(rets)
    rets = _rets(rets, tickers)
    rows = {}
    for c in rets.columns:
        r = rets[c].dropna()
        rows[c] = {"start": r.index[0].date().isoformat(), "end": r.index[-1].date().isoformat(),
                   "n_obs": len(r), "sharpe": metrics.sharpe(r, rf=rf), **_stats(r)}
    out = pd.DataFrame(rows).T
    meta = _meta()
    if meta is not None:
        out = meta.reindex(out.index).join(out)
    out.index.name = "ticker"
    return out


def strategy_stats(weights: dict[str, float], rets: pd.DataFrame | None = None) -> dict:
    """Stats of a fixed-weight portfolio, ready for strategy["stats"] (Guardian G7, G8, G12)."""
    rets = _rets(rets, list(weights))
    port = metrics.portfolio_returns(rets, weights)
    return _stats(port)


def goal_outlook(weights: dict[str, float], *, capital: float, horizon_years: float, monthly_contribution: float = 0.0,
                 target_amount: float | None = None, n_scenarios: int = 2000, seed: int = 0,
                 rets: pd.DataFrame | None = None, premium: float | None = None,
                 inflation: float | None = None) -> dict:
    """Range of simulated outcomes for a strategy over the profile's horizon (contract §1 goal fields).

    Stationary block bootstrap of the strategy's own daily history (no distribution assumed, fixed seed: same inputs,
    same numbers), run twice:
    - "replay": the data window's days as they were, including that period's (strong) average return;
    - "risk_only": same days with the average return replaced by cash (ZST.TO's average): keeps the swings, drops
      the historical drift. This is the one to lead with: it does not assume past returns repeat (#9).
    - "central" (decision R3): same days, average = cash + growth share × `premium` (rules.CENTRAL_PREMIUM, 3% a year
      on the growth part only). The view the goal is sized with (dh.risk.goals): risk_only has no premium, so more
      stocks can only add variance there (audit A2).
    Each gives prob_loss (share ending below the total invested; NOT a risk of ruin), prob_target (None without
    target_amount), prob_target_real (the target in today's dollars, `inflation` a year, decision R9) and
    final_p5 / final_p50 / final_p95 in nominal CAD.
    """
    from .rules import CENTRAL_PREMIUM, DEFENSIVE, INFLATION
    premium = CENTRAL_PREMIUM if premium is None else premium
    inflation = INFLATION if inflation is None else inflation
    all_rets = _rets(rets, None)
    port = metrics.portfolio_returns(all_rets[list(weights)], weights).dropna()
    cash = all_rets["ZST.TO"].reindex(port.index).dropna().mean() if "ZST.TO" in all_rets else 0.0
    ppy = metrics.periods_per_year(port)
    n = max(1, round(horizon_years * ppy))
    every = max(1, round(ppy / 12))
    target = target_amount if target_amount else max(capital, 1.0)  # placeholder when no target; prob_target dropped

    base = qt.bootstrap_paths(port, n_periods=n, n_scenarios=n_scenarios, seed=seed)  # drawn once for all views

    def run(shift: float) -> dict:
        """The views differ only by a constant daily shift of the mean: same days, same paths (fixed seed)."""
        paths = base + shift
        g = qt.goal_probability(paths, initial=capital, target=target, contribution=monthly_contribution,
                                contribution_every=every)
        real = qt.goal_probability(paths, initial=capital, target=target, contribution=monthly_contribution,
                                   contribution_every=every, inflation=inflation,
                                   periods_per_year=max(1, round(ppy))) if target_amount else None
        q = g["richesse_finale_quantiles"]
        return {"prob_loss": g["probabilite_sous_total_investi"],
                "prob_target": g["probabilite_atteinte"] if target_amount else None,
                "prob_target_real": real["probabilite_atteinte"] if real else None,
                "final_p5": q["p5"], "final_p50": q["p50"], "final_p95": q["p95"]}

    growth = sum(w for t, w in weights.items() if t not in DEFENSIVE) / (sum(weights.values()) or 1.0)

    total = capital + monthly_contribution * len(range(0, n, every))
    lab = data.period_label(port.to_frame())
    return {"horizon_years": horizon_years, "n_scenarios": n_scenarios, "total_invested": total,
            "target_amount": target_amount, "replay": run(0.0), "risk_only": run(cash - port.mean()),
            "central": run(cash - port.mean() + growth * premium / ppy),
            "cash_return_used": float((1 + cash) ** ppy - 1), "premium_used": premium, "growth_share": growth,
            "inflation_used": inflation,
            "method": f"stationary block bootstrap of the strategy's {lab} daily returns, fixed seed",
            "limits": f"Replays past days only: no crisis worse than {lab}, no fees or taxes. Not a forecast; "
                      f"'replay' assumes {lab} average returns repeat, 'risk_only' assumes no premium over cash, "
                      f"'central' a {premium:.0%} premium on the growth part (an assumption, not an estimate)."}


def correlations(tickers=None, rets: pd.DataFrame | None = None, top: int = 5) -> dict:
    """Pearson matrix, average correlation and the most correlated pairs."""
    rets = _rets(rets, tickers)
    rep = qt.correlation_report(rets, round(metrics.periods_per_year(rets.dropna(how="all"))), top=top)
    return {"pearson": rep["pearson"].round(3).to_dict(), "average": rep["correlation_moyenne"],
            "top_pairs": rep["paires_les_plus_correlees"], "n_obs": rep["n_obs"]}


def data_quality(tickers=None, rets: pd.DataFrame | None = None) -> dict:
    """Per asset: usable or not, and alerts (frozen prices, gaps, extreme moves, suspicious round trips)."""
    rets = _rets(rets, tickers)
    return {c: {"usable": q["utilisable"], "alerts": q["alertes"]}
            for c in rets.columns for q in [qt.data_quality(rets[c], kind="returns")]}


def macro_snapshot() -> pd.DataFrame:
    """Latest value of each macro series (see LIMITS: reference month, not release date)."""
    m = data.macro().sort_values("date")
    return m.groupby("series_id").tail(1).set_index("series_id")[["date", "value", "unit", "frequency", "label", "source"]]


def market_facts(tickers=None, rets: pd.DataFrame | None = None, include_macro: bool = True) -> dict:
    """Everything this agent hands to Portfolio, Critic, Guardian and Explainer, as one JSON-ready dict
    (goes into the trace store as is)."""
    rets = _rets(rets, tickers)
    macro = None
    if include_macro:
        try:
            macro = macro_snapshot().reset_index().to_dict(orient="records")
        except SystemExit:
            pass
    return qt.to_jsonable({
        "agent": "Market data",
        "base_currency": data.load_config().base_currency,
        "period": {"start": rets.index[0].date().isoformat(), "end": rets.index[-1].date().isoformat()},
        "assets": asset_summary(rets=rets).reset_index().to_dict(orient="records"),
        "correlations": correlations(rets=rets) if rets.shape[1] > 1 else None,
        "quality": data_quality(rets=rets),
        "macro": macro,
        "sources": sources(rets),
        "assumptions": ASSUMPTIONS + data.proxies_used(),
        "limits": LIMITS,
    })


def describe(facts: dict) -> str:
    """Market data → Portfolio hand-off, in words (for Trace.step)."""
    a = facts["assets"]
    bad = [t for t, q in facts["quality"].items() if not q["usable"]]
    s = (f"{len(a)} assets, {facts['period']['start']} to {facts['period']['end']}, in {facts['base_currency']}. "
         f"Per asset: return, volatility, max drawdown, CVaR 95%, worst 12 months, 2022.")
    worst = min(a, key=lambda x: x["max_drawdown"])
    s += f" Deepest drawdown: {worst['ticker']} {worst['max_drawdown']:.0%}."
    c = facts.get("correlations")
    if c and c["top_pairs"]:
        p = c["top_pairs"][0]
        s += f" Most correlated pair: {p['a']}/{p['b']} ({p['correlation']:.3f})."
    if bad:
        s += f" Unusable data: {', '.join(bad)}."
    return s


def tools(category: str | None = None) -> pd.DataFrame:
    """Catalogue of the toolkit functions (name, category, data needed, description)."""
    return qt.list_tools(category)


# ---- tools for the LLM agents (decisions #14, #15) -------------------------------------------------
# Deterministic functions that Will's Strands agents (Critic, Analyst) may CALL; no LLM inside. They take simple
# JSON arguments and give compact JSON-ready output, floats rounded to 4 decimals, and errors returned as {"error": ...} instead of raised, so the agent can read
# them and recover (e.g. "XSP is not in the universe"). Will wraps them with strands' @tool in his lane;
# this module does not import strands. Docstrings are Google style: Strands reads them as the tool description.

_TOOL_RETS: pd.DataFrame | None = None


def _tool_rets() -> pd.DataFrame:
    global _TOOL_RETS
    if _TOOL_RETS is None:
        _TOOL_RETS = data.returns()
    return _TOOL_RETS


def _round(x, nd: int = 4):
    x = qt.to_jsonable(x)
    if isinstance(x, float):
        return round(x, nd)
    if isinstance(x, dict):
        return {k: _round(v, nd) for k, v in x.items()}
    if isinstance(x, list):
        return [_round(v, nd) for v in x]
    return x


def _check_tickers(tickers, rets: pd.DataFrame) -> dict | None:
    unknown = [t for t in tickers if t not in rets.columns]
    if unknown:
        return {"error": f"not in the {rets.shape[1]}-asset starter universe: {', '.join(unknown)}. "
                         "No data for them; call list_assets for what is available, or say it cannot be assessed.",
                "available": sorted(rets.columns)}
    return None


def _check_weights(weights: dict, rets: pd.DataFrame) -> dict | None:
    if not isinstance(weights, dict) or not weights:
        return {"error": "weights must be a non-empty object {ticker: weight}, e.g. {\"SPY\": 0.6, \"XBB.TO\": 0.4}"}
    bad = _check_tickers(weights, rets)
    if bad:
        return bad
    if any(not isinstance(v, (int, float)) or v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
        return {"error": "weights must be non-negative numbers with a positive sum (no short positions)"}
    return None


def _norm(weights: dict) -> dict:
    s = sum(weights.values())
    return {t: round(v / s, 4) for t, v in weights.items()}


def list_assets() -> dict:
    """List the assets that have data: ticker, name, asset class, currency, sector, country of listing.

    Returns:
        {"assets": [...], "base_currency": "CAD", "period": {"start", "end"}}.
    """
    rets = _tool_rets()
    meta = _meta()
    rows = (meta.reindex(rets.columns).reset_index().rename(columns={"index": "ticker"}).to_dict(orient="records")
            if meta is not None else [{"ticker": t} for t in rets.columns])
    return _round({"assets": rows, "base_currency": data.load_config().base_currency,
                   "period": {"start": rets.index[0].date().isoformat(), "end": rets.index[-1].date().isoformat()}})


def asset_facts(tickers: list[str]) -> dict:
    """Historical facts for some assets over the data window (list_assets gives the period), in the base currency.

    Args:
        tickers: tickers from list_assets, e.g. ["TSLA", "SPY"].

    Returns:
        One entry per ticker: name, asset_class, currency, sector, country (of listing), then
        ann_return, ann_vol, sharpe, max_drawdown (<= 0), cvar_95 (positive daily loss),
        worst_12m, return_2022, stress_2022, stress_2022_drawdown. All fractions (0.12 = 12%). Past, not a forecast.
    """
    rets = _tool_rets()
    err = _check_tickers(tickers, rets)
    if err:
        return err
    s = asset_summary(rets=rets[list(tickers)]).drop(columns=["start", "end", "n_obs"], errors="ignore")
    return _round({"assets": s.reset_index().to_dict(orient="records"), "limits": LIMITS[0]})


def portfolio_stats(weights: dict[str, float]) -> dict:
    """Historical stats of a fixed-weight portfolio rebalanced daily (what Portfolio puts in strategy["stats"]).

    Args:
        weights: {ticker: weight}; normalised to sum to 1, no negatives. E.g. {"SPY": 0.6, "XBB.TO": 0.4}.

    Returns:
        weights used, ann_return, ann_vol, max_drawdown (<= 0), cvar_95, worst_12m, return_2022, stress_2022,
        stress_2022_drawdown (+ stress_2008 / stress_2020 when the history covers them). Fractions. Describes
        the past, not a forecast.
    """
    rets = _tool_rets()
    err = _check_weights(weights, rets)
    if err:
        return err
    return _round({"weights": _norm(weights), **strategy_stats(weights, rets=rets)})


def stress_test(weights: dict[str, float], start: str = "2022-01-03", end: str = "2022-10-12") -> dict:
    """How a portfolio behaved inside a historical window (default: the 2022 rate-hike sell-off).

    Args:
        weights: {ticker: weight}, normalised to sum to 1.
        start: first day of the window, YYYY-MM-DD, inside the data period (list_assets gives it).
        end: last day of the window, YYYY-MM-DD.

    Returns:
        cumulative_return over the window and deepest_drop inside it (both fractions, <= 0 for a loss).
    """
    rets = _tool_rets()
    err = _check_weights(weights, rets)
    if err:
        return err
    try:
        s, e = pd.Timestamp(start), pd.Timestamp(end)
    except ValueError:
        return {"error": "start and end must be dates YYYY-MM-DD"}
    if not (rets.index[0] <= s < e <= rets.index[-1]):
        return {"error": f"window must satisfy {rets.index[0].date()} <= start < end <= {rets.index[-1].date()}"}
    port = metrics.portfolio_returns(rets, weights)
    res = qt.scenario_analysis(port, {"window": (start, end)})
    return _round({"weights": _norm(weights), "start": start, "end": end,
                   "cumulative_return": float(res["rendement_cumule"].iloc[0]),
                   "deepest_drop": float(res["pire_baisse_dans_fenetre"].iloc[0])})


def correlation_between(tickers: list[str]) -> dict:
    """Daily-return correlations between a few assets (are they really diversifying?).

    Args:
        tickers: 2 to 10 tickers, e.g. ["QQQ", "NVDA", "SPY"].

    Returns:
        pairs sorted from most to least correlated (-1 to 1), and their average. Above ~0.8 = largely the same bet.
    """
    rets = _tool_rets()
    if not isinstance(tickers, list) or not 2 <= len(tickers) <= 10:
        return {"error": "give 2 to 10 tickers"}
    err = _check_tickers(tickers, rets)
    if err:
        return err
    c = rets[list(tickers)].dropna().corr()
    pairs = sorted(({"a": a, "b": b, "correlation": float(c.loc[a, b])}
                    for i, a in enumerate(tickers) for b in tickers[i + 1:]), key=lambda p: -p["correlation"])
    return _round({"pairs": pairs, "average": sum(p["correlation"] for p in pairs) / len(pairs)}, 3)


def goal_check(weights: dict[str, float], capital: float, horizon_years: float, monthly_contribution: float = 0.0,
               target_amount: float | None = None) -> dict:
    """Chance of ending below what was invested, and of reaching a target, over the client's horizon.

    Args:
        weights: {ticker: weight}, normalised to sum to 1.
        capital: starting amount in the base currency (CAD).
        horizon_years: years until the money is needed (0.5 to 40).
        monthly_contribution: amount added each month, CAD.
        target_amount: amount the client wants at the horizon, CAD (optional).

    Returns:
        risk_only (lead with this: the past swings with a cash-like average return) and replay (the data window as it was,
        optimistic), each with prob_loss, prob_target, final_p5/p50/p95. Simulation, not a forecast.
    """
    rets = _tool_rets()
    err = _check_weights(weights, rets)
    if err:
        return err
    if not 0.5 <= horizon_years <= 40 or capital < 0 or monthly_contribution < 0 or (capital == 0 and not monthly_contribution):
        return {"error": "need 0.5 <= horizon_years <= 40, capital >= 0, monthly_contribution >= 0, and money to invest"}
    out = goal_outlook(weights, capital=capital, horizon_years=horizon_years, monthly_contribution=monthly_contribution,
                       target_amount=target_amount, n_scenarios=1000, rets=rets)
    return _round({"weights": _norm(weights), **out}, 4)


def _future_value(r: float, capital: float, monthly: float, months: int) -> float:
    """Capital and monthly contributions (start of each month, as in goal_outlook) grown at a yearly rate r."""
    g = (1 + r) ** (1 / 12)
    return capital * g ** months + monthly * sum(g ** (months - k) for k in range(months))


def required_return(capital: float, horizon_years: float, target_amount: float, monthly_contribution: float = 0.0,
                    rets: pd.DataFrame | None = None) -> dict:
    """Yearly return the goal needs, next to what cash pays today (asked by Will for the goal floor, decision #17).

    Args:
        capital: amount invested today, CAD.
        horizon_years: years until the money is needed (0.5 to 40).
        target_amount: amount wanted at the horizon, CAD.
        monthly_contribution: added at the start of each month, CAD.

    Returns:
        required (yearly, fraction; <= 0 means contributions alone reach it), total_invested, and for comparison
        cash_last_12m (ZST.TO, realised) and boc_overnight (Bank of Canada policy rate, latest, with its date).
        A deterministic calculation: it says what the goal needs, not what any asset will earn.
    """
    if not target_amount or target_amount <= 0:
        return {"error": "target_amount must be a positive amount in CAD"}
    if not 0.5 <= horizon_years <= 40 or capital < 0 or monthly_contribution < 0 or (capital == 0 and not monthly_contribution):
        return {"error": "need 0.5 <= horizon_years <= 40, capital >= 0, monthly_contribution >= 0, and money to invest"}
    months = int(round(12 * horizon_years))
    invested = capital + monthly_contribution * months
    f = lambda r: _future_value(r, capital, monthly_contribution, months) - target_amount
    lo, hi = -0.99, 1.0
    if f(hi) < 0:
        req = None  # even 100% a year is not enough
    else:
        for _ in range(200):  # bisection: f is increasing in r
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
        req = (lo + hi) / 2
    out = {"required": req, "target_amount": target_amount, "total_invested": invested, "horizon_years": horizon_years,
           "method": "yearly rate r such that capital and start-of-month contributions grown at r reach the target"}
    try:
        r = _tool_rets() if rets is None else rets
        z = r["ZST.TO"].dropna().iloc[-round(metrics.periods_per_year(r["ZST.TO"])):]
        out["cash_last_12m"] = float((1 + z).prod() - 1)
        m = macro_snapshot().loc["V39079"]
        out["boc_overnight"] = float(m["value"]) / 100
        out["boc_overnight_date"] = str(pd.Timestamp(m["date"]).date())
    except (SystemExit, KeyError):
        pass
    if req is None:
        out["reading"] = "out of reach: even 100% a year would not get there"
    elif req <= 0:
        out["reading"] = "reached without any return: what is put in already covers the target"
    elif "cash_last_12m" in out and req <= out["cash_last_12m"]:
        out["reading"] = "cash-like returns have been enough over the last 12 months; no need to take stock risk for it"
    else:
        out["reading"] = "needs more than cash has paid: the gap has to come from riskier assets, with their drops"
    return _round(out)


def dividend_facts(tickers: list[str]) -> dict:
    """Is a company's dividend covered by what it earns? Payout ratio and coverage from its annual statements.

    Args:
        tickers: 1 to 10 stock tickers, e.g. ["ENB.TO", "RY.TO"]. A fund gets its distribution yield only.

    Returns:
        per ticker: status (covered / thin / not covered / loss / no dividend / fund / no data) and why; dividends per
        share over the last 12 months, yield, yearly dividends, growth and cuts (from our price files); payout ratio =
        dividends paid / net income to common shareholders, for the last fiscal year and the last 3 together (the
        status uses the 3 years), earnings and free-cash-flow coverage (from the statements); sector caveats.
        Snapshot, not a forecast.
    """
    from .. import fundamentals
    if not isinstance(tickers, list) or not 1 <= len(tickers) <= 10:
        return {"error": "give 1 to 10 tickers"}
    return _round({"companies": [fundamentals.dividend_facts(str(t)) for t in tickers],
           "rule": f"on the last {fundamentals.YEARS} fiscal years together: covered if earnings >= "
                           f"{fundamentals.COVERAGE_THIN:g}x dividends; thin {fundamentals.COVERAGE_MIN:g}-"
                           f"{fundamentals.COVERAGE_THIN:g}x; not covered below {fundamentals.COVERAGE_MIN:g}x "
                           "(team rule, not a regulation); REITs not measurable without FFO"})


AGENT_TOOLS = [list_assets, asset_facts, portfolio_stats, stress_test, correlation_between, goal_check, required_return]

# Research tools (branch produit_cadusa): handed to the agents only with harness.toml [data] extra set, so the demo's
# tool list (and the tool counts quoted in the deliverables) stay as they are by default.
RESEARCH_TOOLS = [dividend_facts]


def agent_tools() -> list:
    """The tools the Strands agents get: AGENT_TOOLS, plus RESEARCH_TOOLS when an extra catalogue is configured."""
    return list(AGENT_TOOLS) + (list(RESEARCH_TOOLS) if data.load_config().extra else [])
