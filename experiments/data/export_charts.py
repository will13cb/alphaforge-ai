"""Export the market-data charts as PNG (video, one-pager) and HTML (interactive), from the real starter data.

Strategies come from the pipeline (`pipeline.run`): Robert's proposals plus his 25% TSLA request "as asked" and
"fits your limits", and Amira's proposals. Needs the starter CSVs in data/raw/.

    PYTHONPATH=src python experiments/data/export_charts.py     # → experiments/data/figures/ (gitignored)
"""

from __future__ import annotations

from pathlib import Path

from dh.agents import market_charts as mc

OUT = Path(__file__).parent / "figures"

def pipeline_strategies() -> tuple[dict, dict, dict, dict]:
    """(Robert's strategies incl. the request side by side, Robert's profile, Amira's strategies, Amira's profile)."""
    from dh.agents.pipeline import run
    from dh.agents.scenarios import AMIRA, ROBERT
    robert = {**ROBERT, "requested_positions": {"TSLA": 0.25}}
    r, a = run(robert), run(AMIRA)
    rs = {s["name"]: s["weights"] for s in r["strategies"]}
    c = r.get("request_comparison") or {}
    if c.get("as_asked"):
        rs["Request as asked: 25% TSLA"] = c["as_asked"]["weights"]
    if c.get("fits"):
        rs[f"Request that fits: TSLA {c['fits']['request_at']['TSLA']:.1%}"] = c["fits"]["weights"]
    return rs, robert, {s["name"]: s["weights"] for s in a["strategies"]}, AMIRA


def main() -> None:
    OUT.mkdir(exist_ok=True)
    robert, rp, amira, ap = pipeline_strategies()
    goal = dict(capital=rp["capital"], horizon_years=rp["horizon_years"],
                monthly_contribution=rp.get("monthly_contribution") or 0, target_amount=rp.get("target_amount"))
    asked = next(w for n, w in robert.items() if n.startswith("Request as asked"))
    fits = next((w for n, w in robert.items() if n.startswith("Request that fits")), None)
    charts = {
        "robert_growth": mc.growth_chart(mc.growth_data(robert)),
        "robert_outcome_asked": mc.outcome_chart(mc.outcome_data(asked, **goal)),
        "robert_risk_return": mc.risk_return_chart(mc.risk_return_data(robert)),
        "amira_growth": mc.growth_chart(mc.growth_data(amira)),
        "amira_risk_return": mc.risk_return_chart(mc.risk_return_data(amira)),
        "correlation_amira": mc.correlation_chart(mc.correlation_data(["QQQ", "NVDA", "MSFT", "SPY", "ESGV", "BTC-USD", "ETH-USD"])),
        "correlation_all": mc.correlation_chart(mc.correlation_data()),
        "year_2022": mc.year_2022_chart(mc.year_2022_data(), highlight=["TSLA"]),
    }
    if fits:
        charts["robert_outcome_fits"] = mc.outcome_chart(mc.outcome_data(fits, **goal))
    for name, chart in charts.items():
        chart.save(str(OUT / f"{name}.html"))
        try:
            mc.to_png(chart, OUT / f"{name}.png")
        except Exception as e:  # vl-convert-python missing: HTML only
            print(f"{name}: PNG skipped ({type(e).__name__}: {e})")
        print(f"saved {name}")


if __name__ == "__main__":
    main()
