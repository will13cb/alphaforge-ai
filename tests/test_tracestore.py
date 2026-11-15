"""Trace store: S3 when available, local fallback otherwise. Offline (S3 faked)."""
import json

from dh import tracestore
from dh.agents.trace import Trace


def _res():
    tr = Trace()
    tr.step("Profiler", "Portfolio", "risk level 2")
    return {"limits": {"loss_limit": 0.15}, "verdict": "pass", "strategies": [{"name": "Broad core"}],
            "explanation": {"text": "hello", "source": "template"}, "trace": tr}


def test_s3_put(monkeypatch):
    sent = {}
    monkeypatch.setattr(tracestore, "_put_s3", lambda b, k, body: sent.update(bucket=b, key=k, doc=json.loads(body)))
    res = _res()
    out = tracestore.save_run(res, {"name": "Robert"}, persona="robert", bucket="team-bucket")
    assert out["stored"] == "s3" and out["where"].startswith("s3://team-bucket/traces/")
    assert sent["doc"]["persona"] == "robert" and sent["doc"]["trace"][0]["agent"] == "Profiler"
    assert res["trace"].steps[-1]["agent"] == "Trace store" and res["trace"].steps[-1]["to"] == "Amazon S3"


def test_local_fallback_when_s3_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(tracestore, "LOCAL_DIR", tmp_path)
    def boom(*a):
        raise RuntimeError("ExpiredToken")
    monkeypatch.setattr(tracestore, "_put_s3", boom)
    res = _res()
    out = tracestore.save_run(res, {"name": "Robert"}, persona="robert", bucket="team-bucket")
    assert out["stored"] == "local" and "ExpiredToken" in out["note"]
    saved = list(tmp_path.rglob("*.json"))
    assert len(saved) == 1 and json.loads(saved[0].read_text())["explanation"]["text"] == "hello"
    assert res["trace"].steps[-1]["to"] == "local disk"


def test_no_bucket_goes_local(monkeypatch, tmp_path):
    monkeypatch.setattr(tracestore, "LOCAL_DIR", tmp_path)
    monkeypatch.delenv("S3_BUCKET", raising=False)
    assert tracestore.save_run(_res(), {}, persona="amira")["stored"] == "local"
