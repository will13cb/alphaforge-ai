"""interface/core/services.py: the one door to the engine. Offline; the pipeline is replaced where data is needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from dh.agents.scenarios import ROBERT  # noqa: E402
from interface.core import services  # noqa: E402


@pytest.fixture(autouse=True)
def _log_to_tmp(tmp_path, monkeypatch):
    import logging
    log = logging.getLogger("interface")

    def ours():
        for h in [h for h in log.handlers if getattr(h, "af_interface", False)]:
            log.removeHandler(h)
            h.close()

    monkeypatch.setattr(services, "LOG_DIR", tmp_path)
    monkeypatch.setattr(services.tracestore, "LOCAL_DIR", tmp_path / "traces")  # never write to outputs/ in tests
    monkeypatch.delenv("S3_BUCKET", raising=False)
    ours()
    yield
    ours()


def test_incomplete_profile_is_refused_before_the_engine(monkeypatch):
    monkeypatch.setattr(services.pipeline, "run", lambda p: pytest.fail("engine must not be called"))
    with pytest.raises(services.UserError, match="missing"):
        services.run_analysis({"age": 40})


def test_missing_data_is_a_plain_message(monkeypatch):
    monkeypatch.setattr(services, "data_ready", lambda: (False, services.NO_DATA))
    with pytest.raises(services.UserError, match="market data is not installed"):
        services.run_analysis(dict(ROBERT))


def test_systemexit_from_the_data_layer_becomes_a_user_error(monkeypatch):
    monkeypatch.setattr(services, "data_ready", lambda: (True, ""))
    monkeypatch.setattr(services.pipeline, "run", lambda p: (_ for _ in ()).throw(SystemExit("prices missing")))
    with pytest.raises(services.UserError, match="make data"):
        services.run_analysis(dict(ROBERT))


def test_a_crash_is_logged_with_a_reference_and_never_shown(monkeypatch, tmp_path):
    monkeypatch.setattr(services, "data_ready", lambda: (True, ""))
    monkeypatch.setattr(services.pipeline, "run", lambda p: 1 / 0)
    with pytest.raises(services.InternalError) as e:
        services.run_analysis(dict(ROBERT))
    msg = str(e.value)
    assert "ZeroDivision" not in msg and "Traceback" not in msg and e.value.ref in msg
    log = (tmp_path / "interface.log").read_text()
    assert e.value.ref in log and "ZeroDivisionError" in log and "Traceback" in log


def test_analyst_inputs_are_checked(monkeypatch):
    with pytest.raises(services.UserError, match="type a question"):
        services.ask_analyst("   ", {"strategies": [1]}, ROBERT)
    with pytest.raises(services.UserError, match="Run the analysis first"):
        services.ask_analyst("hello", {}, ROBERT)
    seen = {}

    def fake(q, res, profile, history=None):
        seen.update(q=q, history=history)
        return {"answer": "ok " + services.DISCLAIMER, "status": "valid", "tool_calls": [], "source": "mock"}

    monkeypatch.setattr(services.analyst, "ask", fake)
    a = services.ask_analyst("x" * 2000, {"strategies": [1]}, ROBERT,
                             history=[{"question": "q1", "answer": "a1", "status": "done"}, {"answer": "orphan"}])
    assert a["cut"] and len(seen["q"]) == services.MAX_QUESTION and a["text"] == "ok"
    assert seen["history"] == [{"question": "q1", "answer": "a1"}]


def test_analyst_crash_is_an_internal_error(monkeypatch):
    monkeypatch.setattr(services.analyst, "ask", lambda *a, **k: {}["boom"])
    with pytest.raises(services.InternalError):
        services.ask_analyst("What if I put 10% in Tesla?", {"strategies": [1]}, ROBERT)


def test_free_text_and_mode():
    with pytest.raises(services.UserError):
        services.extract_text("hi")
    ex = services.extract_text("I'm 45, I have 50,000 $ to invest for retirement in 20 years. Stable income.")
    assert ex["profile"]["age"] == 45 and "missing" in ex
    m = services.mode()
    assert m["live"] is False and "Offline" in m["label"] and "may not understand" in m["help"]


def _fake_engine(monkeypatch):
    from dh.agents.trace import Trace
    tr = Trace()
    tr.step("Profiler", "Portfolio", "risk level 2")
    res = {"limits": {"loss_limit": 0.15}, "verdict": "pass", "strategies": [{"name": "Broad core"}], "trace": tr}
    monkeypatch.setattr(services, "data_ready", lambda: (True, ""))
    monkeypatch.setattr(services.pipeline, "run", lambda p: res)
    monkeypatch.setattr(services.explainer, "add_to_trace", lambda r, p: {})
    return res


def test_each_analysis_is_stored_local_copy_when_no_s3(monkeypatch, tmp_path):
    res = _fake_engine(monkeypatch)
    services.run_analysis(dict(ROBERT))
    assert res["stored"]["stored"] == "local" and list((tmp_path / "traces").rglob("*.json"))
    assert res["trace"].steps[-1]["agent"] == "Trace store"


def test_s3_goes_to_the_bucket_and_a_store_crash_never_blocks(monkeypatch):
    res = _fake_engine(monkeypatch)
    monkeypatch.setenv("S3_BUCKET", "team-bucket")
    monkeypatch.setattr(services.tracestore, "_put_s3", lambda b, k, body: None)
    assert services.run_analysis(dict(ROBERT))["stored"]["where"].startswith("s3://team-bucket/traces/")
    monkeypatch.setattr(services.tracestore, "save_run", lambda *a, **k: 1 / 0)
    assert services.run_analysis(dict(ROBERT)) is res  # analysis still returned
