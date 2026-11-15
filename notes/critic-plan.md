# Critic: build plan (Sun Nov 15, Will's lane) — BUILT, see decision #30

> **Status:** built on `claude/jolly-gauss-vrakn3`. Will chose: one revision round, which reruns the whole Portfolio
> calculation (section 5 below is superseded by #30: a fix tightens an input, then `portfolio.assemble` reruns);
> Opus 5.5 by default, switchable with `BEDROCK_CRITIC_MODEL_ID`; shown in the trace only (no app panel).
> Still to do: first Bedrock run, then `make explain P=… SAVE=1` for the 3 personas before Mon 11:00.

**Goal:** the sceptic between the Portfolio and the Explainer. A Strands agent on Amazon Bedrock that **investigates
before objecting**: it picks what looks doubtful, calls deterministic tools to check, and returns at most 3
objections, each backed by a tool result it actually obtained. One round. "The LLM argues, code enforces" (#2):
code checks every objection, applies any change, and the Guardian re-checks.

Source of the design: `notes/system-design.md` ("The four agents", 2. Critic), `aws/architecture.md`, decisions
#2, #9, #14, #15. Status today: planned, nothing built (`pipeline.py` docstring says "not built yet").

## 1. Where it sits

```
Portfolio ─► Guardian (G1–G17) ─► CRITIC (agent + tools) ─► [revise once] ─► Guardian ─► Explainer ─► Guardian G11–G13
```

- Runs only on strategies the Guardian passed (✔ or ⚠). Never sees or decides the next step: `pipeline.py` calls it.
- Plugs in the way the Explainer does: `critic.add_to_trace(res, profile)` after `pipeline.run`, before
  `explainer.add_to_trace`. One extra line in `run` once both are stable.

## 2. Inputs → outputs (proposed contract §2c)

**In:** `res["strategies"]` (contract §2, incl. `checks`, `diversification`, `stats`), `limits` (with `reasons`),
`profile`, and the written guide (`notes/critic-guide.md`, section 4).

**Out:** `res["critic"]`:

| Field | Type |
|---|---|
| `objections` | ≤ 3 × {`id`, `strategy` (key), `claim` (≤ 2 sentences), `evidence`: [{`call_id`, `tool`, `args`, `result`}], `action`, `status`} |
| `action` | one of a fixed set (section 5), or `disclose` (no change, shown to the client) |
| `status` | `revised` · `kept, justified: <why>` · `disclosed` · `dropped: <why>` (code decided) |
| `tool_calls` | all calls made, in order (tool, args, short result) |
| `source`, `model`, `note` | `bedrock` · `cache (demo)` · `mock`; like the Explainer (§2b) |
| `facts_hash` | cache key |

## 3. Tools (all deterministic, JSON in/out, errors returned not raised)

Already built (Joud, `market.AGENT_TOOLS`, #15): `list_assets`, `asset_facts`, `portfolio_stats`, `stress_test`,
`correlation_between`, `goal_check`. To add (Will, thin wrappers in `critic.py`, no new maths):

| Tool | Wraps | Answers |
|---|---|---|
| `look_through(weights)` | `metrics.look_through` + `dh.holdings` | "How much NVIDIA is really in there?" |
| `strategy_checks(key)` | the strategy's `checks` (C–F) + Guardian checks | "Which ⚠ is closest to its limit?" |
| `limit_reason(name)` | `limits` + `limits["reasons"]` | "Why is the loss limit 15%?" |

Budget: **6 tool calls** total per run (counter inside each tool; on overflow the tool returns
`{"error": "budget reached: answer now"}`, as the Explainer's `check_text` does).

## 4. The guide (what a sceptic asks): `notes/critic-guide.md`, draft

1. **Same bet twice?** Two holdings with correlation ≥ 0.85 (C6 warns, only ≥ 0.95 blocks).
2. **Hidden concentration?** A company or sector close to its cap once ETFs are looked through (C1, C3).
3. **2022 again?** Stress-window loss within 5 points of the client's loss limit (D3).
4. **Does it fit the goal?** Goal floor vs ceiling conflict, or chance at target < 50% (E).
5. **Does it fit the person?** Home bias for a client working in a sector (C3b), crypto/single names for a
   cautious profile, a request the client made that we only partly met.
6. **Are the 3 strategies really different?** Weights or worst drops nearly identical.

Rules for the agent: object only after a tool confirmed it; at most 3; prefer the objection with the largest
consequence for this client; quote numbers only from tool results; no return forecasts; no "buy/sell".

## 5. Code enforces: what happens to each objection

1. **Backed?** Every number in `claim` must appear in the result of a `call_id` it cites, and that call must be in
   the recorder (same idea as G12). Otherwise → `dropped: unbacked`.
2. **Actionable?** `action` must be one of:
   `merge(a, b)` (keep the larger of two redundant lines), `trim(ticker, to)` (lower a line, excess to the core ETF),
   `shift(pct)` (growth → defensive), `disclose`. Anything that **raises** risk or adds an asset outside
   `limits["allowed_assets"]` is refused → `disclosed`.
3. **Apply once:** `portfolio.revise(strategy, action, limits, rets, holdings)` (deterministic: reuse `build`,
   `round_weights`, `fix_diversification` pieces), recompute `stats`, `checks`, `diversification`.
4. **Guardian re-check:** if the revised strategy fails, or its worst drop breaks the loss limit, keep the original
   → `kept, justified: <rule + number>`. Max one revision per strategy, no second Critic round.
5. **Surviving `disclose` objections** go to the Explainer facts (new `critic` key) and to the strategy's `cons`.

## 6. Modes (same pattern as the Explainer, #23)

- `bedrock`: demo cache → local cache → Strands agent. Model: `BEDROCK_CRITIC_MODEL_ID`, else the Explainer's
  default (Opus 5.5, already verified on the account).
- `mock` (tests, offline demo): deterministic critic that turns the top ⚠ checks into ≤ 3 objections with real tool
  calls. The demo works without AWS and the tests are stable.
- Demo cache `cache/critic/<hash>.json`, committed; `make critic P=amira SAVE=1`. **Re-save the Explainer cache
  after**: its facts now include the Critic's output, so its hash changes.

## 7. Trace (what the jury sees, #9)

```
Critic → Portfolio: called correlation_between(QQQ, SPY) → 0.91; look_through → NVDA 13.2% vs cap 15%.
  Objection 1 (Growth tilt): QQQ and SPY are largely the same bet (0.91). Action: merge(SPY, QQQ).
Portfolio → Guardian: 'Growth tilt' revised (merge SPY into QQQ): worst drop −31.0% vs limit 40%.
Guardian → Explainer: 'Growth tilt' 17 ✔ 2 ⚠ 0 ✘.
```

Tool calls, numbers, verdicts; never the model's reasoning.

## 8. Steps (estimates; deadline repo Sun 23:59, AWS closes Mon ~11:30)

| # | Step | Est. | Cut line |
|---|---|---|---|
| 1 | `notes/critic-guide.md` from section 4; decision #30 | 20 min | must |
| 2 | `critic.py`: tool wrappers + recorder + budget; mock critic | 1 h | must |
| 3 | Validator (backed / allowed action / ≤ 3) + `res["critic"]` + trace lines | 45 min | must |
| 4 | Strands agent on Bedrock + caches + `make critic` | 45 min | must (qualifying: real AWS work) |
| 5 | Explainer facts get `critic`; `cons` filled | 30 min | must |
| 6 | Offline tests (below) | 45 min | must |
| 7 | `portfolio.revise` + Guardian re-check (one round) | 1 h 30 | **MVP stops before this: all objections `disclose`** |
| 8 | Pipeline wiring, app panel "What the Critic checked", save demo caches for 3 personas | 1 h | must before Mon 11:00 |

MVP = steps 1–6 + 8 (~5 h): the Critic investigates and discloses, nothing changes the weights. Full = + step 7.

## 9. Tests (offline, fake agent)

- An objection quoting a number no tool returned → dropped.
- 5 objections returned → 3 kept; 7th tool call → budget error.
- An action that adds a non-allowed asset or raises growth → refused, disclosed.
- (Full) a revision that breaks the loss limit → original kept, `kept, justified`.
- Mock mode on Amira / Mateo / Robert: deterministic objections, Guardian still passes, `make scenarios` 16/16.
- Agent exception → `source: mock`, note says why, pipeline continues.

## 10. Open questions for Will

1. MVP (disclose only) or full (one revision round)? Recommend MVP first, revision only if time is left Sunday.
2. Opus 5.5 for the Critic too, or a cheaper/faster model (6 tool calls ≈ latency in the live demo)?
3. OK to show the Critic panel in the app, or only in the trace?
