"""Turn what a person typed into a clean value, or a short, friendly message saying what to fix.

No Streamlit here: every function is pure and unit-tested (tests/test_interface_validation.py).
Limits are NOT invented: numeric bounds come from the engine's own profile schema (`extractor.NUMBERS`), choices from
`extractor.ENUMS` / `LISTS` / `SECTORS`. The engine never receives a value that failed here.

Each parser returns a `Check`: ok + value, or ok=False + message (shown in small red text under the field).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from dh.agents import extractor


@dataclass(frozen=True)
class Check:
    ok: bool
    value: object = None
    message: str = ""


EMPTY = Check(True, None, "")
_SPACES = re.compile(r"[\s  ]+")


def bounds(field: str) -> tuple[float, float]:
    """(min, max) the engine accepts for a profile field (single source: the extractor's schema)."""
    return extractor.NUMBERS[field]


def _clean(text) -> str:
    return _SPACES.sub(" ", str(text if text is not None else "")).strip()


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}".rstrip("0").rstrip(".")


def _number(text: str) -> float | None:
    """'10 000', '10,000', '10000.5', '1,5' (decimal comma), '10k', '1.2M', '$5,000' → float; None if not a number."""
    t = _clean(text).replace("$", "").replace("CAD", "").replace("cad", "").strip()
    if not t:
        return None
    m = re.fullmatch(r"([+-]?)\s*([\d., ]+)\s*([kKmM]?)", t)
    if not m:
        return None
    sign, digits, unit = m.groups()
    digits = digits.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", digits):        # 10,000 or 10,000.50
        digits = digits.replace(",", "")
    elif re.fullmatch(r"\d+,\d{1,2}", digits):                     # 1,5 (decimal comma)
        digits = digits.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", digits):              # 10.000 (dot thousands)
        digits = digits.replace(".", "")
    if not re.fullmatch(r"\d+(\.\d+)?|\.\d+", digits):
        return None
    v = float(digits) * {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6}.get(unit, 1)
    return -v if sign == "-" else v


def _in_range(v: float, lo: float, hi: float, what: str) -> Check:
    if v < lo or v > hi:
        return Check(False, None, f"Please enter {what} between {_fmt(lo)} and {_fmt(hi)}.")
    return Check(True, v)


def required_missing(text, required: bool) -> Check | None:
    if _clean(text) == "":
        return Check(False, None, "This answer is needed to continue.") if required else EMPTY
    return None


def whole_number(text, lo: float, hi: float, required: bool = True, unit: str = "a whole number") -> Check:
    miss = required_missing(text, required)
    if miss is not None:
        return miss
    v = _number(text)
    if v is None:
        return Check(False, None, "Please enter a whole number (digits only).")
    if not float(v).is_integer():
        return Check(False, None, "Please enter a whole number, without decimals.")
    return _in_range(int(v), lo, hi, unit)


def decimal(text, lo: float, hi: float, required: bool = True, unit: str = "a number") -> Check:
    miss = required_missing(text, required)
    if miss is not None:
        return miss
    v = _number(text)
    if v is None:
        return Check(False, None, "Please enter a number (e.g. 4 or 4.5).")
    return _in_range(v, lo, hi, unit)


def money(text, lo: float, hi: float, required: bool = True) -> Check:
    miss = required_missing(text, required)
    if miss is not None:
        return miss
    v = _number(text)
    if v is None:
        return Check(False, None, "Please enter an amount in dollars, digits only (e.g. 10,000).")
    if v < 0:
        return Check(False, None, "Please enter an amount that is zero or more.")
    return _in_range(v, lo, hi, "an amount")


def percent(text, lo: float = 0, hi: float = 100, required: bool = True) -> Check:
    """Typed as a percentage: '15', '15%', '15 %' → 15.0 (percent points, as the engine's max_loss_pct)."""
    miss = required_missing(text, required)
    if miss is not None:
        return miss
    v = _number(_clean(text).rstrip("%").strip())
    if v is None:
        return Check(False, None, "Please enter a percentage, digits only (e.g. 15 for 15%).")
    if v < lo or v > hi:
        return Check(False, None, f"Please enter a percentage between {_fmt(lo)} and {_fmt(hi)}.")
    return Check(True, v)


def choice(value, options: list, required: bool = True) -> Check:
    if value in (None, "", []):
        return Check(False, None, "Please choose one option.") if required else EMPTY
    if value not in options:
        return Check(False, None, "Please choose one of the options shown.")
    return Check(True, value)


def choices(values, options: list | set) -> Check:
    values = list(values or [])
    bad = [v for v in values if v not in options]
    return Check(False, None, "Please choose only from the options shown.") if bad else Check(True, values)


def name(text, required: bool = False, max_len: int = 40) -> Check:
    t = _clean(text)
    if not t:
        return Check(False, None, "Please enter a name.") if required else EMPTY
    if len(t) > max_len:
        return Check(False, None, f"Please keep it under {max_len} characters.")
    if not re.search(r"[A-Za-zÀ-ÿ]", t) or re.search(r"[<>{}\\|$%#@*=;]", t):
        return Check(False, None, "Please enter a valid name (letters, spaces, hyphens).")
    return Check(True, t)


def a_date(text, earliest: date | None = None, latest: date | None = None, required: bool = True) -> Check:
    """YYYY-MM-DD (also accepts DD/MM/YYYY)."""
    miss = required_missing(text, required)
    if miss is not None:
        return miss
    t = _clean(text)
    try:
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", t):
            d, m, y = map(int, t.split("/"))
            v = date(y, m, d)
        else:
            v = date.fromisoformat(t)
    except ValueError:
        return Check(False, None, "Please enter a valid date, e.g. 2030-06-30.")
    if earliest and v < earliest:
        return Check(False, None, f"Please enter a date on or after {earliest.isoformat()}.")
    if latest and v > latest:
        return Check(False, None, f"Please enter a date on or before {latest.isoformat()}.")
    return Check(True, v)


def date_range(start: date, end: date) -> Check:
    if end <= start:
        return Check(False, None, "The end date must come after the start date.")
    return Check(True, (start, end))


def position(text_name: str, text_pct) -> Check:
    """A requested holding: a company or fund name or ticker + a percentage of the portfolio (0 < % <= 100)."""
    n = _clean(text_name)
    if not n and _clean(text_pct) == "":
        return EMPTY
    if not n:
        return Check(False, None, "Please enter the name of the company or fund (e.g. Tesla).")
    p = percent(text_pct, 0, 100, required=True)
    if not p.ok:
        return p
    if p.value == 0:
        return Check(False, None, "Please enter a percentage above 0.")
    return Check(True, {extractor.ticker_of(n): p.value / 100})
