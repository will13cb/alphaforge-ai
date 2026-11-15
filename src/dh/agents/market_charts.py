"""Market-data charts for the app and the video. DETERMINISTIC, no LLM (decision #16).

Each chart has two functions:
- `*_data(...)`  a tidy DataFrame (testable, and the exact numbers the chart shows, so the Explainer can quote them);
- `*_chart(...)` an Altair chart built only from that DataFrame. In the app: `st.altair_chart(chart, use_container_width=True)`.

    from dh.agents import market_charts as mc
    strategies = {"Cautious": {"XBB.TO": .5, "XIU.TO": .3, "GLD": .2}, "Your request": {"TSLA": .25, "XIU.TO": .75}}
    st.altair_chart(mc.growth_chart(mc.growth_data(strategies)))

All numbers come from `dh.metrics` / `dh.agents.market` (same as the trace). Past data only (the window in data.period()), never a forecast (#9).
Altair ships with Streamlit; PNG export (`experiments/data/export_charts.py`) also needs `vl-convert-python`.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from .. import data, metrics
from .. import quant_toolkit as qt
from . import market

STRESS_START, STRESS_END = market.STRESS_2022["rate_hikes_2022"]
SOURCE_NOTE = "Starter pack (Yahoo Finance, Bank of Canada), 2021-11 to 2026-11, in CAD. Past data, not a forecast."


def source_note(rets: pd.DataFrame | None = None) -> str:
    """Caption with the window actually used (starter pack or the long build, decision #31)."""
    p = data.period(rets)
    if not p or data.period_label(rets) == data.DEFAULT_LABEL:
        return SOURCE_NOTE
    return f"Yahoo Finance and Bank of Canada data, {p[0][:7]} to {p[1][:7]}, in CAD. Past data, not a forecast."
CLASS_ORDER = ["equity", "etf_equity", "etf_bond", "etf_commodity", "crypto"]


def _rets(rets: pd.DataFrame | None) -> pd.DataFrame:
    return data.returns() if rets is None else rets


def _caption(chart: alt.Chart, title: str, note: str | None = None) -> alt.Chart:
    note = source_note() if note is None else note
    return chart.properties(title=alt.TitleParams(title, subtitle=[note], anchor="start"))


# ---- 1. growth of each strategy, 2022 shaded -----------------------------------------------------

def growth_data(strategies: dict[str, dict[str, float]], start_value: float = 100.0,
                rets: pd.DataFrame | None = None) -> pd.DataFrame:
    """Value of start_value invested in each strategy (daily rebalanced), and its drawdown, day by day."""
    rets = _rets(rets)
    rows = []
    for name, w in strategies.items():
        port = metrics.portfolio_returns(rets[list(w)], w).dropna()
        value = start_value * (1 + port).cumprod()
        rows.append(pd.DataFrame({"date": value.index, "strategy": name, "value": value.to_numpy(),
                                  "drawdown": (value / value.cummax() - 1).to_numpy()}))
    return pd.concat(rows, ignore_index=True)


def growth_chart(df: pd.DataFrame, height: int = 320) -> alt.Chart:
    band = alt.Chart(pd.DataFrame({"start": [pd.Timestamp(STRESS_START)], "end": [pd.Timestamp(STRESS_END)],
                                   "label": ["2022 sell-off"]}))
    rect = band.mark_rect(opacity=0.12, color="#b91c1c").encode(x="start:T", x2="end:T")
    text = band.mark_text(align="left", baseline="top", dx=4, dy=4, color="#b91c1c").encode(x="start:T", text="label")
    lines = alt.Chart(df).mark_line(strokeWidth=2).encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("value:Q", title=f"Value of {df['value'].iloc[0]:.0f} invested", scale=alt.Scale(zero=False)),
        color=alt.Color("strategy:N", title=None, legend=alt.Legend(orient="top")),
        tooltip=["strategy", alt.Tooltip("date:T"), alt.Tooltip("value:Q", format=".1f"),
                 alt.Tooltip("drawdown:Q", format=".1%", title="below previous peak")])
    return _caption((rect + text + lines).properties(height=height, width=620), f"How each strategy would have moved, {data.period_label()}")


# ---- 2. range of final values (goal outlook) -----------------------------------------------------

def outcome_data(weights: dict[str, float], *, capital: float, horizon_years: float, monthly_contribution: float = 0.0,
                 target_amount: float | None = None, rets: pd.DataFrame | None = None) -> pd.DataFrame:
    """p5 / p50 / p95 of the final value, risk_only and replay, from market.goal_outlook (same numbers as the trace)."""
    g = market.goal_outlook(weights, capital=capital, horizon_years=horizon_years,
                            monthly_contribution=monthly_contribution, target_amount=target_amount, rets=_rets(rets))
    label = {"risk_only": "Risk only (cash-like average)", "replay": f"Replay of {data.period_label()}"}
    return pd.DataFrame([{"scenario": label[k], "key": k, "p5": g[k]["final_p5"], "p50": g[k]["final_p50"],
                          "p95": g[k]["final_p95"], "prob_loss": g[k]["prob_loss"], "prob_target": g[k]["prob_target"],
                          "total_invested": g["total_invested"], "target_amount": target_amount,
                          "horizon_years": horizon_years} for k in ("risk_only", "replay")])


def outcome_chart(df: pd.DataFrame, height: int = 160) -> alt.Chart:
    base = alt.Chart(df).encode(y=alt.Y("scenario:N", title=None, sort=list(df["scenario"])))
    tip = ["scenario", alt.Tooltip("p5:Q", format=",.0f", title="1 in 20 worse than"),
           alt.Tooltip("p50:Q", format=",.0f", title="median"), alt.Tooltip("p95:Q", format=",.0f", title="1 in 20 better than"),
           alt.Tooltip("prob_loss:Q", format=".0%", title="chance of ending below invested")]
    rng = base.mark_rule(strokeWidth=10, opacity=0.35).encode(
        x=alt.X("p5:Q", title="Final value (CAD), 5th to 95th percentile", axis=alt.Axis(format=",.0f")), x2="p95:Q",
        tooltip=tip)
    mid = base.mark_point(filled=True, size=120, color="black").encode(x="p50:Q", tooltip=tip)
    refs = pd.DataFrame([{"x": df["total_invested"].iloc[0], "label": "invested", "align": "right", "dx": -3}]
                        + ([{"x": df["target_amount"].iloc[0], "label": "target", "align": "left", "dx": 3}]
                           if pd.notna(df["target_amount"].iloc[0]) else []))
    rules = alt.Chart(refs).mark_rule(strokeDash=[4, 3]).encode(x="x:Q")
    labels = alt.layer(*[alt.Chart(refs.iloc[[i]]).mark_text(align=r["align"], dx=r["dx"], dy=-4, baseline="bottom")
                         .encode(x="x:Q", y=alt.value(0), text="label") for i, r in refs.iterrows()])
    h = df["horizon_years"].iloc[0]
    return _caption((rng + mid + rules + labels).properties(height=height, width=620),
                    f"Range of outcomes after {h:g} years (simulation, not a forecast)",
                    "Bar: 5th to 95th percentile, dot: median. 'Risk only' keeps the past swings without assuming "
                    f"{data.period_label()} returns repeat. No fees or taxes.")


# ---- 3. correlations ------------------------------------------------------------------------------

def correlation_data(tickers: list[str] | None = None, rets: pd.DataFrame | None = None) -> pd.DataFrame:
    """Long table a, b, correlation of daily returns (a == b included, for the heatmap diagonal)."""
    r = _rets(rets)
    r = r[list(tickers)] if tickers is not None else r
    c = r.dropna().corr()
    return c.rename_axis("a").reset_index().melt(id_vars="a", var_name="b", value_name="correlation")


def correlation_chart(df: pd.DataFrame, size: int | None = None) -> alt.Chart:
    order = list(dict.fromkeys(df["a"]))
    n = len(order)
    size = size or (42 if n <= 10 else 18)
    heat = alt.Chart(df).mark_rect().encode(
        x=alt.X("a:N", sort=order, title=None, axis=alt.Axis(labelAngle=-60)),
        y=alt.Y("b:N", sort=order, title=None),
        color=alt.Color("correlation:Q", scale=alt.Scale(scheme="redblue", domain=[-1, 1], reverse=True),
                        title="corr."),
        tooltip=["a", "b", alt.Tooltip("correlation:Q", format=".2f")])
    chart = heat
    if n <= 10:
        chart = heat + alt.Chart(df).mark_text(fontSize=10).encode(
            x=alt.X("a:N", sort=order), y=alt.Y("b:N", sort=order), text=alt.Text("correlation:Q", format=".2f"),
            color=alt.condition("abs(datum.correlation) > 0.6", alt.value("white"), alt.value("black")))
    return _caption(chart.properties(width=size * n, height=size * n),
                    "Do these assets move together?", f"Daily returns {data.period_label()}. Above ~0.8: largely the same bet.")


# ---- 4. risk vs return, with the historical frontier ----------------------------------------------

def risk_return_data(strategies: dict[str, dict[str, float]] | None = None, rets: pd.DataFrame | None = None,
                     frontier_points: int = 20) -> pd.DataFrame:
    """One row per asset, per strategy and per point of the long-only historical frontier: ann_return (CAGR),
    ann_vol, kind. Frontier weights come from mean/covariance, but every point's return and volatility is
    recomputed with dh.metrics, so the whole chart uses the same measures as the trace.
    The frontier is a picture of the data window (hindsight), not how strategies are built (decision #1)."""
    rets = _rets(rets).dropna()
    meta = market._meta()
    cls = meta["asset_class"].reindex(rets.columns) if meta is not None else pd.Series(index=rets.columns, dtype=object)
    rows = [{"name": t, "kind": "asset", "group": cls[t] if pd.notna(cls[t]) else "asset",
             "ann_return": metrics.ann_return(rets[t]), "ann_vol": metrics.ann_vol(rets[t])} for t in rets.columns]
    ppy = metrics.periods_per_year(rets)
    ef = qt.efficient_frontier(rets.mean() * ppy, rets.cov() * ppy, n_points=frontier_points)
    w_cols = list(rets.columns)
    for i, row in ef["frontiere"].iterrows():
        w = {t: float(row[t]) for t in w_cols if row[t] > 1e-6}
        port = metrics.portfolio_returns(rets[list(w)], w)
        rows.append({"name": f"frontier {i + 1}", "kind": "frontier", "group": "frontier",
                     "ann_return": metrics.ann_return(port), "ann_vol": metrics.ann_vol(port)})
    for name, w in (strategies or {}).items():
        port = metrics.portfolio_returns(rets[list(w)], w)
        rows.append({"name": name, "kind": "strategy", "group": "strategy",
                     "ann_return": metrics.ann_return(port), "ann_vol": metrics.ann_vol(port)})
    return pd.DataFrame(rows)


def risk_return_chart(df: pd.DataFrame, height: int = 380) -> alt.Chart:
    enc = dict(x=alt.X("ann_vol:Q", title="Volatility (annualised)", axis=alt.Axis(format=".0%")),
               y=alt.Y("ann_return:Q", title=f"Return per year ({data.period_label()})", axis=alt.Axis(format=".0%")),
               tooltip=["name", alt.Tooltip("ann_return:Q", format=".1%"), alt.Tooltip("ann_vol:Q", format=".1%")])
    front = alt.Chart(df[df.kind == "frontier"].sort_values("ann_vol")).mark_line(color="gray", strokeDash=[5, 3]).encode(**enc)
    assets = df[df.kind == "asset"]
    pts = alt.Chart(assets).mark_circle(size=60, opacity=0.8).encode(
        color=alt.Color("group:N", title=None, sort=CLASS_ORDER, legend=alt.Legend(orient="top")), **enc)
    names = alt.Chart(assets).mark_text(align="left", dx=5, fontSize=9, color="gray").encode(text="name", **enc)
    layers = front + pts + names
    strat = df[df.kind == "strategy"]
    if len(strat):
        layers += alt.Chart(strat).mark_point(shape="diamond", size=200, filled=True, color="black").encode(**enc)
        layers += alt.Chart(strat).mark_text(align="left", dx=9, fontWeight="bold").encode(text="name", **enc)
    return _caption(layers.properties(height=height), f"Risk and return of each asset, {data.period_label()}",
                    "Dashed: best historical mixes (hindsight, unstable; not used to build strategies).")


# ---- 5. 2022 -------------------------------------------------------------------------------------

def year_2022_data(tickers: list[str] | None = None, rets: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per asset: calendar-2022 return and the deepest drop inside the 2022 sell-off window."""
    s = market.asset_summary(tickers, rets=None if rets is None else rets)
    cols = [c for c in ("name", "asset_class") if c in s.columns]
    out = s[cols + ["return_2022", "stress_2022_drawdown"]].reset_index()
    out[["return_2022", "stress_2022_drawdown"]] = out[["return_2022", "stress_2022_drawdown"]].astype(float)
    return out.sort_values("return_2022").reset_index(drop=True)


def year_2022_chart(df: pd.DataFrame, highlight: list[str] | None = None) -> alt.Chart:
    hl = set(highlight or [])
    df = df.assign(highlight=df["ticker"].isin(hl))
    color = (alt.condition("datum.highlight", alt.value("#b91c1c"), alt.value("#94a3b8")) if hl else
             alt.Color("asset_class:N", title=None, sort=CLASS_ORDER, legend=alt.Legend(orient="top"))
             if "asset_class" in df else alt.value("#64748b"))
    bars = alt.Chart(df).mark_bar().encode(
        y=alt.Y("ticker:N", sort=list(df["ticker"]), title=None),
        x=alt.X("return_2022:Q", title="Return in calendar 2022 (CAD)", axis=alt.Axis(format=".0%")),
        color=color,
        tooltip=["ticker"] + (["name"] if "name" in df else [])
        + [alt.Tooltip("return_2022:Q", format=".1%"),
           alt.Tooltip("stress_2022_drawdown:Q", format=".1%", title="deepest drop, Jan-Oct 2022")])
    return _caption(bars.properties(height=max(120, 14 * len(df))), "What 2022 did to each asset")


# ---- helpers --------------------------------------------------------------------------------------

def to_png(chart: alt.Chart, path, scale: float = 2.0) -> None:
    """Save a PNG for the video / one-pager (needs vl-convert-python)."""
    chart.save(str(path), format="png", scale_factor=scale)


__all__ = ["growth_data", "growth_chart", "outcome_data", "outcome_chart", "correlation_data", "correlation_chart",
           "risk_return_data", "risk_return_chart", "year_2022_data", "year_2022_chart", "to_png"]
