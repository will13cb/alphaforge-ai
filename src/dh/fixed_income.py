"""Illustrative annual-coupon bond held to maturity, separate from traded funds.

No issuer, security or quoted rate is invented. Coupon and principal cash flows
assume the issuer pays as agreed. They are not a market-value or credit-risk model.
"""
from __future__ import annotations

import math
import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .personas import DISCLAIMER


def _previous_coupon(day: date, months: int = 6) -> date:
    month = day.month - months
    year = day.year - (month <= 0)
    month = month if month > 0 else month + 12
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def project(profile: dict, bond: dict | None = None, today: date | None = None) -> dict:
    capital = float(profile.get("capital") or 0)
    years = float(profile.get("horizon_years") or 0)
    rate_pct = float(profile.get("fixed_rate_pct", 3))
    if not all(math.isfinite(x) for x in (capital, years, rate_pct)):
        raise ValueError("Use finite amounts, a maturity and a rate.")
    if capital <= 0 or not 0 < years <= 60 or not 0 <= rate_pct <= 100:
        raise ValueError("Enter positive capital, a maturity up to 60 years, and an assumed rate from 0 to 100%.")
    if bond is not None:
        today = today or datetime.now(ZoneInfo("America/Toronto")).date()
        maturity = date.fromisoformat(bond["maturity"])
        if maturity <= today:
            raise ValueError("The bond has matured.")
        rate_pct = float(bond["coupon_pct"])
        if bond.get("instrument_type") in ("gic", "cd"):
            whole_years = maturity.year - today.year
            anniversary = date(today.year + whole_years, today.month,
                               min(today.day, calendar.monthrange(today.year + whole_years, today.month)[1]))
            if anniversary > maturity:
                whole_years -= 1
                anniversary = date(today.year + whole_years, today.month,
                                   min(today.day, calendar.monthrange(today.year + whole_years, today.month)[1]))
            next_anniversary = date(anniversary.year + 1, today.month,
                                    min(today.day, calendar.monthrange(anniversary.year + 1, today.month)[1]))
            term = whole_years + (maturity - anniversary).days / (next_anniversary - anniversary).days
            rate = rate_pct / 100
            payout = bond.get("cashflow_type")
            if payout == "compound_at_maturity":
                interest = capital * ((1 + rate) ** term - 1)
                schedule = [{"date": maturity.isoformat(), "interest": round(interest, 2), "principal_repaid": round(capital, 2)}]
                convention = "Annual compounding, all interest paid at maturity; no annual cash payout."
            elif payout == "annual_payout":
                schedule = []
                year = 1
                previous = today
                while True:
                    anniversary = date(today.year + year, today.month, min(today.day, calendar.monthrange(today.year + year, today.month)[1]))
                    payment = min(anniversary, maturity)
                    fraction = 1.0 if payment == anniversary else (payment - previous).days / (anniversary - previous).days
                    schedule.append({"date": payment.isoformat(), "interest": round(capital * rate * fraction, 2),
                                     "principal_repaid": round(capital, 2) if payment == maturity else 0.0})
                    if payment == maturity:
                        break
                    previous = payment
                    year += 1
                interest = sum(row["interest"] for row in schedule)
                convention = "Annual interest paid out without reinvestment; a partial last year is prorated."
            else:
                raise ValueError("Deposit payout terms must be specified.")
            return {"kind": "sourced_deposit_illustration", "allocation": {bond["instrument_id"]: 1.0},
                    "capital": round(capital, 2), "annual_rate_pct": rate_pct,
                    "maturity_years": term, "maturity_date": maturity.isoformat(),
                    "annual_interest": round(capital * rate, 2) if payout == "annual_payout" else 0.0,
                    "total_interest": round(interest, 2), "principal_at_maturity": round(capital, 2),
                    "total_cash_paid": round(capital + interest, 2), "schedule": schedule,
                    "assumptions": ["New deposit illustrated from today at the sourced rate; current availability must be confirmed.",
                                    convention, "Issuer repayment is assumed; CDIC/FDIC eligibility and coverage are not certified.",
                                    "Fees, taxes, inflation, monthly contributions and early withdrawals are excluded."],
                    "evidence": "sourced deposit terms; illustrative payment conventions"}
        frequency = int(bond.get("coupon_frequency") or 2)
        payments = []
        day = maturity
        while day > today:
            payments.append(day)
            day = _previous_coupon(day, 12 // frequency)
        payments.reverse()
        accrued_per_100 = rate_pct / frequency * (today - day).days / (payments[0] - day).days
        clean_price = float(100 if bond.get("offer_price") is None else bond["offer_price"])
        if not math.isfinite(clean_price) or clean_price <= 0:
            raise ValueError("A purchase price must be positive and finite.")
        face = capital * 100 / (clean_price + accrued_per_100)
        coupon = face * rate_pct / 100 / frequency
        schedule = [{"date": d.isoformat(), "interest": round(coupon, 2),
                     "principal_repaid": round(face, 2) if d == maturity else 0.0} for d in payments]
        paid = sum(row["interest"] for row in schedule)
        accrued = face * accrued_per_100 / 100
        return {"kind": "sourced_held_to_maturity", "allocation": {bond.get("instrument_id") or bond.get("isin") or bond["maturity"]: 1.0},
                "capital": round(capital, 2), "annual_rate_pct": rate_pct,
                "maturity_years": (maturity - today).days / 365.25, "maturity_date": maturity.isoformat(),
                "annual_interest": round(face * rate_pct / 100, 2),
                "total_interest": round(paid - accrued, 2), "principal_at_maturity": round(face, 2),
                "total_cash_paid": round(face + paid, 2), "schedule": schedule,
                "assumptions": [
                    "Sourced instrument terms; broker availability must be confirmed.",
                    f"Cash flows use a clean price of {clean_price:g} per 100 face value, plus accrued interest. " + ("This is an assumed par price; a current broker quote is required." if bond.get("offer_price") is None else "Price is from the supplied catalogue; availability and fees must be checked."),
                    f"Coupons are paid {frequency} times a year, not reinvested; principal is repaid at maturity if the issuer pays as agreed.",
                    "Selling before maturity can cause a loss. No risk-free return or zero-loss guarantee is certified.",
                    "Fees, taxes, inflation and any reinvestment after maturity are excluded.",
                    "Monthly contributions are excluded from this single-purchase illustration.",
                ], "evidence": "sourced bond terms; cash-flow pricing assumption"}
    annual = capital * rate_pct / 100
    schedule = []
    whole = math.floor(years)
    for year in range(1, whole + 1):
        schedule.append({"year": year, "interest": round(annual, 2), "principal_repaid": 0.0})
    if years > whole:
        schedule.append({"year": years, "interest": round(annual * (years - whole), 2),
                         "principal_repaid": 0.0})
    schedule[-1]["principal_repaid"] = round(capital, 2)
    total_interest = round(sum(row["interest"] for row in schedule), 2)
    assumptions = [
        "Hypothetical fixed-rate bond: no actual security, issuer or available market quote has been selected.",
        "The entered annual coupon is a scenario assumption, not the equity risk premium used in market simulations.",
        "Purchased at par and held to the stated maturity; the issuer pays every coupon and repays principal in full.",
        "Interest is paid out annually, not reinvested; a partial final year uses prorated interest.",
        "Principal repayment at maturity does not mean the bond's resale price cannot fall before maturity.",
        "No credit default, fees, taxes, inflation or early withdrawal is modelled. No capital guarantee is verified.",
    ]
    if profile.get("monthly_contribution"):
        assumptions.append("Monthly contributions are excluded from this single-principal illustration.")
    if profile.get("withdrawal_share_3y"):
        assumptions.append("Early withdrawals may conflict with holding to maturity; sale proceeds are not modelled.")
    return {"kind": "illustrative_held_to_maturity", "allocation": {"fixed_rate_bond": 1.0},
            "capital": round(capital, 2), "annual_rate_pct": rate_pct, "maturity_years": years,
            "annual_interest": round(annual, 2), "total_interest": total_interest,
            "principal_at_maturity": round(capital, 2),
            "total_cash_paid": round(capital + total_interest, 2),
            "schedule": schedule, "assumptions": assumptions, "evidence": "user-selected scenario assumption"}


def explanation(s: dict) -> str:
    if s.get("status") == "unavailable":
        return "### Bond request\n\n" + s["message"] + "\n\n" + DISCLAIMER
    if s.get("selected_bond"):
        b = s["selected_bond"]
        reference_yield = (f" Published benchmark yield: {b['benchmark_yield_pct']:g}% as of {b['yield_as_of']}."
                           if b.get("benchmark_yield_pct") is not None else " A current yield for this exact bond still needs a purchase quote.")
        return (
            "### Your bond portfolio\n\n" + s["message"] + "\n\n"
            f"Your requested rate was {s['requested_rate_pct']:g}% over {s['requested_horizon_years']:g} years. "
            f"This bond has a fixed {b['coupon_pct']:g}% coupon and matures on {b['maturity']}."
            + reference_yield + "\n\n### Income illustration\n\n"
            + (f"Interest paid at maturity is about {s['total_interest']:,.0f} {s.get('currency', 'CAD')}, using annual compounding. "
               if b.get("cashflow_type") == "compound_at_maturity" else
               f"On a {s['capital']:,.0f} {s.get('currency', 'CAD')} budget, annual income is about {s['annual_interest']:,.0f} {s.get('currency', 'CAD')}, "
               "using the purchase assumptions below. Interest is paid out; it is not reinvested. ")
            + "No rate is assumed after this bond matures.\n\n### Details and assumptions\n\n"
            + "\n".join(f"- {a}" for a in s["assumptions"])
            + f"\n\n[Bond terms]({b['terms_source']})"
            + "\n\n" + DISCLAIMER
        )
    return (
        "### Your fixed-rate portfolio illustration\n\n"
        f"100% in a hypothetical fixed-rate bond, purchased at par and held for {s['maturity_years']:g} years. "
        f"The assumed annual coupon is {s['annual_rate_pct']:g}%. No stocks, gold or crypto are included.\n\n"
        "### Income and principal\n\n"
        f"On {s['capital']:,.0f} $ of principal, annual interest is {s['annual_interest']:,.0f} $. "
        f"Total interest paid over the term is {s['total_interest']:,.0f} $, without reinvestment. "
        f"At maturity, {s['principal_at_maturity']:,.0f} $ of principal is returned, assuming the issuer pays as agreed.\n\n"
        "### What this assumes\n\n"
        + "\n".join(f"- {a}" for a in s["assumptions"])
        + "\n\n" + DISCLAIMER
    )
