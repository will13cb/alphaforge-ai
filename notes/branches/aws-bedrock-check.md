# aws/bedrock-check — Will

**Goal:** one command that says whether our AWS setup works before any agent code depends on it.
**Status:** ready to merge.

## Done
- `scripts/bedrock_check.py` + `make bedrock-check`: region (must be us-east-1), credentials (STS, identity not
  printed), Bedrock text through `dh.llm.ask` (cache off), Bedrock tool use (one Converse call with an `add` tool,
  `toolChoice` auto), S3 put/get/delete under `s3://$S3_BUCKET/healthcheck/`. PASS/FAIL per step with the AWS error.
- README Quick start line. Not in `make test` (tests stay offline).

## How to check it
`make bedrock-check` → `ALL PASS`, exit code 0. Needs `.env` with the event credentials, `AWS_REGION=us-east-1`,
`BEDROCK_MODEL_ID` (copied from the Bedrock console) and `S3_BUCKET`.

## Notes for other agents
- Run `make bedrock-check` before debugging any Bedrock/Strands error: it separates "expired token" and "model access
  not granted" from code bugs.
- Use `toolChoice` auto, never forced (`any`/`tool`): newer Claude models reject forced tool choice with a 400.
- `dh.llm.ask` sends `temperature`; if step "bedrock text" fails with a validation error on temperature while
  "bedrock tool use" passes, the model rejects sampling params: drop `temperature` in `dh.llm.ask`.
- Never print or read `.env`; the script prints only region, model id, bucket and AWS error messages.

## Open questions / blocked on
- Which Bedrock model is enabled on the event account (copy its id into `BEDROCK_MODEL_ID`).
