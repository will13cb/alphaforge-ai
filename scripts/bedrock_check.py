"""Smoke test of the AWS setup: region, credentials, Bedrock text, Bedrock tool use, S3.

    make bedrock-check        # loads .env for this command only

Never prints credentials or .env contents: only the region, the model id, the bucket name and AWS error messages.
Not part of `make test` (tests stay offline). Exit code 1 if any step fails.
"""

from __future__ import annotations

import os
import sys
import uuid

os.environ["LLM_PROVIDER"] = "bedrock"  # this check is about Bedrock, whatever .env says

import boto3  # noqa: E402
from botocore.exceptions import BotoCoreError, ClientError  # noqa: E402

from dh.llm import ask, model  # noqa: E402

REGION_EXPECTED = "us-east-1"
results: list[tuple[str, bool]] = []


def report(step: str, ok: bool, detail: str) -> None:
    results.append((step, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {step:<18} {detail}")


def why(e: Exception) -> str:
    """AWS error code + message (e.g. AccessDeniedException, ExpiredTokenException), nothing else."""
    if isinstance(e, ClientError):
        err = e.response.get("Error", {})
        return f"{err.get('Code', 'ClientError')}: {err.get('Message', '')}"
    return f"{type(e).__name__}: {e}"


region = os.getenv("AWS_REGION") or boto3.session.Session().region_name or ""
report("region", region == REGION_EXPECTED, f"{region or '(not set)'} (expected {REGION_EXPECTED})")

try:  # catches missing / expired session tokens before the other steps fail with less clear errors
    boto3.client("sts", region_name=region or REGION_EXPECTED).get_caller_identity()
    report("credentials", True, "valid (identity not printed)")
except (ClientError, BotoCoreError) as e:
    report("credentials", False, why(e))

model_id = model()
try:
    reply = ask("Reply with OK", max_tokens=16, cache=False)
    report("bedrock text", bool(reply.strip()), f"model {model_id} replied {reply.strip()[:60]!r}")
except (ClientError, BotoCoreError) as e:
    report("bedrock text", False, f"model {model_id}: {why(e)}")

try:
    resp = boto3.client("bedrock-runtime", region_name=region or REGION_EXPECTED).converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": "What is 2 + 3? Use the add tool."}]}],
        toolConfig={"tools": [{"toolSpec": {
            "name": "add",
            "description": "Add two numbers.",
            "inputSchema": {"json": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                                     "required": ["a", "b"]}},
        }}], "toolChoice": {"auto": {}}},
        inferenceConfig={"maxTokens": 512},
    )
    calls = [b["toolUse"] for b in resp["output"]["message"]["content"] if "toolUse" in b]
    detail = (f"model asked for {calls[0]['name']}({calls[0]['input']})" if calls
              else f"model answered without the tool (stopReason {resp.get('stopReason')})")
    report("bedrock tool use", bool(calls), detail)
except (ClientError, BotoCoreError) as e:
    report("bedrock tool use", False, f"model {model_id}: {why(e)}")

bucket = os.getenv("S3_BUCKET")
if not bucket:
    report("s3", False, "S3_BUCKET is not set in .env")
else:
    key = f"healthcheck/{uuid.uuid4().hex}.txt"
    s3 = boto3.client("s3", region_name=region or REGION_EXPECTED)
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=b"alphaforge healthcheck")
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        s3.delete_object(Bucket=bucket, Key=key)
        report("s3", body == b"alphaforge healthcheck", f"put/get/delete s3://{bucket}/{key}")
    except (ClientError, BotoCoreError) as e:
        report("s3", False, f"s3://{bucket}: {why(e)}")

failed = [s for s, ok in results if not ok]
print(f"\n{'ALL PASS' if not failed else 'FAILED: ' + ', '.join(failed)}")
sys.exit(1 if failed else 0)
