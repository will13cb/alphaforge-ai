# CLAUDE.md — PolyFinances Datathon 2026 (Polytechnique Montréal)

> Agents: read this, then CONTEXT.md, before doing anything. Humans: fill the TODOs at kickoff (10 min).

## The challenge (fill at kickoff)
- **Problem statement:** AlphaForge AI (Banque Nationale x AWS). Design a self-explaining **agentic** solution that uses public financial data to inform investment analysis/decisions for different investor profiles. Simulation only: no real transactions, no personalized advice. Source: `Datathon2026Infos/Datathon - Case Officiel 2026 ENG.pdf`. NOT a prediction task: no train/val split, no leaderboard metric.
- **Personas (reference scenarios):** Amira (26, high risk, 15y+, AI/crypto, still wants diversification), Mateo (41, moderate, 8-12y, ESG + avoid controversies), Robert (59, low-moderate, 3-5y, preserve capital; tempted by hyped names, system must challenge him).
- **Data:** optional starter pack in `Datathon2026Infos/alphaforge_starter/` (31 assets, daily prices 2021-11-12 to 2026-11-12, FX, macro; no ESG/news/fundamentals). `make data` puts the CSVs in `data/raw/` (gitignored). Any extra public data must be documented (source, date, processing, limits, licence).
- **Deadlines (verified, see CONTEXT.md):**
  - **Sun Nov 15 23:59 (Devpost): public deployed app link + GitHub repo link (install guide in README) + team number. NO CHANGE AFTER 23:59 (disqualification)**
  - **Mon Nov 16 13:59: AWS account closes** (organizers' reminder). Commit caches and results BEFORE Sun 23:59: no `make backup` after the freeze
  - Mon 14:00, email logiciel@polyfinances.ca ("Datathon - Équipe XX"): video (≤ 5 min, Google Drive link) + technical doc PDF + one-pager PDF
  - Finalist pitches: Fri Nov 20, 14:00
- **Judging criteria (brief p.17):** relevance of the problem, strength of approach, creativity, execution quality, usefulness to users, relevance of the agentic approach, ability to explain its own results (data, assumptions, limitations). Faithful explanations > complexity or historical returns. Confirm any weights at the presentation.
- **Deliverables (brief p.15-16):** prototype + repo/README; ~5 min demo video (ideally two contrasting personas); technical doc (agent roles/controls, methods, sources/assumptions, explainability example, validation/limits); one-pager (max 1 page).
- **Challenge owner / sponsors:** National Bank × AWS × PolyFinances (slides). Other event partners: La Caisse, Desjardins, CGI, Valnet, BeeQuest, Mag Energy, Finance Montréal, CFA Montréal.
- **Our angle, one sentence:** A team of specialised agents profiles the investor the way a Canadian advisor would, proposes up to three simulated strategies inside limits it can explain, and lets code (not the LLM) enforce those limits, so it can tell Robert "no" to 25% in Tesla and show exactly which rule, number and source made it say so.
- **AWS services (QUALIFYING requirement, slide 7: no real integration = not eligible):** Amazon Bedrock (models for the Strands agents), Strands Agents SDK (extractor, Critic, Explainer, analyst), Amazon S3 (input profiles, data, run traces), Bedrock AgentCore Runtime (hosts the pipeline, if ready by Sun midday). Decision #14. Name them in every deliverable.

## Team & lanes
Team: William Caron-Bastarache, Joud Katbe. Will owns everything except deterministic market data, which Joud owns.

| Lane | Who | Owns (only edit these) |
|---|---|---|
| market data (deterministic) | Joud | `src/dh/data.py`, market-data agent (`src/dh/agents/market.py`), `experiments/data/`, starter-data docs |
| agents | Will | `src/dh/agents/` (analysis, governance, explanation), `src/dh/llm.py`, `experiments/agents/` |
| app / aws | Will | `app/`, `aws/`, the architecture diagram |
| pitch | Will | `deliverables/`, `notes/` |
| shared (ask first) | anyone, announce in chat | `harness.toml`, `src/dh/metrics.py`, `src/dh/personas.py`, `notes/contract.md`, this file |

Where things go: official brief + our slides in `Datathon2026Infos/`, ideas/notes in `notes/`, final submissions in `deliverables/`.

## How we work
1. **One data path.** Load prices/returns only via `dh.data` (adj_close, base currency and calendar from `harness.toml`), and compute stats only via `dh.metrics`, so every agent quotes the same numbers.
2. **Every evaluation goes in `results.csv`** through `dh.log_run(value, experiment, metric, persona=...)` (e.g. governance pass rate on persona scenarios, a simulated allocation's max drawdown). Commit code first. `make board` shows the latest values.
3. **No number goes in the pitch unless it's in results.csv or under "Verified" in CONTEXT.md.**
4. **Data never goes in git** (`data/` is gitignored). The starter-pack CSVs are shared by hand, not through git (decision #11). Notebooks are for exploring. Anything others depend on goes in `src/dh/` as a `.py` file.
5. **LLM calls only through `dh.llm.ask`** (mock offline, Bedrock for real, cached).
6. **Small commits, merge often.** Pull main every ~2h. On conflict in a shared file, ask its lane.
7. **Never commit or read secrets.** Don't `cat`/`grep`/`source` `.env` or AWS credentials, or dump `env`. Use `make <target>`, which loads `.env` for that command. The guard hook blocks the common cases, plus cloud deletes and force-push.
8. **The app is a deliverable (Sun 23:59).** Get `make app` showing real output by Saturday night, then keep it working.
9. **Before Monday 11:00:** `make backup` (pulls S3 traces, commits the demo cache). The AWS account closes ~11:30 (event dashboard), not 13:59.
10. **Ask, don't guess.** If an official source (event site, rules, sponsor brief, data docs) can't be reached, or key facts are missing, stop and ask the user before building on search results or assumptions. Ask for the document, or for network access to the host.
11. **One design doc per branch:** `notes/branches/<branch-name>.md` (`/` → `-`), from the template in
    `notes/branches/README.md`. Create it with the branch, update it before each merge (Done, Next, Decisions,
    Contract changes, How to check). Agents: read the doc of the branch you're on before starting, and update it
    at the end of your work. Decisions still go in `notes/decisions.md` + the decisions log; the branch doc links to them.

## Commands
| | |
|---|---|
| `make setup` | venv + deps + .env |
| `make data` | starter CSVs into data/raw (copy, S3, or rebuild via Yahoo/BoC/FRED) |
| `make check` | load data, print per-asset return/vol/Sharpe/drawdown |
| `make board` | latest results per experiment/persona |
| `make scenarios` | test profiles vs Profiler + Guardian, prints each agent hand-off (`LOG=1` logs the pass rate) |
| `make app` | run the demo app (Streamlit) |
| `make test` | tests |
| `make worktrees` | one worktree per lane, for parallel agents |
| `make backup` | commit+push results/deliverables before AWS teardown |

```python
from dh import returns, summary, log_run, PERSONAS
from dh.metrics import portfolio_returns, max_drawdown
from dh.personas import describe
from dh.llm import ask
r = returns(["XIU.TO", "SPY", "XBB.TO", "GLD"])          # daily, base currency
port = portfolio_returns(r, {"XIU.TO": .3, "SPY": .3, "XBB.TO": .3, "GLD": .1})
log_run(max_drawdown(port), experiment="robert-balanced", metric="max_drawdown", persona="robert")
ask(f"{describe('robert')}

Explain this allocation's risk: ...", system="...")
```

## Decisions log (one line each: time — decision — why)
- Sat — Architecture from Will's sketch: input → profiler → market data (deterministic) → portfolio → critic → explainer; Guardian watches the whole pipeline; all agents write traces — see `aws/architecture.md`
- Sat — Portfolio proposes at most 3 strategies at different risk levels, with pros and cons each — clear comparison for the client
- Sat — Finance-knowledge score changes the proposal — a beginner asking for 100% TSLA gets a "no" and the reasons. **Revised:** scored by rules (declared level, experience, quiz cap), LLM only extracts answers — same answers, same limits (`notes/decisions.md` #4)
- Sat — ~~Guardian checks compliance with Canadian laws~~ **Revised:** Guardian = deterministic rules G1–G13 "modelled on NI 31-103 KYC/suitability", never "compliant"; Critic = LLM judgment — "the LLM argues, code enforces"; testable (#2, #3)
- Sat — Profiler outputs `profile` (facts) and `limits` (conclusions) separately; Portfolio reads only `limits` — see `notes/contract.md`; lanes work in parallel on fake data
- Sat — Strategies from risk-level templates; efficient frontier is a chart, not the optimiser — 5y incl. 2022 makes optimised weights unstable (#1). **Revised (#17):** strategies defined by what they hold; split computed, no optimiser still
- Sat — Risk levels 1–5, thresholds in `src/dh/agents/rules.py`; level = min(tolerance, capacity) — team assumptions, to validate on 2022 data (#5). **Revised (#17):** levels = label + diversification caps + Guardian safety net; split and loss limit come from the client
- Sat — Single-company cap counts ETF look-through (`dh.metrics.look_through`) — 3 ETFs can be one bet (#6)
- Sat — 16 test profiles with expected verdicts in `src/dh/agents/scenarios.py`; every hand-off described in the trace — validation deliverable
- Sat — Lanes: Will owns everything except deterministic market data (Joud); `metrics.py` + contract shared — Joud already building it (`notes/decisions.md` #8)
- Sat — ETF holdings from issuer files only (`src/dh/holdings.py`, `scripts/build_holdings.py`); Guardian G4/G10 use them by default, tests use illustrative ones — SPY loaded, QQQ/ESGV/XIU by hand (`data/README.md`, `notes/decisions.md` #6)
- Sat — Trace shows steps/numbers/verdicts, not raw model reasoning; no return predictions; AWS must do real work (qualifying, slide 7) — brief p.17 + slides (`notes/decisions.md` #9)
- Sat — **Revised:** starter CSVs shared by hand (folder sent to Joud), not in git; briefly committed in `a24478b`, so the submission = fresh repo without this history — Yahoo redistribution terms (`notes/decisions.md` #11)
- Sat — Annualise with observed rows/year (~261 on weekday calendar), 252 only as fallback — fixed 252 understated CAGR ~3% relative (`notes/decisions.md` #12)
- Sat — Risk thresholds checked on 2021-2026: G7 holds 90% (L1 8% too tight with equal-weight defensive basket → proposal to Will); goal outlook shows `risk_only` (cash drift) before `replay` — no historical return as forecast (`notes/decisions.md` #13)
- Sat — Strands agents (extractor, Critic, Explainer, analyst) on Bedrock for the steps that decide; `pipeline.py` orchestrates (Guardian always runs); S3 for traces; AgentCore Runtime hosts if ready — real agency + AWS in the flow, without losing "code enforces" (`notes/decisions.md` #14)
- Sat — Market data stays deterministic (no LLM); its functions are exposed as tools to the Strands agents (`market.AGENT_TOOLS`): JSON in/out, errors returned not raised, unknown tickers (e.g. XSP) refused; one universe-wide calendar so every agent gets the same numbers (`notes/decisions.md` #15)
- Sat — Market-data charts (`market_charts.py`): `*_data()` + Altair `*_chart()`, same numbers as the trace; PNG/HTML export for the video, figures gitignored (`notes/decisions.md` #16)
- Sat — Stocks/bonds split computed per strategy between the client's goal floor and risk ceiling (largest growth share whose 2021-2026 worst drop ≤ the client's own loss limit), liquidity floor hard, conflict shown — no made-up level→split table; data decides (`notes/decisions.md` #17)
- Sat — Diversification measured on 5 dimensions (classes, companies and sectors through ETFs, currency, correlation), rules C3 sector ≤ 40% / C6 no pair ≥ 0.95 / C4 ≥ 2 classes; reuses look-through; lower bound shown when holdings missing (`notes/decisions.md` #18)
- Sat — Loss limit = min(tolerance, capacity level's drawdown), defensive floor = max(withdrawals within 3 years, 5%), goal floor = ≥ 50% chance (risk-only); Portfolio builds core/income/growth strategies at their computed ceiling — #17 made concrete, tested offline (`notes/decisions.md` #19)
- Sat — Portfolio checks C-F (`checks.py`): 17 checks, one shape {check, value, limit, status, reason, source}; ✘ blocks (company, sector > 40%, job sector > 15%, drawdown $, horizon, liquidity, beginner, exclusions), ⚠ discloses (country > 70%, sector > 30%, < 8 effective holdings, correlation > 0.85, tolerance close); Guardian G14–G17 call them (`notes/decisions.md` #20)
- Sat — CPPI tested then **set aside**: we stick to what the judges ask (decision-support, simulation only, "sophistication is not an end"); a dynamic rebalancing rule implies ongoing management (`notes/decisions.md` #21)
- Sat — Horizon directive (`rules.horizon_max_growth`): growth cap linear in the client's horizon, 0% up to 2 y → 100% from 15 y (3 y → 8%, 4 y → 15%, 10 y → 62%); defensive floor = strictest of withdrawals, horizon, 5% safety net — data-only ceiling gave Robert 80% stocks (`notes/decisions.md` #22)
- Sat — Explainer = Strands agent on Bedrock (Opus 5.5) writing only from pre-formatted facts, self-checks with G11–G13 via a tool, template fallback if it fails, committed demo cache for offline replay; rule 5 exception for Strands (`notes/decisions.md` #23)
- Sat — Caps on one company / crypto computed per client and per asset: ¼ of the loss limit at its own worst 2021–2026 drop, ≤ ⅕ of the stock room; no per-level table; requests explained with numbers, never "refused" (`notes/decisions.md` #24)
- Sun — Every run's trace saved as JSON to s3://$S3_BUCKET/traces/ (`dh.tracestore`), local fallback outputs/traces/ if AWS fails; `make backup` pulls them into git — AWS holds the evidence (slide 7) (`notes/decisions.md` #25)
- Sun — AWS closing time: plan for Mon ~11:30 (event dashboard: 72 h from Fri 11:30), not the schedule's 13:59 → `make backup` before 11:00 — use the earlier of two sources (CONTEXT.md)
- Sun — Crypto only if the client asks (interest or requested position) AND the profile allows it (cap > 0) AND the model suggests it (growth ceiling not lower with it); otherwise left out, reason in the trace — no crypto by default (`notes/decisions.md` #26)
- Sun — Strict G12: Explainer writes ids ({nK}) for every number (%, $, ages, years, dates) that code fills in; any digit or spelled-out amount it types is rejected; final text must match the facts exactly; general G12 tolerance 0.5 → 0.05 — ±0.5 let 23–36% of invented numbers through (`notes/decisions.md` #27)
- Sat — Request side by side (`requests.py`): "as asked" vs "fits your limits", same C-F checks + Guardian, drop in % and $; selection drops any ✘ (Guardian or C-F); pros/cons from stats/checks only, G12 knows them — Robert 25% TSLA: 106k $ drop vs 60k $ limit, 9 ✘; at 3.1%: 38k $, all ✔ (`notes/decisions.md` #28)
- Sun — Free-text extractor = Strands agent on Bedrock (Opus 5.5) filling `profile` only; code checks schema and keeps a number only if the client wrote it; missing essentials → fixed follow-up questions; offline cache + rule parser fallback (`notes/decisions.md` #29)
- Sun — Critic = Strands agent (Opus 5.5, switchable by env): 9 deterministic tools, ≤ 6 calls, ≤ 3 objections each backed by a tool result it obtained; a fix only tightens an input (merge / trim / shift) and reruns the whole Portfolio calculation, Guardian re-checks, original kept if it fails; one round; trace only — agency without the LLM setting a number (`notes/decisions.md` #30)
- Sun — Analyst (`analyst.py`): Strands agent for follow-ups; tools = market tools + what-ifs that re-run the real pipeline (position, profile field); every number backed by a cited tool result, no advice/forecast, disclaimer by code, only valid answers cached; `python -m dh ask` (`notes/decisions.md` #35)
- Sun — Longer history (optional, `make data-long`, official script from 2004 + FRED USD/CAD before BoC); missing history is NaN, never 0%; stand-ins only before first price (ZST ← overnight rate, ESGV ← SPY); 2008/2020 stress when covered; windows in texts from the data — audit: one 5-year window (`notes/decisions.md` #31)
- Sun — Up to 3 strategies = 3 risk levels: most growth the limits allow, −10 and −20 points (full recalculation each); preferred flavour first; < 5 points apart dropped — audit S3, promise = behaviour (`notes/decisions.md` #32)
- Sun — Every split states what set it (horizon rule, withdrawals, safety net, level, or the worst-drop test) and what the worst-drop test alone would allow; deliverables no longer say "the data decides" — audit S2(a) (`notes/decisions.md` #33)
- Sun — Audit technical fixes: G12 catches losses written as gains; Sharpe vs cash; one implementation per rule (C3/C4, lists, tolerances); C1 per company; persona card = pipeline numbers; no noise pros; crypto pairs weekly in C6; stale results listed — CNQ factor left until verified (`notes/decisions.md` #34)
- Sun — Guided interface (`interface/`, `make ui`): step-by-step questions checked with the engine's own limits, one service layer as error boundary, results essentials-first, Analyst as a conversation (history; offline: context, glossary, results overview, labelled "limited answers") — usefulness to users without faking AI; branch `interface`, merge after Will's OK (`notes/decisions.md` #36)
- Sun — Mean-variance optimisers (Joud, branches `interface`, `optimisation-markowitz`) tested, kept off the demo: unstable across windows, worse than equal weight out of sample; #1 stands (`notes/decisions.md` #37)
- Sun — From Markowitz keep only what describes risk: risk contributions (covariance only) as a Critic tool; Joud's KYC bets → A as a Profiler cross-check (flag to clarify, no limit change) + an expected-value question that caps knowledge at 3 if wrong — explains without forecasting; KYC conflicts → clarify (`notes/decisions.md` #40)
- Sun — Research mode (`harness.toml [data] extra = ["cadusa"]`, off by default): 60 CAD/USD products; baskets driven by the profile or C2 (ESG → XESG.TO, horizon ≤ 5 y → XSB.TO, one country > 70% → XEF/XEC); dividend coverage on 3 years (`dh.fundamentals`), income names ≤ 80% payout (ENB.TO out), F7 ⚠ — demo unchanged (`notes/decisions.md` #41)
- Sun — Existing portfolio (`portefeuille_existant`): holdings entered one by one, reviewed with C-F + Guardian, rebuilt into the first strategy; funds without data measured with a labelled stand-in (XSP.TO = SPY, CAD hedge simulated, checked vs real prices: −24.3% vs −27.5%) or left out; Critic/Explainer/Analyst read it — BN workshop slides 13-14 (`notes/decisions.md` #42)
- Sun — Existing portfolio follow-ups: fund fees in $/year (Yahoo net expense ratio, held fund's own), free text reads holdings owned, "10% in XSP" measured via its stand-in, look-through status shown + SPY holdings built on the host, `make warm` covers Robert + example portfolio (`notes/decisions.md` #44)
