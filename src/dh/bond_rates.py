"""Dated Canadian/U.S. fixed-income catalogue and government reference terms.

Bank of Canada yields are mid-market references, not executable broker offers.
Missing prices and inventories stay unknown. A dated snapshot supports offline use.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
import csv
from datetime import date
from pathlib import Path
import re
from urllib.request import Request, urlopen

PAGE = "https://www.bankofcanada.ca/rates/interest-rates/canadian-bonds/"
API = "https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json?recent=5"
OUTSTANDING = "https://www.bankofcanada.ca/markets/government-securities-auctions/goc-t-bills-bonds-outstanding/"
from .data import load_config

def folder() -> Path:
    return load_config().data_dir / "fixed_income"

SNAPSHOT = folder() / "reference_snapshot.json"
SERIES = {"2 year": "BD.CDN.2YR.DQ.YLD", "3 year": "BD.CDN.3YR.DQ.YLD",
          "5 year": "BD.CDN.5YR.DQ.YLD", "7 year": "BD.CDN.7YR.DQ.YLD",
          "10 year": "BD.CDN.10YR.DQ.YLD", "Long": "BD.CDN.LONG.DQ.YLD"}


def _get(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "AlphaForge educational prototype"}), timeout=10) as response:
        return response.read()


def parse(page: str, data: dict) -> dict:
    text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", page)))
    rows = []
    for term, series in SERIES.items():
        match = re.search(re.escape(term) + r"\s*-\s*(\d{4}\.\d{2}\.\d{2}),\s*(\d+(?:\.\d+)?)%", text, re.I)
        observations = [o for o in data.get("observations", []) if (o.get(series) or {}).get("v") not in (None, "NA", "")]
        if not match or not observations:
            continue
        latest = max(observations, key=lambda o: o["d"])
        rows.append({"issuer": "Government of Canada", "currency": "CAD", "term": term,
                     "maturity": match[1].replace(".", "-"), "coupon_pct": float(match[2]),
                     "benchmark_yield_pct": float(latest[series]["v"]), "yield_as_of": latest["d"],
                     "offer_price": None, "available_to_buy": None})
    if not rows:
        raise ValueError("No bond terms could be matched to the published yields.")
    return {"bonds": rows, "terms_source": PAGE, "yields_source": API,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_mode": "live", "note": "Mid-market benchmark yields, not executable purchase quotes. Price and inventory are unverified."}


def outstanding(page: str) -> list[dict]:
    class Table(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self.row, self.cell = [], [], None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.row = []
            if tag == "td":
                self.cell = []

        def handle_data(self, text):
            if self.cell is not None:
                self.cell.append(text)

        def handle_endtag(self, tag):
            if tag == "td" and self.cell is not None:
                self.row.append(" ".join("".join(self.cell).split()))
                self.cell = None
            if tag == "tr" and self.row:
                self.rows.append(self.row)
    table = Table()
    table.feed(page)
    rows = []
    for row in table.rows:
        if len(row) < 6 or row[5] != "BD-FIX" or not re.fullmatch(r"CA\w{10}", row[4]):
            continue
        rows.append({"issuer": "Government of Canada", "currency": "CAD", "isin": row[4],
                     "maturity": row[1], "coupon_pct": float(row[3]), "terms_as_of": row[0],
                     "terms_source": OUTSTANDING, "benchmark_yield_pct": None,
                     "offer_price": None, "available_to_buy": None})
    return rows


def _canada(fetch=None) -> dict:
    fetch = fetch or _get
    try:
        result = parse(fetch(PAGE).decode(), json.loads(fetch(API)))
        try:
            issues = outstanding(fetch(OUTSTANDING).decode())
            by_maturity = {b["maturity"]: b for b in result["bonds"]}
            for bond in issues:
                benchmark = by_maturity.get(bond["maturity"])
                if benchmark:
                    bond.update(benchmark_yield_pct=benchmark["benchmark_yield_pct"], yield_as_of=benchmark["yield_as_of"])
            result["outstanding_bonds"] = issues
        except Exception:
            result["outstanding_bonds"] = []
        return result
    except Exception as error:
        saved = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else {"bonds": [], "outstanding_bonds": [], "terms_source": PAGE, "yields_source": API, "note": "No saved bond references available."}
        return {**saved, "source_mode": "saved snapshot",
                "note": f"Live refresh unavailable ({type(error).__name__}); showing the dated saved reference. " + saved["note"]}


US_SOURCE = "https://www.treasurydirect.gov/auctions/auction-query/"
FX_API = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=5"


def refresh(fetch=None) -> dict:
    """Public Canadian issues and U.S. nominal Treasury notes/bonds; no broker inventory claim."""
    fetch = fetch or _get
    result = _canada(fetch)
    rows = [dict(b) for b in result.get("outstanding_bonds", []) if b.get("currency") == "CAD"]
    for b in rows:
        b.update(country="Canada", instrument_type="bond", issuer_type="sovereign", coupon_frequency=2,
                 instrument_id=b.get("isin"), quote_kind="benchmark" if b.get("benchmark_yield_pct") is not None else "terms_only")
    notes = []
    for family in ("Note", "Bond"):
        url = f"https://www.treasurydirect.gov/TA_WS/securities/search?format=json&type={family}"
        try:
            issues = json.loads(fetch(url))
            seen = {}
            for b in issues:
                maturity = (b.get("maturityDate") or "")[:10]
                auction = (b.get("competitiveAuctionCloseDate") or "")[:10]
                if (not b.get("cusip") or not b.get("interestRate") or maturity <= date.today().isoformat()
                        or not auction or auction > date.today().isoformat() or b.get("floatingRate") == "Yes"
                        or b.get("inflationIndexSecurity") == "Yes"):
                    continue
                row = {"instrument_id": b["cusip"], "issuer": "U.S. Treasury", "issuer_type": "sovereign",
                       "country": "United States", "currency": "USD", "instrument_type": "bond", "coupon_frequency": 2,
                       "maturity": maturity, "coupon_pct": float(b["interestRate"]), "terms_as_of": auction,
                       "auction_yield_pct": float(b["highYield"]) if b.get("highYield") else None,
                       "benchmark_yield_pct": None, "offer_price": None, "quote_kind": "auction_history",
                       "terms_source": url, "available_to_buy": None}
                if auction >= seen.get(b["cusip"], {}).get("terms_as_of", ""):
                    seen[b["cusip"]] = row
            rows.extend(seen.values())
        except Exception as error:
            notes.append(f"U.S. {family} refresh unavailable ({type(error).__name__})")
    try:
        observations = json.loads(fetch(FX_API))["observations"]
        last = max((o for o in observations if (o.get("FXUSDCAD") or {}).get("v")), key=lambda o: o["d"])
        result["fx_usdcad"] = {"value": float(last["FXUSDCAD"]["v"]), "as_of": last["d"], "source": FX_API}
    except Exception:
        result["fx_usdcad"] = None
    result["outstanding_bonds"] = rows
    result["coverage"] = "Public Government of Canada issues and U.S. nominal Treasury notes/bonds. Corporate, municipal, provincial, GIC/CD and other instruments can be added with sourced CSV records; this is not an exhaustive dealer inventory."
    result["refresh_notes"] = notes
    return result


def validate(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """One path for public and uploaded catalogues. Invalid records are reported and excluded."""
    import math
    good, issues, seen = [], [], set()
    for row in rows:
        r = dict(row)
        key = r.get("instrument_id") or r.get("isin")
        try:
            if not key or key in seen:
                raise ValueError("missing or duplicate instrument_id")
            if r.get("currency") not in ("CAD", "USD"):
                raise ValueError("currency must be CAD or USD")
            if not r.get("issuer") or r.get("country") not in ("Canada", "United States"):
                raise ValueError("issuer and Canada/United States country are required")
            if r.get("issuer_type") not in ("sovereign", "provincial", "municipal", "corporate", "deposit"):
                raise ValueError("issuer_type must be explicit; guarantees are never inferred")
            if r.get("instrument_type") not in ("bond", "gic", "cd", "bill", "strip", "floating_rate", "inflation_linked"):
                raise ValueError("unsupported instrument_type")
            if r["instrument_type"] in ("gic", "cd") and r.get("cashflow_type") not in ("annual_payout", "compound_at_maturity"):
                raise ValueError("GIC/CD records require an explicit cashflow_type")
            date.fromisoformat(r["maturity"])
            rate = float(r["coupon_pct"])
            if not math.isfinite(rate) or not 0 <= rate <= 100:
                raise ValueError("invalid coupon/rate")
            if not str(r.get("terms_source", "")).startswith("https://") or not r.get("terms_as_of"):
                raise ValueError("a dated HTTPS source is required")
            date.fromisoformat(r["terms_as_of"])
            r["coupon_pct"], r["instrument_id"] = rate, key
            r["coupon_frequency"] = int(r.get("coupon_frequency") or 2)
            if r["coupon_frequency"] not in (1, 2, 4, 12):
                raise ValueError("unsupported coupon frequency")
            for field in ("benchmark_yield_pct", "auction_yield_pct", "offer_price", "offer_yield_pct"):
                value = r.get(field)
                r[field] = None if value in (None, "") else float(value)
                if r[field] is not None and not math.isfinite(r[field]):
                    raise ValueError(f"non-finite {field}")
            if r["offer_price"] is not None and r["offer_price"] <= 0:
                raise ValueError("offer_price must be positive")
            if r["offer_price"] is not None or r["offer_yield_pct"] is not None:
                date.fromisoformat(r["quote_as_of"])
                if not str(r.get("quote_source", "")).startswith("https://"):
                    raise ValueError("offer prices/yields require a dated HTTPS quote source")
            if r["benchmark_yield_pct"] is not None:
                date.fromisoformat(r["yield_as_of"])
            if r["instrument_type"] in ("gic", "cd"):
                date.fromisoformat(r["quote_as_of"])
                if not str(r.get("quote_source", "")).startswith("https://"):
                    raise ValueError("GIC/CD records require a dated HTTPS offer source")
            seen.add(key)
            good.append(r)
        except (ValueError, KeyError, TypeError) as error:
            issues.append({"instrument_id": key, "status": "excluded", "reason": str(error)})
    return good, issues


def references(fetch=None) -> dict:
    path = folder() / "instruments.csv"
    if path.exists():
        with path.open(newline="") as source:
            rows, issues = validate(list(csv.DictReader(source)))
        context = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else {"terms_source": PAGE, "bonds": []}
        return {**context, "outstanding_bonds": rows, "source_mode": "S3/local catalogue", "quality_issues": issues}
    result = refresh(fetch)
    result["outstanding_bonds"], result["quality_issues"] = validate(result.get("outstanding_bonds", []))
    return result
