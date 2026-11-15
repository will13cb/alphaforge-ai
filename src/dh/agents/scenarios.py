"""Test profiles with expected verdicts: the 3 official personas + trap profiles.

    python -m dh scenarios            # run them, show each hand-off
    python -m dh scenarios --log      # + log the pass rate to results.csv (commit code first)

FICTIONAL. Persona facts come from the brief (dh.personas); everything else (capital, emergency fund, quiz,
candidate strategies and their stats) is invented for the test. Strategy stats are NOT computed from data;
they only exercise the Guardian. Holdings marked ILLUSTRATIVE are placeholders, not issuer data.
"""

from __future__ import annotations

from ..personas import DISCLAIMER
from .pipeline import run

AMIRA = dict(name="Amira", age=26, horizon_years=15, objective="growth", capital=30_000, monthly_contribution=500,
             emergency_fund_months=6, income_stability="stable", withdrawal_share_3y=0.0,
             loss_reaction="buy_more", max_loss_pct=40, knowledge_level="intermediate", years_experience=4,
             products_held=["etfs", "stocks", "crypto"], interests=["ai", "crypto"], exclusions=[],
             kyc_bets={"bet_small": 0.08, "bet_large": 0.10, "bet_savings": 0.065}, ev_answer_pct=10)
MATEO = dict(name="Mateo", age=41, horizon_years=10, objective="growth", capital=150_000, monthly_contribution=800,
             emergency_fund_months=6, income_stability="stable", withdrawal_share_3y=0.0,
             loss_reaction="hold", max_loss_pct=25, knowledge_level="intermediate", years_experience=8,
             products_held=["etfs"], interests=["esg"], exclusions=["fossil_fuels"],
             kyc_bets={"bet_small": 0.06, "bet_large": 0.06, "bet_savings": 0.045}, ev_answer_pct=10)
ROBERT = dict(name="Robert", age=59, horizon_years=4, objective="retirement", capital=400_000, monthly_contribution=0,
              emergency_fund_months=12, income_stability="stable", withdrawal_share_3y=0.2,
              loss_reaction="hold", max_loss_pct=15, knowledge_level="advanced", years_experience=20,
              products_held=["stocks", "etfs", "bonds"], interests=["dividends", "canada"], exclusions=["crypto"],
              kyc_bets={"bet_small": 0.04, "bet_large": 0.02, "bet_savings": 0.035}, ev_answer_pct=10)
# KYC answers (dh.kyc, decision #40): fictional, chosen to match each story (Joud's examples on optimisation-markowitz).

# The profiles the app and the CLI (`python -m dh propose|explain`) run. One definition, so the same profile gives the
# same facts hash and the committed Explainer cache (cache/explainer/) is hit from both.
DEMO_PROFILES = {
    "amira": AMIRA,
    "mateo": MATEO,
    "robert": ROBERT,
    "robert_tsla": {**ROBERT, "requested_positions": {"TSLA": 0.25}},
}
DEMO_LABELS = {"amira": "Amira (26, high risk, AI + crypto)", "mateo": "Mateo (41, moderate, ESG)",
               "robert": "Robert (59, cautious, 4 years)", "robert_tsla": "Robert asks for 25% in Tesla"}

# Worst 2021-2026 drop per asset in CAD, copied from market.asset_summary() on 2026-11-14 (starter data), so the
# scenarios and tests run offline with the same company caps as the real data (decision #24).
DROPS_DEMO = {"SHOP.TO": -0.835, "ETH-USD": -0.772, "BTC-USD": -0.733, "TSLA": -0.709, "NVDA": -0.635, "CSU.TO": -0.564,
              "AMZN": -0.524, "TLT": -0.397, "GOOGL": -0.395, "MSFT": -0.343, "AAPL": -0.342, "CNQ.TO": -0.331,
              "JPM": -0.322, "QQQ": -0.321, "CNR.TO": -0.272, "ESGV": -0.269, "TD.TO": -0.261, "GLD": -0.26,
              "FTS.TO": -0.24, "PG": -0.235, "SPY": -0.222, "ATD.TO": -0.222, "ENB.TO": -0.214, "RY.TO": -0.212,
              "MFC.TO": -0.21, "XOM": -0.191, "XIU.TO": -0.164, "JNJ": -0.155, "XBB.TO": -0.155, "AGG": -0.128,
              "ZST.TO": -0.004}

# ILLUSTRATIVE holdings (round placeholders, NOT issuer data) to exercise look-through.
HOLDINGS_DEMO = {"QQQ": {"NVDA": 0.09, "MSFT": 0.08, "AAPL": 0.08}, "SPY": {"NVDA": 0.07, "MSFT": 0.06, "AAPL": 0.06},
                 "XIU.TO": {"RY.TO": 0.07, "ENB.TO": 0.05, "CNQ.TO": 0.04}}

# Horizon 4 years → at most 15% growth (decision #22), so 85% defensive (was 55% before the horizon directive).
# One company ≤ 3.1% for Robert (decision #24: about 15% stock room / 5), so RY.TO 3% (was 5% under the fixed 8% cap).
# Equities split Canada/US (XIU, RY 9% / SPY 6%): all-Canadian equities would trip G14 geography (decision #20).
ROBERT_OK = dict(name="Cautious income", weights={"XBB.TO": 0.35, "ZST.TO": 0.40, "GLD": 0.10, "XIU.TO": 0.06,
                                                  "SPY": 0.06, "RY.TO": 0.03},
                 stats=dict(ann_return=0.035, ann_vol=0.04, max_drawdown=-0.06))
ROBERT_TEXT = (f"You asked for 25% in TSLA. Its worst drop in 2021-2026 was -70.9%, so at 25% it alone would have cost "
               f"-17.7% of the portfolio, more than your whole 15% loss limit. It fits up to 3.1%, so this strategy "
               f"leaves it out. "
               f"It keeps 85% in defensive assets; its worst historical drop was 6%, within your 15% limit. {DISCLAIMER}")
MATEO_OK = dict(name="Balanced ESG", weights={"ESGV": 0.35, "XIU.TO": 0.15, "XBB.TO": 0.25, "AGG": 0.10, "GLD": 0.05,
                                              "MSFT": 0.05, "FTS.TO": 0.05},
                stats=dict(ann_return=0.06, ann_vol=0.11, max_drawdown=-0.20))
AMIRA_TECH = dict(name="Growth tilt", weights={"NVDA": 0.12, "QQQ": 0.30, "SPY": 0.20, "XIU.TO": 0.10, "MSFT": 0.08,
                                               "BTC-USD": 0.08, "ETH-USD": 0.02, "GLD": 0.05, "XBB.TO": 0.05},
                  stats=dict(ann_return=0.14, ann_vol=0.21, max_drawdown=-0.36))


def _p(base, **kw):
    return {**base, **kw}


SCENARIOS = [
    dict(id="amira-crypto-ok", note="high risk, small crypto request inside her cap",
         profile=_p(AMIRA, requested_positions={"BTC-USD": 0.08}), expect=dict(risk_level=5, refused=[])),
    dict(id="amira-all-in-nvda", note="high risk is not 'anything goes'",
         profile=_p(AMIRA, requested_positions={"NVDA": 0.50}), expect=dict(risk_level=5, refused=["NVDA"])),
    dict(id="amira-nvda-lookthrough", note="12% NVDA direct passes alone, but QQQ+SPY push it over 15%",
         profile=AMIRA, strategy=AMIRA_TECH, holdings=HOLDINGS_DEMO, expect=dict(verdict="fail", failed=["G4"])),
    dict(id="mateo-esg-ok", note="ESG-tilted balanced strategy passes", profile=MATEO, strategy=MATEO_OK,
         expect=dict(risk_level=3, verdict="pass")),
    dict(id="mateo-xom", note="excluded fossil-fuel stock slipped into the strategy", profile=MATEO,
         strategy=_p(MATEO_OK, weights={**MATEO_OK["weights"], "FTS.TO": 0.0, "XOM": 0.05}),
         expect=dict(verdict="fail", failed=["G3"])),
    dict(id="mateo-xiu-lookthrough", note="XIU holds Enbridge and CNQ: disclose, don't hide", profile=MATEO,
         strategy=MATEO_OK, holdings=HOLDINGS_DEMO, expect=dict(verdict="warn", warned=["G10"])),
    dict(id="robert-tsla-refused", note="the brief's test: challenge the hyped request",
         profile=_p(ROBERT, requested_positions={"TSLA": 0.25}), strategy=ROBERT_OK, explanation=ROBERT_TEXT,
         expect=dict(risk_level=2, refused=["TSLA"], verdict="pass")),
    dict(id="robert-tsla-applied", note="strategy quietly gives him the 25% TSLA anyway",
         profile=_p(ROBERT, requested_positions={"TSLA": 0.25}),
         strategy=_p(ROBERT_OK, weights={"XBB.TO": 0.30, "ZST.TO": 0.20, "GLD": 0.05, "XIU.TO": 0.20, "TSLA": 0.25}),
         expect=dict(verdict="fail", failed=["G4", "G9"])),
    dict(id="robert-invented-number", note="explanation quotes a return that was never computed",
         profile=_p(ROBERT, requested_positions={"TSLA": 0.25}), strategy=ROBERT_OK,
         explanation=ROBERT_TEXT.replace("It keeps", "It should earn about 9% a year. It keeps"),
         expect=dict(verdict="fail", failed=["G12"])),
    dict(id="robert-no-disclaimer", note="explanation drops the simulation disclaimer",
         profile=_p(ROBERT, requested_positions={"TSLA": 0.25}), strategy=ROBERT_OK,
         explanation=ROBERT_TEXT.replace(DISCLAIMER, ""), expect=dict(verdict="fail", failed=["G11"])),
    dict(id="beginner-all-crypto", note="no knowledge, quiz 0/3, wants 100% Bitcoin",
         profile=dict(name="Trap: beginner", age=22, horizon_years=10, objective="growth", emergency_fund_months=2,
                      income_stability="stable", loss_reaction="buy_more", max_loss_pct=50, knowledge_level="none",
                      quiz_correct=0, requested_positions={"BTC-USD": 1.0}),
         expect=dict(risk_level=3, knowledge_score=1, refused=["BTC-USD"], max_crypto=0.0)),
    dict(id="short-horizon-high-risk", note="wants high risk but needs the money in 2 years",
         profile=dict(name="Trap: short horizon", age=30, horizon_years=2, objective="major_project",
                      emergency_fund_months=6, income_stability="stable", loss_reaction="buy_more", max_loss_pct=50,
                      knowledge_level="intermediate"),
         expect=dict(risk_level=1, risk_tolerance=5, risk_capacity=1)),
    dict(id="no-cushion-uncertain-income", note="long horizon, but no emergency fund and uncertain income",
         profile=dict(name="Trap: fragile", age=35, horizon_years=12, objective="retirement", emergency_fund_months=0,
                      income_stability="uncertain", loss_reaction="hold", max_loss_pct=25, knowledge_level="basic"),
         expect=dict(risk_level=2, risk_capacity=2)),
    dict(id="overconfident", note="declares 'advanced' but scores 1/3 on the quiz",
         profile=dict(name="Trap: overconfident", age=45, horizon_years=10, objective="growth", emergency_fund_months=6,
                      income_stability="stable", loss_reaction="hold", max_loss_pct=25, knowledge_level="advanced",
                      years_experience=1, quiz_correct=1),
         expect=dict(knowledge_score=3)),
    dict(id="big-withdrawal", note="60% may be withdrawn within 3 years; strategy keeps only 50% defensive",
         # horizon 8 y (was 6): the horizon directive (#22) allows 46% growth, so the 60% withdrawals still bind
         profile=dict(name="Trap: needs cash", age=50, horizon_years=8, objective="major_project",
                      emergency_fund_months=6, income_stability="stable", withdrawal_share_3y=0.6,
                      loss_reaction="hold", max_loss_pct=25, knowledge_level="intermediate"),
         strategy=dict(name="Too risky", weights={"XBB.TO": 0.30, "ZST.TO": 0.20, "SPY": 0.30, "XIU.TO": 0.20},
                       stats=dict(max_drawdown=-0.13, ann_vol=0.08)),
         expect=dict(risk_level=2, min_defensive=0.6, verdict="fail", failed=["G6"])),
    dict(id="missing-horizon", note="horizon unknown: ask, don't guess",
         profile=_p(MATEO, horizon_years=None), expect=dict(missing=["horizon_years"], verdict="fail", failed=["G1"])),
]


def evaluate(sc: dict) -> tuple[dict, list[str]]:
    """Run one scenario; return (pipeline result, list of mismatches). Empty list = scenario passed."""
    # {} = no look-through unless the scenario brings its ILLUSTRATIVE holdings: tests stay offline and stable
    res = run(sc["profile"], sc.get("strategy"), sc.get("explanation"), sc.get("holdings", {}), propose=False,
              drops=DROPS_DEMO)
    lim, exp, bad = res["limits"], sc["expect"], []
    refused = [f.split()[1].rstrip(":") for f in lim.get("flags", []) if f.startswith("request ")]
    failed = {c["rule"] for c in res["checks"] if c["status"] == "fail"}
    warned = {c["rule"] for c in res["checks"] if c["status"] == "warn"}
    for k, v in exp.items():
        got = {"refused": refused, "verdict": res["verdict"], "failed": failed, "warned": warned}.get(k, lim.get(k))
        ok = set(v) <= set(got or []) if k in ("failed", "warned", "missing") else got == v
        if k == "refused":
            ok = sorted(got) == sorted(v)
        if not ok:
            bad.append(f"{k}: expected {v}, got {sorted(got) if isinstance(got, set) else got}")
    return res, bad


def run_all(verbose: bool = False) -> float:
    passed = 0
    for sc in SCENARIOS:
        res, bad = evaluate(sc)
        passed += not bad
        print(f"{'PASS' if not bad else 'FAIL'}  {sc['id']:<28} {sc['note']}")
        for b in bad:
            print(f"      ↳ {b}")
        if verbose:
            print("\n".join("      " + ln for ln in res["trace"].markdown().splitlines()) + "\n")
    rate = passed / len(SCENARIOS)
    print(f"\n{passed}/{len(SCENARIOS)} scenarios behave as expected ({rate:.0%})")
    return rate
