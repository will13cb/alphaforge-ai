"""Trace store: every pipeline run saved as one JSON document, in Amazon S3, with a local fallback.

    from dh.tracestore import save_run
    where = save_run(res, profile, persona="robert")   # → "s3://<bucket>/traces/2026-11-15/<run_id>.json"

S3 is where the run's evidence lives (decision #14, slide 7: AWS does real work in the flow): the client's facts, the
limits and their reasons, the strategies, the Guardian's checks, the Explainer's text and every hand-off of the trace.
Never the model's raw reasoning (#9). Bucket from S3_BUCKET (set in .env, loaded by `make`), region from AWS_REGION.

If S3_BUCKET is unset or AWS can't be reached (expired session token, offline demo, Friday after the account closes),
the same JSON goes to outputs/traces/ and the run says so: the demo never breaks.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .data import ROOT

PREFIX = "traces"
LOCAL_DIR = ROOT / "outputs" / "traces"


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=ROOT, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def document(res: dict, profile: dict, persona: str = "") -> dict:
    """The JSON saved for one run (fictional profile, no secrets, no raw model reasoning)."""
    now = datetime.now(timezone.utc)
    e = res.get("explanation") or {}
    return {
        "run_id": f"{now:%Y%m%dT%H%M%S}-{persona or 'client'}-{uuid.uuid4().hex[:6]}",
        "created": now.isoformat(timespec="seconds"),
        "commit": _commit(),
        "persona": persona,
        "profile": profile,
        "limits": res.get("limits"),
        "verdict": res.get("verdict"),
        "strategies": res.get("strategies", []),
        "dropped": [{"name": s.get("name"), "guardian": s.get("guardian")} for s in res.get("dropped", [])],
        "explanation": {k: e.get(k) for k in ("text", "source", "model", "check_calls", "checks", "verdict",
                                             "facts_hash", "note")} if e else None,
        "trace": res["trace"].steps if res.get("trace") is not None else [],
    }


def _put_s3(bucket: str, key: str, body: bytes) -> None:
    import boto3

    boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1")).put_object(
        Bucket=bucket, Key=key, Body=body, ContentType="application/json")


def save_run(res: dict, profile: dict, persona: str = "", bucket: str | None = None) -> dict:
    """Save the run; returns {where, run_id, stored: "s3" | "local", note}. Adds a 'Trace store' step to the trace."""
    doc = document(res, profile, persona)
    body = json.dumps(doc, ensure_ascii=False, indent=1, default=str).encode()
    key = f"{PREFIX}/{doc['created'][:10]}/{doc['run_id']}.json"
    bucket = bucket if bucket is not None else os.getenv("S3_BUCKET", "")
    note = ""
    if bucket:
        try:
            _put_s3(bucket, key, body)
            out = {"where": f"s3://{bucket}/{key}", "run_id": doc["run_id"], "stored": "s3", "note": ""}
        except Exception as ex:  # noqa: BLE001 — any AWS error → local copy, said in the trace
            note = f"S3 unavailable ({type(ex).__name__}: {str(ex)[:150]}), saved locally"
            out = None
    else:
        note = "S3_BUCKET not set, saved locally"
        out = None
    if out is None:
        p = LOCAL_DIR / doc["created"][:10] / f"{doc['run_id']}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        where = str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
        out = {"where": where, "run_id": doc["run_id"], "stored": "local", "note": note}
    if res.get("trace") is not None:
        res["trace"].step("Trace store", "Amazon S3" if out["stored"] == "s3" else "local disk",
                          f"run {out['run_id']} saved to {out['where']}" + (f" ({note})" if note else ""))
    res["stored"] = out
    return out


def save_run_safe(res: dict, profile: dict, persona: str = "") -> dict | None:
    """`save_run` that never raises (for the apps): saving the evidence must never break the screen. On failure it
    returns None, and `res["stored"]` says why."""
    try:
        return save_run(res, profile, persona)
    except Exception as ex:  # noqa: BLE001 — e.g. the local disk is read-only
        res["stored"] = {"where": "", "run_id": "", "stored": "none", "note": f"not saved ({type(ex).__name__}: {ex})"[:200]}
        return None
