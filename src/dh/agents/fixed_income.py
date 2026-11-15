"""Fixed-income lookup agent: source-backed matching and deterministic cash flows.

No LLM chooses a rate, invents a security, or certifies a guarantee. Reference
securities remain distinct from broker offers and from traded bond-fund backtests.
"""
from __future__ import annotations

import math
from datetime import datetime, date
from zoneinfo import ZoneInfo

from .. import bond_rates
from ..fixed_income import project


def run(profile: dict, reference: dict | None = None, today: date | None = None) -> dict:
    reference = bond_rates.references() if reference is None else reference
    today = today or datetime.now(ZoneInfo("America/Toronto")).date()
    target = float(profile.get("fixed_rate_pct", 3))
    horizon = float(profile.get("horizon_years") or 0)
    if not math.isfinite(target) or not 0 <= target <= 100 or not math.isfinite(horizon) or not 0 < horizon <= 60:
        raise ValueError("Enter a valid target rate and horizon.")
    market = profile.get("fixed_income_market", "both")
    candidates = []
    for bond in reference.get("outstanding_bonds", reference.get("bonds", [])):
        if str(bond.get("available_to_buy", "")).lower() in ("no", "false", "0"):
            continue
        country = bond.get("country", "Canada")
        if (market == "canada" and country != "Canada") or (market == "us" and country != "United States"):
            continue
        if str(bond.get("callable", "")).lower() in ("yes", "true", "1"):
            continue  # a callable term cannot promise coupons through the requested maturity
        if bond.get("instrument_type", "bond") not in ("bond", "gic", "cd"):
            continue
        if float(profile.get("max_loss_pct") or 0) == 0 and bond.get("issuer_type") != "sovereign":
            continue  # no corporate/deposit guarantee is inferred from a high coupon
        years = (date.fromisoformat(bond["maturity"]) - today).days / 365.25
        if years <= 0 or abs(years - horizon) > max(1.25, horizon * .1):
            continue
        # A coupon can identify an income candidate. It cannot establish the return
        # on the client's cash without a current purchase price.
        observed_yield = bond.get("offer_yield_pct")
        if observed_yield is None:
            observed_yield = bond.get("benchmark_yield_pct")
        rate = observed_yield if observed_yield is not None else bond["coupon_pct"]
        if rate >= target:
            evidence_rank = 0 if bond.get("offer_price") is not None else (1 if observed_yield is not None else 2)
            candidates.append(((0 if bond.get("currency", "CAD") == "CAD" else 1, evidence_rank, abs(years - horizon)), bond))
    result = {"requested_rate_pct": target, "requested_horizon_years": horizon, "references": reference}
    if not candidates:
        return {**result, "status": "unavailable", "allocation": {},
                "message": (f"No supported fixed-income instrument in the loaded Canada/U.S. catalogue matches a {target:g}% "
                            f"coupon target near your {horizon:g}-year horizon. We cannot promise that return. "
                            "The available rates are shown below.")}
    bond = min(candidates, key=lambda pair: pair[0])[1]
    converted = dict(profile)
    currency = bond.get("currency", "CAD")
    fx = reference.get("fx_usdcad")
    if currency == "USD":
        if not fx or fx["value"] <= 0:
            return {**result, "status": "unavailable", "allocation": {}, "message": "A U.S. bond was found, but a dated USD/CAD rate is needed to illustrate this CAD budget."}
        converted["capital"] = float(profile.get("capital") or 0) / fx["value"]
    scenario = project(converted, bond=bond, today=today)
    scenario["currency"] = currency
    scenario["budget_cad"] = profile.get("capital")
    if currency == "USD":
        scenario["assumptions"].append(f"Budget converted at {fx['value']:g} CAD per USD ({fx['as_of']}); future CAD income and principal are exposed to exchange-rate changes.")
    return {**result, **scenario, "selected_bond": bond, "status": "quote_required",
            "message": (f"100% {bond['issuer']} · {bond['coupon_pct']:g}% coupon · "
                        f"matures {bond['maturity']}. Current purchase price must be confirmed before the return is locked in.")}
