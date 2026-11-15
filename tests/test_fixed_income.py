"""Dated fixed-income matching and cash flows; no network, model, or market backtest."""
import sys
import types
from datetime import date

import pytest

from dh import bond_rates
from dh.agents import fixed_income
from dh.fixed_income import project

TODAY = date(2026, 11, 15)


def instrument(**changes):
    row = {
        "instrument_id": "CA135087P329", "isin": "CA135087P329",
        "issuer": "Government of Canada", "issuer_type": "sovereign",
        "country": "Canada", "currency": "CAD", "instrument_type": "bond",
        "maturity": "2036-11-15", "coupon_pct": 3.25, "coupon_frequency": 2,
        "terms_source": bond_rates.OUTSTANDING, "terms_as_of": "2026-11-12",
        "benchmark_yield_pct": 3.78, "yield_as_of": "2026-11-12",
        "offer_price": None,
    }
    return {**row, **changes}


def profile(**changes):
    return {"capital": 300_000, "horizon_years": 10, "fixed_rate_pct": 3,
            "max_loss_pct": 0, "fixed_income_market": "both", **changes}


def reference(*rows, fx=None):
    return {"outstanding_bonds": list(rows), "bonds": [], "terms_source": bond_rates.PAGE,
            "fx_usdcad": fx}


def test_zero_loss_bond_request_gets_separate_held_to_maturity_plan():
    result = fixed_income.run(profile(), reference(instrument()), TODAY)
    assert result["status"] == "quote_required"
    assert result["allocation"] == {"CA135087P329": 1.0}
    assert result["selected_bond"]["coupon_pct"] == 3.25
    assert result["annual_interest"] == 9_750
    assert any("assumed par price" in line for line in result["assumptions"])
    assert any("zero-loss guarantee" in line for line in result["assumptions"])


def test_unsupported_eighteen_percent_request_does_not_invent_a_bond():
    result = fixed_income.run(profile(fixed_rate_pct=18), reference(instrument()), TODAY)
    assert result["status"] == "unavailable"
    assert result["allocation"] == {}
    assert "cannot promise" in result["message"]
    assert "selected_bond" not in result


def test_twenty_year_horizon_uses_nearby_actual_maturity_without_extending_income():
    bond = instrument(maturity="2045-12-01", coupon_pct=3.5, benchmark_yield_pct=None)
    result = fixed_income.run(profile(horizon_years=20), reference(bond), TODAY)
    assert result["status"] == "quote_required"
    assert result["maturity_date"] == "2045-12-01"
    assert result["schedule"][-1]["date"] == "2045-12-01"
    assert all(row["date"] <= "2045-12-01" for row in result["schedule"])


def test_canadian_preference_and_explicit_us_selection():
    us = instrument(instrument_id="91282CRX1", isin=None, country="United States",
                    issuer="U.S. Treasury", currency="USD", coupon_pct=5)
    ref = reference(us, instrument(), fx={"value": 1.4, "as_of": "2026-11-12"})
    assert fixed_income.run(profile(), ref, TODAY)["currency"] == "CAD"
    result = fixed_income.run(profile(capital=140_000, fixed_income_market="us"), ref, TODAY)
    assert result["currency"] == "USD"
    assert result["capital"] == 100_000
    assert result["annual_interest"] == 5_000
    assert result["budget_cad"] == 140_000
    assert result["allocation"] == {"91282CRX1": 1.0}
    assert any("exchange-rate changes" in line for line in result["assumptions"])


def test_us_bond_without_dated_fx_does_not_treat_cad_as_usd():
    us = instrument(country="United States", currency="USD", issuer="U.S. Treasury")
    result = fixed_income.run(profile(fixed_income_market="us"), reference(us), TODAY)
    assert result["status"] == "unavailable"
    assert "USD/CAD" in result["message"]
    assert result["allocation"] == {}


def test_auction_yield_is_not_presented_as_a_current_purchase_yield():
    # A historic auction yield cannot make a current 3% coupon satisfy a 4% request.
    bond = instrument(coupon_pct=3, benchmark_yield_pct=None, auction_yield_pct=5)
    result = fixed_income.run(profile(fixed_rate_pct=4), reference(bond), TODAY)
    assert result["status"] == "unavailable"


def test_zero_loss_request_does_not_imply_corporate_guarantee():
    bond = instrument(issuer="Example issuer", issuer_type="corporate", coupon_pct=18,
                      benchmark_yield_pct=None)
    result = fixed_income.run(profile(fixed_rate_pct=18), reference(bond), TODAY)
    assert result["status"] == "unavailable"


def test_par_purchase_on_coupon_date_preserves_financial_identities():
    result = project(profile(capital=100_000), instrument(coupon_pct=3), TODAY)
    assert len(result["schedule"]) == 20
    assert all(row["interest"] == 1_500 for row in result["schedule"])
    assert sum(row["principal_repaid"] for row in result["schedule"]) == 100_000
    assert result["total_interest"] == 30_000
    assert result["total_cash_paid"] == 130_000


def test_purchase_between_coupons_accounts_for_accrued_interest():
    result = project(profile(capital=100_000), instrument(maturity="2036-06-01", coupon_pct=3), TODAY)
    accrued_per_100 = 1.5 * (TODAY - date(2026, 6, 1)).days / (date(2026, 12, 1) - date(2026, 6, 1)).days
    face = 100_000 * 100 / (100 + accrued_per_100)
    assert result["principal_at_maturity"] == pytest.approx(face, abs=.005)
    assert result["annual_interest"] == pytest.approx(face * .03, abs=.005)
    assert result["principal_at_maturity"] < result["capital"]
    assert result["schedule"][0]["date"] == "2026-12-01"


def test_benchmark_parser_keeps_coupon_and_latest_yield_distinct():
    series = bond_rates.SERIES["10 year"]
    parsed = bond_rates.parse("<p>10 year - 2036.06.01, 3.25%</p>", {"observations": [
        {"d": "2026-11-12", series: {"v": "3.78"}},
        {"d": "2026-11-10", series: {"v": "3.70"}},
    ]})
    bond = parsed["bonds"][0]
    assert bond["coupon_pct"] == 3.25
    assert bond["benchmark_yield_pct"] == 3.78
    assert bond["yield_as_of"] == "2026-11-12"
    assert bond["offer_price"] is None


def test_catalogue_validation_normalizes_csv_and_reports_rejected_records():
    valid = instrument(coupon_pct="3.25", coupon_frequency="2", offer_price="", benchmark_yield_pct="3.78")
    good, issues = bond_rates.validate([
        valid, dict(valid), instrument(instrument_id="bad-source", terms_source="http://example.com"),
        instrument(instrument_id="bad-rate", coupon_pct="nan"),
        instrument(instrument_id="bad-date", terms_as_of="yesterday"),
    ])
    assert len(good) == 1
    assert good[0]["coupon_pct"] == 3.25
    assert good[0]["coupon_frequency"] == 2
    assert good[0]["offer_price"] is None
    assert len(issues) == 4
    assert all(row["status"] == "excluded" for row in issues)


@pytest.mark.parametrize("field,value", [("offer_price", -1), ("offer_price", 0)])
def test_catalogue_rejects_nonpositive_purchase_prices(field, value):
    good, issues = bond_rates.validate([instrument(**{field: value})])
    assert not good
    assert len(issues) == 1


def test_fixed_income_s3_download_is_independent_of_market_dataset(tmp_path, monkeypatch):
    from dh import bootstrap

    downloads = []

    class Client:
        def download_file(self, bucket, key, destination):
            downloads.append((bucket, key))
            from pathlib import Path
            Path(destination).write_text("{}" if key.endswith(".json") else "instrument_id\n")

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda *a, **kw: Client()))
    monkeypatch.setattr(bootstrap, "load_config", lambda: types.SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setenv("AF_AUTO_DATA", "1")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    assert bootstrap.ensure_fixed_income() == "loaded"
    assert downloads[-1] == ("test-bucket", "raw/fixed_income/instruments.csv")
    assert {key for _, key in downloads} == {
        "raw/fixed_income/reference_snapshot.json", "raw/fixed_income/sources_metadata.csv",
        "raw/fixed_income/quality_report.csv", "raw/fixed_income/instruments.csv",
    }
    assert not (tmp_path / "prices_daily.csv").exists()
    assert bootstrap.ensure_fixed_income() == "present"
    assert len(downloads) == 4


def test_fixed_income_pipeline_and_explainer_do_not_require_market_data_or_llm(monkeypatch):
    from dh.agents import explainer, pipeline

    def unexpected(*args, **kwargs):
        pytest.fail("Held-to-maturity lookup must not require market portfolio calculations")

    monkeypatch.setattr(bond_rates, "references", lambda: reference(instrument()))
    monkeypatch.setattr(pipeline, "derive_limits", unexpected)
    monkeypatch.setattr(pipeline, "data_columns", unexpected)
    monkeypatch.setattr(explainer, "_run_agent", unexpected)
    p = profile(investment_mode="fixed_rate")
    result = pipeline.run(p)
    explainer.add_to_trace(result, p)
    assert result["strategies"] == []
    assert result["fixed_income_scenario"]["status"] == "quote_required"
    assert result["explanation"]["source"] == "fixed_rate"


@pytest.mark.parametrize("callable_flag", [True, "true", "Yes", "1"])
def test_callable_bonds_do_not_promise_full_term_coupon_income(callable_flag):
    result = fixed_income.run(profile(), reference(instrument(callable=callable_flag)), TODAY)
    assert result["status"] == "unavailable"


@pytest.mark.parametrize("kind", ["gic", "cd"])
def test_deposit_annual_payout_returns_principal_and_pays_interest_each_year(kind):
    bond = instrument(instrument_type=kind, maturity="2028-11-15", coupon_pct=3,
                      cashflow_type="annual_payout")
    result = project(profile(capital=100_000, horizon_years=2), bond, TODAY)
    assert result["kind"] == "sourced_deposit_illustration"
    assert result["annual_interest"] == 3_000
    assert result["total_interest"] == 6_000
    assert result["schedule"] == [
        {"date": "2027-11-15", "interest": 3_000, "principal_repaid": 0},
        {"date": "2028-11-15", "interest": 3_000, "principal_repaid": 100_000},
    ]


@pytest.mark.parametrize("kind", ["gic", "cd"])
def test_deposit_compounding_pays_only_at_maturity_using_calendar_year_term(kind):
    bond = instrument(instrument_type=kind, maturity="2028-11-15", coupon_pct=3,
                      cashflow_type="compound_at_maturity")
    result = project(profile(capital=100_000, horizon_years=2), bond, TODAY)
    assert result["annual_interest"] == 0
    assert result["total_interest"] == 6_090
    assert result["total_cash_paid"] == 106_090
    assert result["schedule"] == [
        {"date": "2028-11-15", "interest": 6_090, "principal_repaid": 100_000},
    ]


def test_deposit_payout_convention_is_required():
    with pytest.raises(ValueError, match="payout terms"):
        project(profile(), instrument(instrument_type="gic"), TODAY)


def test_wizard_preserves_fixed_income_mode_rate_market_and_profile_fields():
    from dh.agents.scenarios import DEMO_PROFILES
    from interface.core import wizard

    p = {**DEMO_PROFILES["robert"], "investment_mode": "fixed_rate",
         "fixed_rate_pct": 3.5, "fixed_income_market": "us"}
    values, errors = wizard.all_values(wizard.from_profile(p))
    assert not errors
    result = wizard.to_profile(values)
    for field in ("investment_mode", "fixed_rate_pct", "fixed_income_market", "capital", "horizon_years"):
        assert result[field] == p[field]


@pytest.mark.parametrize("client_text", ["I want a bond at 3% for 10 years.", "Je veux une obligation à 3% pour 10 ans."])
def test_free_text_identifies_explicit_bond_rate(client_text):
    from dh.agents import extractor

    result, _ = extractor.validate({}, client_text)
    assert result["investment_mode"] == "fixed_rate"
    assert result["fixed_rate_pct"] == 3


def test_free_text_loss_limit_is_not_a_fixed_bond_interest_rate():
    from dh.agents import extractor

    result, _ = extractor.validate({"max_loss_pct": 3}, "I want bonds. My maximum loss is 3%.")
    assert result["max_loss_pct"] == 3
    assert result.get("investment_mode") != "fixed_rate"


def test_results_view_renders_bond_plan_without_no_strategies_error():
    from streamlit.testing.v1 import AppTest

    from dh.agents import explainer
    from dh.agents.trace import Trace

    p = profile(investment_mode="fixed_rate")
    plan = fixed_income.run(p, reference(instrument()), TODAY)
    result = {"fixed_income_scenario": plan, "strategies": [], "trace": Trace()}
    explainer.add_to_trace(result, p)
    app = AppTest.from_string("from interface.views.results import render\nrender()", default_timeout=20)
    app.session_state["res"] = result
    app.session_state["profile"] = p
    app.run()
    assert not app.exception
    assert any(element.value == "100% Government of Canada" for element in app.subheader)
    assert any(metric.label == "Maturity" and metric.value == "2036-11-15" for metric in app.metric)
    assert not app.error
    assert not any("No strategy fits" in element.value for element in app.markdown)


def test_dated_yield_candidate_preferred_to_nearer_high_coupon_without_price():
    older = instrument(instrument_id="OLD", coupon_pct=5, maturity="2036-11-15", benchmark_yield_pct=None)
    benchmark = instrument(instrument_id="BENCHMARK", maturity="2036-06-01", benchmark_yield_pct=3.78)
    result = fixed_income.run(profile(), reference(older, benchmark), TODAY)
    assert result["selected_bond"]["instrument_id"] == "BENCHMARK"
