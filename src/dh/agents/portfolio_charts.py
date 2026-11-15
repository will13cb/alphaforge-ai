"""Portfolio charts for the app: built ONLY from a strategy the Portfolio already returned (no recomputation).

Same pattern as Joud's `market_charts.py` (decision #16): `*_data()` gives the tidy DataFrame (the exact numbers on
screen, testable), `*_chart()` draws it with Altair. Numbers come from `strategy["split_curve"]` and
`strategy["outlook"]`, which `market.strategy_stats` / `market.goal_outlook` computed, so the chart, the trace and the
Explainer quote the same values.

    from dh.agents import portfolio_charts as pc
    st.altair_chart(pc.split_curve_chart(pc.split_curve_data(s), limits, s), use_container_width=True)
    st.altair_chart(market_charts.outcome_chart(pc.outcome_frame(s)))
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from ..data import period_label
from .market_charts import source_note

OUTCOME_LABEL = {"risk_only": "Risk only (cash-like average)", "central": "Central (cash + 3% on growth assets)",
                 "replay": "Replay of the data window"}


def split_curve_data(strategy: dict) -> pd.DataFrame:
    """One row per growth share tested (0-100%, 5% steps): worst drop as a positive loss, 2022 numbers, volatility."""
    cols = ["growth", "worst_drop", "stress_2022", "return_2022", "ann_vol", "sim_drop"]
    df = pd.DataFrame(strategy.get("split_curve") or [])
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["worst_drop"] = df["max_drawdown"].abs()
    # the 1-in-10 drop over the client's horizon (simulated, decision R1): the line the ceiling is read from
    df["sim_drop"] = df["sim_drop"].abs() if "sim_drop" in df else float("nan")
    return df[cols].astype(float)


def split_curve_chart(df: pd.DataFrame, limits: dict, strategy: dict, height: int = 220, title: bool = True) -> alt.Chart:
    """Growth share vs worst historical drop, with the client's loss limit, the horizon cap and the chosen split."""
    loss = float(limits.get("loss_limit", limits.get("max_drawdown", 0.0)))
    cap = float(limits.get("horizon_max_growth", 1.0 - limits.get("min_defensive", 0.0)))
    max_share = round(1 - float(limits.get("min_defensive", 0.0)), 4)
    chosen = float(strategy["split"]["growth"])
    x = alt.X("growth:Q", title="Share in growth assets", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1]))
    y = alt.Y("worst_drop:Q", title="Worst drop", axis=alt.Axis(format=".0%"))
    tip = [alt.Tooltip("growth:Q", format=".0%", title="growth"), alt.Tooltip("worst_drop:Q", format=".1%", title="worst drop"),
           alt.Tooltip("return_2022:Q", format=".1%", title="2022 return"),
           alt.Tooltip("ann_vol:Q", format=".1%", title="volatility")]
    layers = []
    if max_share < 1:
        band = pd.DataFrame({"x": [max_share], "x2": [1.0],
                             "label": ["horizon cap" if abs(max_share - cap) < 1e-3 else "defensive floor"]})
        layers += [alt.Chart(band).mark_rect(opacity=0.10, color="#64748b").encode(x="x:Q", x2="x2:Q"),
                   alt.Chart(band).mark_text(align="left", baseline="top", dx=4, dy=4, color="#475569", fontSize=10)
                   .encode(x="x:Q", y=alt.value(0), text="label")]
    layers.append(alt.Chart(df).mark_line(point=True, color="#2563eb").encode(x=x, y=y, tooltip=tip))
    sim = df.dropna(subset=["sim_drop"]) if "sim_drop" in df else df.iloc[0:0]
    if len(sim):  # simulated over the client's horizon: the ceiling is where this line crosses the loss limit
        layers.append(alt.Chart(sim).mark_line(point=True, color="#d97706", strokeDash=[4, 2]).encode(
            x=x, y=alt.Y("sim_drop:Q"), tooltip=[alt.Tooltip("growth:Q", format=".0%", title="growth"),
                                                 alt.Tooltip("sim_drop:Q", format=".1%",
                                                             title="1-in-10 drop over your horizon (simulated)")]))
    ref = pd.DataFrame({"y": [loss], "label": [f"your loss limit {loss:.0%}"]})
    layers += [alt.Chart(ref).mark_rule(color="#b91c1c", strokeDash=[5, 3]).encode(y="y:Q"),
               alt.Chart(ref).mark_text(align="left", dx=4, dy=-6, color="#b91c1c", fontSize=10)
               .encode(x=alt.value(0), y="y:Q", text="label")]
    st = strategy.get("stats") or {}
    if "max_drawdown" in st:  # the proposed strategy itself (after rounding and caps), not the nearest grid point
        pick = pd.DataFrame([{"growth": chosen, "worst_drop": abs(st["max_drawdown"]),
                              "return_2022": st.get("return_2022"), "ann_vol": st.get("ann_vol")}])
        layers.append(alt.Chart(pick).mark_point(shape="diamond", size=160, filled=True, color="black")
                      .encode(x=x, y=y, tooltip=tip))
    chart = alt.layer(*layers).properties(height=height)
    if not title:  # narrow columns: the app writes the title above the chart instead (clipped otherwise)
        return chart
    return chart.properties(title=alt.TitleParams(
        "More growth, deeper worst drop", anchor="start",
        subtitle=[source_note(), "Blue: worst drop observed. Orange: 1-in-10 drop over your horizon (simulated)."]))


def outcome_frame(strategy: dict) -> pd.DataFrame | None:
    """`market_charts.outcome_chart`'s DataFrame from the strategy's own outlook (same numbers, no second bootstrap)."""
    o = strategy.get("outlook")
    if not o:
        return None
    return pd.DataFrame([{"scenario": OUTCOME_LABEL[k], "key": k, "p5": o[k]["final_p5"], "p50": o[k]["final_p50"],
                          "p95": o[k]["final_p95"], "prob_loss": o[k]["prob_loss"], "prob_target": o[k]["prob_target"],
                          "total_invested": o["total_invested"], "target_amount": o.get("target_amount"),
                          "horizon_years": o["horizon_years"]} for k in ("risk_only", "central", "replay") if k in o])
