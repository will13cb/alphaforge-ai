# agents/explainer — Will

**Goal:** the Explainer as a Strands agent on Amazon Bedrock (Claude Opus 5.5): writes the client text from the
strategies, limits and reasons; the Guardian checks it (G11–G13); offline mock + committed demo cache.
**Status:** built and tested offline (agent faked); **not yet run against Bedrock** (needs your `.env`).
Branched from `lane/portfolio` at `612d6f1` (needs its strategies): **merge `lane/portfolio` first**, then this.

## Done

| Piece | File | What it does | LLM? |
|---|---|---|---|
| Explainer | `src/dh/agents/explainer.py` | `facts` (pre-formatted numbers + reasons + refusals), `template` (passes G11–G13 by construction), `_run_agent` (Strands Agent + BedrockModel + `check_text` tool), `explain` (caches → agent → Guardian re-check → template fallback), `save_demo`, `add_to_trace` | yes (Bedrock), mock offline |
| CLI | `src/dh/__main__.py` | `python -m dh explain amira\|mateo\|robert [--save-demo]` | |
| Make | `Makefile` | `make explain P=robert [SAVE=1]` (loads `.env`); `make setup` installs `.[dev,agents]` | |
| Deps | `pyproject.toml` | extra `agents = ["strands-agents>=1.65"]` (imported lazily: tests don't need it) | |
| Demo cache | `cache/explainer/` | committed Bedrock texts, replayed in mock mode | |
| Tests | `tests/test_explainer.py` | 7 offline: template passes, facts stable, agent text used + cached, invented number → template, AWS error → template, demo cache replays offline, trace steps | no |

`pipeline.py` untouched (it's being edited elsewhere): `explainer.add_to_trace(res, profile)` plugs in after `pipeline.run`.

## Decisions made here
- #23 Explainer design, caching, rule 5 exception for Strands. (#20 reserved for `portfolio/checks`.)

## Contract changes
- New §2b: Explainer output (`text`, `source`, `model`, `check_calls`, `checks`, `verdict`, `facts_hash`, `note`).

## How to check it
```
make test                                   # 54 passed (7 explainer), offline
make explain P=robert                       # with LLM_PROVIDER=bedrock + BEDROCK_EXPLAINER_MODEL_ID in .env
make explain P=robert SAVE=1                # then commit cache/explainer/*.json for the offline demo
```
Expected with Bedrock: `source: bedrock`, `verdict: pass` (or `template` with a note saying which rule failed).

## Notes for other agents
- **#24 changed the limits:** use `limits["company_caps"][ticker]`, not one `max_single` for every company (it is now
  just the largest cap, for display). Requests that don't fit come with `limits["request_checks"]` (numbers + reason).
  Tests pin the worst drops (`tests/conftest.py`): pass `drops=` to `derive_limits` / `pipeline.run` if you need others.
- **Tone:** never "refused" in client text; give the numbers and what fits (prompt v2). The demo cache was re-saved
  for the three personas after #24 (`cache/explainer/`); re-save again after any rule or data change.
- **Set `BEDROCK_EXPLAINER_MODEL_ID`** in `.env` (Opus 5.5 id or `us.` inference profile from the console, us-east-1);
  `LLM_PROVIDER=bedrock` to call it. Never put the id guess in code.
- **Don't call Bedrock for the Explainer through `dh.llm.ask`:** use `explainer.explain` / `add_to_trace` (rule 5
  exception, #23).
- **App:** show `res["explanation"]["text"]`, its `source` and the G11–G13 checks; never the agent's reasoning (#9).
- **Re-save the demo cache** after any change to data, rules or the Portfolio (the hash changes), before the AWS
  account closes (Monday ~11:30 per the event dashboard).
- `pipeline.py` owner: when ready, call `explainer.add_to_trace(res, profile)` at the end of `run` (one line).

## Open questions / blocked on
1. First real Bedrock run (model access for Opus 5.5 in us-east-1, Strands tool use on Bedrock).
2. Whether to show the agent's `check_text` calls in the app trace (count is already in the step summary).
