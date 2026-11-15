"""interface/core/validation.py: typed text → clean value or a short message; limits from the engine's schema."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from dh.agents import extractor  # noqa: E402
from interface.core import validation as v  # noqa: E402


@pytest.mark.parametrize("text,value", [("10 000", 1e4), ("10,000", 1e4), ("10000.5", 10000.5), ("1,5", 1.5),
                                        ("10.000", 1e4), ("10k", 1e4), ("1.2M", 1.2e6), ("$5,000", 5e3),
                                        (" 42 ", 42), ("5 000 $", 5e3)])
def test_numbers_people_type(text, value):
    assert v._number(text) == pytest.approx(value)


@pytest.mark.parametrize("text", ["abc", "12abc", "1/2", "--5", "five", "1e5", "10..5"])
def test_not_numbers(text):
    assert v._number(text) is None


def test_bounds_come_from_the_engine():
    assert v.bounds("age") == extractor.NUMBERS["age"]
    lo, hi = v.bounds("age")
    assert v.whole_number(str(int(lo)), lo, hi).ok and v.whole_number(str(int(hi)), lo, hi).ok
    assert not v.whole_number(str(int(hi) + 1), lo, hi).ok and not v.whole_number(str(int(lo) - 1), lo, hi).ok


def test_whole_number_messages():
    assert v.whole_number("", 18, 100).message == "This answer is needed to continue."
    assert v.whole_number("", 18, 100, required=False).ok
    assert "whole number" in v.whole_number("45.5", 18, 100).message
    assert "digits only" in v.whole_number("forty", 18, 100).message
    assert "between 18 and 100" in v.whole_number("150", 18, 100).message
    assert v.whole_number("45", 18, 100).value == 45


def test_money_and_percent():
    assert not v.money("-5", 0, 1e9).ok and "zero or more" in v.money("-5", -10, 1e9).message
    assert v.money("10,000", 0, 1e9).value == 1e4
    assert v.percent("15%", 0, 100).value == 15 and v.percent("15 %").value == 15
    assert not v.percent("150").ok and "between 0 and 100" in v.percent("150").message
    assert "digits only" in v.percent("lots").message


def test_choices_names_dates_positions():
    assert v.choice("hold", ["hold", "sell_all"]).ok and not v.choice("x", ["hold"]).ok
    assert "choose one option" in v.choice(None, ["hold"]).message
    assert v.choices(["a"], {"a", "b"}).ok and not v.choices(["z"], {"a"}).ok
    assert v.name("Marie-Ève").ok and not v.name("<script>").ok and not v.name("x" * 41).ok and v.name("").ok
    assert v.a_date("2030-06-30").value == date(2030, 6, 30) and v.a_date("30/06/2030").ok
    assert not v.a_date("2030-13-01").ok and not v.a_date("2020-01-01", earliest=date(2026, 1, 1)).ok
    assert not v.date_range(date(2030, 1, 1), date(2029, 1, 1)).ok
    assert v.position("Tesla", "10").value == {"TSLA": 0.10}
    assert v.position("", "").ok and v.position("", "").value is None
    assert not v.position("", "10").ok and not v.position("Tesla", "").ok and not v.position("Tesla", "0").ok
