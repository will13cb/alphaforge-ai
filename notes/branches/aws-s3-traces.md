# aws/s3-traces — Will

**Goal:** every pipeline run saved as JSON in Amazon S3 (`s3://$S3_BUCKET/traces/`), with a local fallback.
**Status:** done, tested offline (S3 faked); first real upload to do on Will's laptop (`make explain P=robert`).

## Done
| Piece | File | What it does |
|---|---|---|
| Trace store | `src/dh/tracestore.py` | `document` (profile, limits, strategies, checks, explanation, trace steps), `save_run` (S3 `put_object`, else `outputs/traces/`), adds a "Trace store" step |
| CLI | `src/dh/__main__.py` | `explain` saves the run by default; `--no-store` to skip |
| Backup | `scripts/backup.sh` | syncs `s3://$S3_BUCKET/traces` → `outputs/traces/`, commits it with `cache/explainer/` |
| Tests | `tests/test_tracestore.py` | S3 put (faked), fallback on AWS error, no bucket → local |

## Decisions made here
- See the newest decision in `notes/decisions.md` ("Every run's trace is saved to Amazon S3").

## Contract changes
- Pipeline result gains `res["stored"]` = {`where`, `run_id`, `stored`: s3|local, `note`}.

## How to check it
```
make test                    # all offline
make explain P=robert        # last trace step: "Trace store → Amazon S3: run … saved to s3://…/traces/…"
aws s3 ls s3://$S3_BUCKET/traces/ --recursive   # (through your AWS profile)
```

## Notes for other agents
- **App:** call `dh.tracestore.save_run(res, profile, persona)` after `explainer.add_to_trace`, and show
  `res["stored"]["where"]` (link to the evidence). Don't write traces anywhere else.
- `S3_BUCKET` and `AWS_REGION=us-east-1` must be in `.env`; without them runs are saved to `outputs/traces/`.
- Run `make backup` Monday morning before the AWS account closes (~11:30 per the event dashboard).

## Open questions / blocked on
1. First real upload (needs the event credentials on Will's laptop).
