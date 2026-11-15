# AlphaForge AI: an investment analyst that can say no

PolyFinances Datathon 2026 (Polytechnique Montréal), challenge **AlphaForge AI** by **National Bank × AWS**.
Team: William Caron-Bastarache, Joud Katbe. *Version française : [`README.md`](README.md).*

> A team of specialised agents profiles the investor the way a Canadian advisor would, proposes up to three
> simulated strategies inside limits it can explain, and lets code (not the LLM) enforce those limits, so it can
> tell Robert "no" to 25% in Tesla and show exactly which rule, number and source made it say so.

**Live app:** https://alphaforge-ai-wj.streamlit.app/ · **Simulation only.** Fictional profiles, no real transactions, not financial advice.

## What it does

A client's profile goes in. The pipeline works out their limits (each with a written reason), builds up to three
strategies at different risk levels, sets each stocks/bonds split as the strictest of the client's constraints (a
stated horizon rule, money needed soon, a simulated chance of exceeding their loss threshold over their horizon) and says which one decided,
checks everything against explicit rules, and explains the result in plain language, tying
every number to the data.

Example: Robert (59, about 4 years before he needs the money, accepts at most a 15% loss) asks for 25% in Tesla.
- His horizon rule (a stated judgment, not a data result) allows at most about 15% in stocks: his first strategy is
  about 15/85 and the second holds 10 points less in stocks; the trace says the horizon rule decided.
- Caps are computed, not fixed: Tesla's own worst drop was −70.9%, so 25% alone would have cost −17.7% of the
  portfolio, more than his whole 15% loss limit; it fits up to 3.1%.
- The explanation (Claude Opus 5.5 on Amazon Bedrock) gives him those numbers and leaves the decision to him;
  the Guardian checks that every % in it was computed and that the request is explained.

## How it works

| Step | Agent | How | Output | Status |
|---|---|---|---|---|
| 1 | Profiler | rules | tolerance, capacity, knowledge, loss limit (also in $), defensive floor (horizon, withdrawals), per-company and crypto caps, each with a reason | built |
| 2 | Market data | deterministic | per-asset return, volatility, worst drop, CVaR, 2022, correlations, goal outlook | built |
| 3 | Portfolio | rules + data | up to 3 strategies at different risk levels (#32); split = strictest of horizon rule, withdrawals and the simulated loss test, with the one that decided (#33); diversification checks C–F | built |
| 5 | Explainer | Strands agent, Claude Opus 5.5 on Bedrock | client text from pre-formatted facts; checks its own draft with the Guardian's rules (tool) | built |
| all | Guardian | rules including G7 (simulated loss) and G18 (consistency) | ✔ / ⚠ / ✘ at each step; ✘ on the profile → ask; on a strategy → dropped; on a Critic fix → original kept; on the text → template | built |
| all | Trace store | Amazon S3 | every run as JSON in `s3://$S3_BUCKET/traces/` (local fallback) | built |
| 0 | Free-text extractor | Strands agent, tool `check_profile` | `profile` fields from a description; every number must be in the client's text; missing essentials asked (#29) | built, Bedrock answers cached |
| 4 | Critic | Strands agent with tools | investigates (11 tools incl. risk contributions, ≤ 6 calls), ≤ 3 backed objections, one recomputed fix per strategy, Guardian re-check (#30, #40) | built, Bedrock answers cached |
| app | Analyst | Strands agent with tools | follow-up questions (English or French): what-ifs re-run the pipeline, every number in the answer checked by code | built, in the app (Follow-up tab), Bedrock answers cached |

**Agents investigate and argue, code enforces.** Strands agents on Amazon Bedrock decide what to write or check;
`pipeline.py` fixes the order so the Guardian always runs; every run's evidence goes to Amazon S3. Limits move with
the client and the data (horizon, loss limit, each asset's own worst drop), not with a fixed table. The Guardian's
suitability checks are *modelled on* Canadian KYC / suitability duties (NI 31-103 s.13.2–13.3); they are not a
legal compliance test. Every hand-off between agents is written to a
trace (steps, numbers, verdicts, never the model's raw reasoning).

- Graph of the orchestration: [`aws/architecture.en.md`](aws/architecture.en.md) (image: [`aws/architecture.en.png`](aws/architecture.en.png)); deliverables in English: `deliverables/*.en.md`
- Design and agents: [`notes/system-design.md`](notes/system-design.md)
- What each agent hands to the next: [`notes/contract.md`](notes/contract.md)
- Every decision and why: [`notes/decisions.md`](notes/decisions.md)

### Status

| Built | In progress |
|---|---|
| Profiler, market data, Portfolio (computed split, per-company caps, checks C–F, request side by side), Guardian loss and consistency controls, Strands agents on Bedrock (Opus 5.5): free-text extractor, Critic, Explainer (demo texts cached for offline replay), Analyst (app follow-ups), review of a portfolio the client already holds (labelled stand-ins, fees, rebuild in $), fixed-income lookup for a bond-only preference (sourced government bonds held to maturity), guided interface (optional voice: Amazon Transcribe + Polly; KYC bets and expected-value question as a cross-check, #40), S3 trace store, demo app, `propose` / `explain` / `extract` / `ask` CLI, offline tests, 16 test profiles | Re-save the Bedrock demo caches on the final data (`make warm`); AgentCore hosting not deployed; ETF holdings for QQQ / ESGV / XIU (SPY loaded) |

Per-branch details: [`notes/branches/`](notes/branches/).

## Quick start

Requires Python 3.12+ and internet access (to build the data).

```bash
make setup        # venv + dependencies + .env (fill it in)
make data         # starter CSVs into data/raw/
make check        # per-asset return / volatility / Sharpe / drawdown
make scenarios    # 16 test profiles through Profiler + Guardian, every hand-off printed
make explain P=robert   # full pipeline + Explainer on a persona (amira, mateo, robert); trace saved to S3
make test         # offline tests
make extract T="I'm 59, ..."   # free text → profile + follow-up questions
make bedrock-check  # AWS smoke test: region, credentials, Bedrock text + tool use, S3 (needs .env)
make app          # the demo (jury view) on http://localhost:8501: limits, strategies, explanation, Analyst, trace
make ui           # guided interface (client view) on http://localhost:8502: same engine, step-by-step questions
make warm         # with Bedrock: fill every demo cache in one run (DRY=1 lists the calls)
```

**Both views include a Light / Dark appearance switch and live analysis hand-offs.** Clients can inspect their
completed run in Activity; judges can inspect Activity & evidence, including checks, sources, explanation origin,
and the actual S3/local storage outcome. Activity also lists and searches the currently enabled product universe.

**Risk model (release integration).** The growth ceiling uses a stationary block bootstrap over the client's horizon, with a stated 3% annual premium on growth assets above cash and a 10% model exceedance threshold. A fresh simulation checks the final weights. These are scenario assumptions, not a calibrated guarantee of future losses. G17 is folded into G7; G18 checks result consistency; research-mode dividend warnings use G19. See `notes/risk-architecture.md`.

**Two front ends, one engine.** `make app` is the demo: it shows everything the agents did (limits with reasons,
strategies and what set each split, Guardian checks, the Explainer's text, follow-ups, the full trace) and saves
each run's trace to Amazon S3. `make ui` is what a client would use: questions one at a time, results
essentials-first, the Analyst as a conversation. Both call the same `pipeline.run`; neither computes a number.

Windows without `make`:

```bash
python -m venv .venv && .venv\Scripts\python -m pip install -e ".[dev,agents]"
copy Datathon2026Infos\alphaforge_starter\build_dataset.py data\raw\ && .venv\Scripts\python data\raw\build_dataset.py
.venv\Scripts\python -m dh check
.venv\Scripts\python -m dh scenarios -v
.venv\Scripts\python -m dh explain robert
set LLM_PROVIDER=mock && .venv\Scripts\python -m pytest -q
.venv\Scripts\python -m streamlit run app/app.py
```

### Configuration (`.env`, never committed)

| Variable | Use |
|---|---|
| `LLM_PROVIDER` | `mock` (offline, default) or `bedrock` |
| `BEDROCK_MODEL_ID` | Bedrock model for the LLM agents (verified on the event account: `global.anthropic.claude-opus-5-5`) |
| `BEDROCK_EXPLAINER_MODEL_ID` | optional override for the Explainer (default `global.anthropic.claude-opus-5-5`) |
| `AWS_REGION` | e.g. `us-east-1` |
| `S3_BUCKET` | bucket for run traces (`traces/`) and data (`raw/`, `make data` can sync from it) |

AWS credentials come from your AWS profile (`aws configure`), not from this repo. LLM calls go through
`dh.llm.ask` (cached in `.cache/llm/`), except the Strands Explainer, which caches its own answers; the three
personas' Opus texts are committed in `cache/explainer/`, matching facts replay without AWS; otherwise offline mode uses an explicitly labelled deterministic fallback. Run `make warm` on the final code and dataset before recording.

## Deploy (Streamlit Community Cloud)

The data never goes in git (decision #11). A hosted copy gets it at first start: from the team's S3 bucket, else by
rebuilding it with the organizers' script (`src/dh/bootstrap.py`).

1. Once, from a laptop with the data and `.env`: `make data-up` (uploads `data/raw/*.csv` to `s3://$S3_BUCKET/raw/`).
2. On https://share.streamlit.io: **New app** → this repo, branch `main`, file `interface/app.py` (guided
   interface) or `app/app.py` (demo view); **Advanced settings** → Python 3.12. Deploy each app separately if both.
3. **Secrets** (same box for each app; never in git):
   ```toml
   AF_AUTO_DATA = "1"
   S3_BUCKET = "…"
   AWS_REGION = "us-east-1"
   AWS_ACCESS_KEY_ID = "…"
   AWS_SECRET_ACCESS_KEY = "…"
   AWS_SESSION_TOKEN = "…"
   LLM_PROVIDER = "bedrock"
   AF_LANG = "fr"           # interface language at start: "fr" (default) or "en"; a sidebar switch changes it
   AF_VOICE_ENABLED = "0"   # "1" turns on voice in the guided interface (Amazon Transcribe + Polly, audio via S3 voice/)
   ```
   After the event account closes, set `LLM_PROVIDER = "mock"` and remove the AWS keys: the app rebuilds the data
   itself and replays the cached Claude answers (offline mode, said on screen).

## Data

| Source | What | Where |
|---|---|---|
| Starter pack (organizers) | 31 assets, daily prices 2021-11-12 → 2026-11-12, dividends/splits, USD/CAD, rates, CPI | Yahoo Finance, Bank of Canada, FRED; rebuilt by `Datathon2026Infos/alphaforge_starter/build_dataset.py` |
| ETF holdings | what SPY, QQQ, ESGV and XIU actually hold, for look-through | issuer files (State Street, Invesco, Vanguard, iShares); `scripts/build_holdings.py`. SPY loaded (as of 2026-11-12); the others still to download |

Prices in each asset's currency, converted to CAD (`harness.toml`); returns from adjusted close. Known limits:
survivorship bias in the universe, monthly macro data dated by reference month (lagged before use), holdings are a
snapshot used for exposure only. Historical numbers describe the past; they are not predictions.
Sources, dates, processing and terms: [`data/README.md`](data/README.md). Data files are never committed.

## Validation

`make scenarios` runs 16 fictional profiles (the brief's three personas plus trap cases: a beginner asking for
100% Bitcoin, a short horizon with high risk appetite, no emergency fund, an invented number in the explanation…)
against their expected verdicts, and `make scenarios LOG=1` logs the pass rate to [`results.csv`](results.csv).
It tests the rules, not real portfolios ([decision #7](notes/decisions.md)). `make test` runs the regression suite (release verification: 375 passed, 1 skipped with rebuilt starter data)
(synthetic data, faked AWS), including the Portfolio's split search, the Explainer's fallback when its text
breaks a rule, and each agent's controls (an unbacked number dropped, a Critic fix that breaks a limit reverted).

## Repository layout

```
src/dh/            data.py (loaders, FX, calendar) · metrics.py (risk stats, look-through, results log)
                   quant_toolkit.py (risk, stress, bootstrap) · holdings.py (ETF holdings) · tracestore.py (S3 traces)
                   llm.py (mock | Bedrock, cached) · personas.py
src/dh/agents/     profiler.py · market.py · market_charts.py · portfolio.py · diversification.py · checks.py
                   guardian.py · explainer.py · pipeline.py · trace.py · rules.py · scenarios.py
app/app.py         demo app (Streamlit)
aws/               architecture graph
cache/explainer/   committed Opus texts for the three personas (offline demo)
outputs/traces/    run traces pulled from S3 by `make backup`
scripts/           get-data, build_holdings, bedrock_check, backup, scan-secrets, worktrees
notes/             design, contract, decisions, branch docs, intake form, kickoff notes
deliverables/      one-pager, technical doc, video script
Datathon2026Infos/ official brief, slides, starter-pack script
tests/             offline tests
```

## Working on this repo

Team rules (lanes, one data path, results log, branch design docs, secrets): [`CLAUDE.md`](CLAUDE.md).
Facts, verified vs assumed: [`CONTEXT.md`](CONTEXT.md). Coding agents: read both before doing anything.

A guard hook (`.claude/hooks/guard_bash.py`) stops coding agents from reading secrets, force-pushing or deleting cloud
resources. It's a speed bump, not a security boundary. Run `make scan` before making the repo public, and
`make backup` before the Sunday 23:59 freeze (nothing can be pushed after it; the AWS account closes Monday 13:59).

## License

MIT, see [`LICENSE`](LICENSE).
