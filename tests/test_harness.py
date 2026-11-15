"""Smoke tests only: imports work, metrics are right, logging works, LLM mock is offline."""
import pytest

from dh import PERSONAS, board, describe, load_config, log_run
from dh.metrics import max_drawdown, sharpe


def test_config_and_personas():
    assert load_config().base_currency in {"CAD", "USD"}
    assert set(PERSONAS) == {"amira", "mateo", "robert"}


def test_metrics_and_log(tmp_path):
    assert max_drawdown([0.1, -0.5, 0.2]) == pytest.approx(-0.5)
    assert sharpe([0.01, 0.02, 0.015]) > 0
    res = tmp_path / "r.csv"
    log_run(0.5, "gov", "pass_rate", persona="robert", results=res)
    log_run(0.9, "gov", "pass_rate", persona="robert", results=res)
    assert board(res).value.tolist() == [0.9]


def test_llm_mock(monkeypatch):
    from dh.llm import ask

    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert ask("hi").startswith("[mock]")


def test_simulated_personas_fit_the_brief():
    """Audit P11: the pipeline's personas (scenarios) must match the brief's (personas) on the common fields."""
    from dh.agents.scenarios import DEMO_PROFILES

    for k, brief in PERSONAS.items():
        sim = DEMO_PROFILES[k]
        assert sim["age"] == brief["age"] and sim["name"] == brief["name"]
        lo, _, hi = brief["horizon_years"].rstrip("+").partition("-")
        assert float(lo) <= sim["horizon_years"] <= (float(hi) if hi else 99), (k, sim["horizon_years"])
        assert "Simulated as" in describe(k) and "Simulated as" not in describe(k, simulated=False)


def test_bootstrap_builds_only_when_asked(monkeypatch, tmp_path):
    """Hosted copy: data/raw is built only with AF_AUTO_DATA=1; never a download by surprise on a laptop."""
    from dh import bootstrap, data

    cfg = data.Config(data_dir=tmp_path)
    monkeypatch.setattr(bootstrap, "load_config", lambda: cfg)
    monkeypatch.delenv("AF_AUTO_DATA", raising=False)
    ok, note = bootstrap.ensure_data()
    assert not ok and "AF_AUTO_DATA" in note

    calls = []

    class FakeBuild:
        @staticmethod
        def main(argv):
            calls.append(argv)
            for f in bootstrap.FILES:
                (tmp_path / f).write_text("x")
    monkeypatch.setenv("AF_AUTO_DATA", "1")
    monkeypatch.setattr(bootstrap.importlib.util, "module_from_spec", lambda spec: FakeBuild)
    monkeypatch.setattr(type(bootstrap.importlib.util.spec_from_file_location("x", __file__).loader), "exec_module",
                        lambda self, m: None)
    assert bootstrap.ensure_data() == (True, "") and calls[0][:2] == ["--start", bootstrap.build_start()]
    assert bootstrap.ensure_data() == (True, "") and len(calls) == 1       # built once


def test_build_start_follows_harness(monkeypatch):
    from dh import bootstrap, data
    monkeypatch.setattr(bootstrap, "load_config", lambda: data.Config(start="2010-01-04"))
    assert bootstrap.build_start() == "2010-01-04"
    monkeypatch.setattr(bootstrap, "load_config", lambda: data.Config(start=""))
    assert bootstrap.build_start() == bootstrap.STARTER_START
