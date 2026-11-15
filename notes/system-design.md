# System design (DRAFT, direction not decided yet)

Status: proposal to discuss. Nothing here is built. Decisions go in the `CLAUDE.md` decisions log once agreed.

## The idea in one paragraph

A multi-agent system. First it figures out **who the investor is** (free text, or answering questions in the GUI).
That profile starts an agentic pipeline. **Each specialised sub-agent outputs a feature set** (constraints, signals,
objections, compliance flags) that **modifies the strategy** for this specific profile. The output is a fictional
allocation with an explanation that traces every conclusion back to data, assumptions and limits.
Same pipeline for everyone, so the contrast between personas shows adaptability.

## Why this shape fits the judging (weights from the challenge presentation, see CONTEXT.md)

| Criterion | Weight | How this design answers it |
|---|---|---|
| Solution | 20% | Profile → constraints → strategy → checks → explanation, end to end |
| Agentic | 20% | Specialised agents with clear roles, a bounded debate, a governance loop |
| Data | 20% | Public data only, every source cited, traceable numbers (`dh.data`, `dh.metrics`) |
| UX/UI | 10% | Simple intake (text or guided questions), readable result |
| AWS | 15% | Bedrock for the agents, plus S3/others (to decide) |
| Pitch | 15% | Two contrasting personas, same question, different justified answers |

## Pipeline (Will's sketch, Sat 14:25)

Graph view: `aws/architecture.md` (Mermaid, renders on GitHub).

```
0. INPUT ──────────── free text → extractor   OR   guided questions  →  stored in S3
          │
          ▼
1. PROFILER ───────── risk tolerance, risk capacity, finance-knowledge score (judged by the LLM),
          │            objective(s), horizon, liquidity, constraints, preferences
          ▼
2. MARKET DATA ────── DETERMINISTIC: ingestion, cleaning, features → asset summary
          │            (return, volatility, drawdown, correlation, 2022 behaviour, macro)
          ▼
3. PORTFOLIO ──────── up to 3 strategies for this client (fewer if enough), each with a different risk
          │            level inside the client's preferences; diversification types (see workshop slides),
          │            efficient frontier, Monte Carlo, risk of ruin; pros/cons per strategy
          ▼
4. CRITIC ─────────── judges the strategies against a short written guide (Will writes it);
          │            debate but not too much: one round, Portfolio revises once or justifies
          ▼
5. EXPLAINER ──────── text for the client, then visuals in the app

GUARDIAN (code, rules G1–G13) ─ runs after the Profiler, the Portfolio and the Explainer; checks limits,
          exclusions, look-through, traced numbers, disclaimer; any ✘ sends the step back.

TRACE STORE (every agent writes to it) ─ profile info, decisions, verdicts; the Guardian adds its checks.
```

## Agents

**Profiler**
- Risk **tolerance** (what they accept): concrete scenarios ("your portfolio drops 20%, what do you do?"), max loss.
- Risk **capacity** (what they can afford): computed from horizon, income stability, emergency fund, dependents,
  planned withdrawals. Not asked directly.
- **Finance-knowledge score**, computed by rules from the answers (declared level, years of experience, quiz cap;
  the LLM only extracts the answers from free text). It changes the proposal: a complete beginner asking for 100%
  in TSLA gets a "no", with the reasons. Rules and thresholds: `notes/decisions.md` #4–5, code `src/dh/agents/profiler.py`.
- Objective: safety cushion · fund a major project · prepare retirement · generate income · pass on wealth (+ growth).
- Horizon buckets from the presentation: short < 3 y, medium 3–10 y, long 10 y+.
- Constraints: liquidity, exclusions, currency.

**Market data**: deterministic. Ingestion, cleaning, features, then a per-asset summary. No LLM touches the numbers.

**Portfolio**: proposes **at most 3 strategies**, only as many as needed, built from the client's profile.
- Each one is at a different risk level within the client's risk preferences, with balanced distributions.
- Each one lists its advantages and disadvantages.
- Methods: risk-level templates filled with allowed assets (not an optimiser: `notes/decisions.md` #1), diversification
  types (workshop slides), ETF look-through, Monte Carlo, risk of ruin. The efficient frontier is shown as a chart.
- If the request is narrow, answer it directly. Example: a client who wants 3% a year guaranteed is offered bonds.

**Critic** (LLM): the judgment calls rules can't make. Does it make sense, is it really diversified, what would a
sceptic ask? Judges against a short written guide (Will writes it). One round only.

**Guardian** (code, no LLM): "the LLM argues, code enforces". Suitability checks **modelled on** NI 31-103 KYC /
suitability (s.13.2, s.13.3). We never claim legal compliance. Rules (`src/dh/agents/guardian.py`):

| Rule | Checks | On failure |
|---|---|---|
| G1 | KYC essentials known before any proposal | ✘ ask the client |
| G2 | weights valid, sum to 100% | ✘ |
| G3 | only allowed assets (universe, client exclusions, profile) | ✘ |
| G4 | each company ≤ cap, counted through ETFs (look-through) | ✘ |
| G5 | crypto ≤ cap | ✘ |
| G6 | defensive share ≥ floor (incl. money needed within 3 years) | ✘ |
| G7 | historical max drawdown ≤ the level's limit | ✘ |
| G8 | volatility ≤ target | ⚠ |
| G9 | requests that break a limit are refused, not quietly applied | ✘ |
| G10 | exclusions held only through ETFs | ⚠ disclose |
| G11 | explanation carries the simulation disclaimer | ✘ |
| G12 | every % in the explanation matches a computed number | ✘ |
| G13 | explanation addresses each refused request | ✘ |

Any ✘ sends the step back. Known limit of G12: it checks that each number exists in the computed outputs, not that
it is attached to the right label.

**Explainer**: writes the client-facing text, then the app shows it visually. Cites sources, separates facts /
assumptions / fiction, states uncertainty.

All agents write to one trace store: profile info, decisions, verdicts. It is what the jury can inspect.

## The agentic part: four agents that decide (decision #14)

Everything else (Profiler, market data, Portfolio, Guardian) is deterministic code. These four are where the LLM
**decides what to do**. Each runs inside a fixed slot in the pipeline, with a tool budget, and everything it does
goes in the trace. Graph: `aws/architecture.md`.

### What makes them agents

Each one is a **Strands agent**: a model on Amazon Bedrock + instructions + a set of tools. It works in a loop:

1. Read the task.
2. Decide whether it needs information, and if so which tool to call.
3. Get the result back and decide again: another tool, or answer.
4. Stop when it has its answer or hits its call limit (e.g. 5).

The tools are our own Python functions, mostly Joud's market data (`strategy_stats`, `correlations`, `look_through`,
the 2022 stress window, `goal_outlook`). So the agent **chooses what to check, but never makes up a number**: every
figure it uses comes from a tool result.

### The four agents

**1. Extractor (input):** free text → the client's facts.
- In: "I'm 59, retiring in about 4 years, I don't want to lose much, put 25% in Tesla."
- Decides which profile fields it can fill and which essentials are missing.
- Out: the `profile` dict + follow-up questions ("How many months of expenses do you have set aside?").
- The Profiler (rules) then scores the profile. The agent never sets a risk level.

**2. Critic (after the Portfolio):** the sceptic, the most visibly agentic of the four.
- In: the up-to-3 strategies, the client's limits, the market facts, Will's written guide.
- Decides what looks doubtful, then **investigates before objecting**. Example on Amira's growth strategy:
  - "QQQ and SPY might be the same bet" → calls `correlations` → 0.9 → false-diversification objection.
  - "How much NVIDIA is really in there?" → calls `look_through` → 13.2%, close to her 15% cap → flag.
  - "How would this have held up in 2022?" → calls the stress window → −31% → near her limit → objection.
  (Numbers illustrative.)
- Out: at most 3 objections, each tied to the tool result behind it. The Portfolio revises once or justifies.

**3. Explainer (end):** writes the answer for the client.
- In: chosen strategies, limits with their reasons, objections, Guardian verdicts, sources.
- Out: plain language, "data → findings → analysis → proposal → limits".
- Checked by the Guardian (G11–G13): disclaimer present, every % matches a computed number, every refused request
  explained. On ✘, rewritten.

**4. Analyst (in the app, after the result):** answers follow-up questions.
- "What if I add XSP?" → calls `strategy_stats` with the new weights, `look_through`, `correlations` → before/after numbers.
- "Why not more Nvidia?" → finds the cap and its reason in the limits, shows the look-through.
- Its answer is re-checked by the Guardian, so it can't slip in a position that breaks the limits.

### How it fits with the rest

```
profile ─► Profiler (rules) ─► market data ─► Portfolio ─► Guardian
                                                 ▲            │ ✔
                                                 └─ revise ◄── Critic (agent, tools)
                                                              │
                                              Explainer (agent) ─► Guardian ─► app
                                                                              │
                                                       Analyst (agent, tools) ◄┘ follow-ups
```

- **The order is fixed in `pipeline.py`.** Agents decide *inside* their step, never which step comes next, so the
  Guardian always runs.
- **Hard limits:** a cap on tool calls, one round of debate, at most 2 send-backs.

### What the jury sees in the trace

One line per step, for example:

> **Critic → Portfolio:** called `correlations(QQQ, SPY)` → 0.91; called `look_through` → NVDA 13.2% vs cap 15%.
> Objection 1: QQQ and SPY are largely the same bet (correlation 0.91).

Tool calls, results and verdicts only, **never the model's raw reasoning** (brief p.17, decision #9).

### Why this is the right amount of agency

- **Real agency where it's useful:** investigating, arguing, explaining, answering questions. A sceptic that checks
  before speaking is easy to show in a demo.
- **None where it would hurt:** limits, numbers and rules stay code, so "Robert gets a no" is provable and the 16
  scenarios stay reliable.
- **Runs on AWS:** Bedrock models, traces in S3, hosted on AgentCore if ready (slide 7, "real role in the flow").

### What it costs

- Results vary between runs: save the demo runs and replay them (Friday's pitch can't depend on AWS, closed Monday).
- Needs Bedrock models with tool use on the event account: check first, with `strands-agents` and AgentCore.
- Tests: deterministic tests stay offline; for the agents, test that they stay within their tool budget and that the
  Guardian catches anything they invent.

## Portfolio construction: sub-workflows (DRAFT, Sat Nov 14)

Almost everything here is **deterministic**: plain functions that each return a few numbers, a limit, a status and a
reason. The **Critic** (Strands agent, #14) uses the same functions as tools, so all the agency sits in one place.
Thresholds marked "assumption" are team assumptions, to settle and log under decision #5.

```
3 · PORTFOLIO CONSTRUCTION
│
├── A. Strategies: what each one holds ............................. deterministic
│     up to 3 strategies defined by their assets, each with a growth basket and a defensive basket
│     ├── broad core:        XIU + SPY/ESGV        |  ZST + XBB
│     ├── income/dividends:  RY, ENB, FTS, JNJ, PG + XIU  |  XBB + AGG
│     └── growth tilt:       QQQ + a few stocks (+ crypto ≤ cap)  |  ZST + GLD   (only if the profile wants it)
│     allowed assets only (limits.allowed_assets) · ESG tilt (ESGV for SPY) · beginner → broad ETFs only
│
├── B. The split, computed per strategy (decision #17) ............... deterministic
│     ├── B1 Risk ceiling: largest growth share (0–100%, 5% steps) whose 2021–2026 worst drop
│     │      ≤ the client's loss limit = min(tolerance: max_loss_pct, capacity: affordable loss in $)
│     ├── B2 Goal floor: smallest growth share with a reasonable chance at the target (goal_outlook,
│     │      "risk only" first); 0% if bonds alone reach it; none if no target amount
│     ├── B3 Liquidity floor (hard): money needed within 3 years stays defensive
│     ├── B4 Conflict: floor > ceiling → say so + options (longer horizon, lower target, more savings, more risk)
│     └── B5 Result: each strategy shown at its ceiling, with floor, goal outlook and the
│            growth-share vs worst-drop curve (chart) → strategy_stats (market data, Joud)
│
├── C. Diversification ............................................. deterministic
│     ├── C1 Real weight per company (look-through: direct + via ETFs)
│     ├── C2 Geography: country (Canada / US) + currency (CAD / USD)
│     ├── C3 Sector, look-through
│     │     └── C3b Job sector: client's own industry gets a lower cap
│     ├── C4 Asset classes: equity · bonds · gold · crypto · cash
│     ├── C5 Concentration: effective number of holdings (1 / Σw², on look-through weights)
│     └── C6 Hidden overlap: ETF overlap + highly correlated pairs (> 0.85)
│
├── D. Risk vs the client .......................................... deterministic
│     ├── D1 Tolerance fit: worst drop vs the loss they said they'd accept
│     ├── D2 Drawdown capacity: max drawdown in % AND in $ (capital × drawdown) vs the level's limit
│     └── D3 Stress: 2022 window · worst 12 months · CVaR 95%
│
├── E. Goal fit .................................................... deterministic
│     goal_outlook (Joud): chance of a loss / of reaching the target over the horizon,
│     "risk only" view first (no past return as forecast, #13)
│
├── F. Profile fit ................................................. deterministic
│     objective · horizon · liquidity · knowledge · interests/ESG · exclusions (direct + via ETFs)
│
├── G. Request handling ............................................ deterministic
│     client's request applied on top of our proposal → same C–F checks → side by side
│     (Robert's 25% TSLA: real weight, drawdown % and $, which checks fail, the version that fits)
│
├── H. Selection + pros/cons ....................................... deterministic
│     drop any candidate with a ✘ · keep ≤ 3 (fewer if enough)
│     pros/cons written from C–F numbers, never by the LLM
│
└── Critic ......................................................... AGENT (Strands)
      tools = C–G functions · investigates before objecting · ≤ 3 objections · one round
      → Portfolio revises once or justifies → Guardian
```

**Why the split matters most, and why it's computed:** the stocks/bonds split explains most of the difference between
portfolios (Brinson, Hood & Beebower 1986) and is the language of the BNCD workshop, so the app shows it first ("55/45")
with the growth-share vs worst-drop chart. It is computed from the client's own loss limit, goal and liquidity and from
the data, not looked up in a table (decision #17): "55% because more would have lost over 15% in 2022, your limit".

**"Growth" vs "defensive":** growth = stocks + crypto; defensive = `DEFENSIVE` in `rules.py` (ZST, XBB, AGG, GLD).
Risk levels remain a label, the source of the diversification caps, and a Guardian safety net (G6 keeps a small floor,
5% at level 5, so a 100%-equity strategy is still refused).

### What each check returns

Every C–G check returns the same shape, which goes into the trace and to the Critic, Explainer and Guardian:
`{check, value, limit, status ✔/⚠/✘, reason, source}`.

| Blocks (✘) | Disclosed (⚠) |
|---|---|
| company cap (C1) · job sector (C3b) · drawdown capacity (D2) · liquidity, horizon, exclusions (F) · split above the client's ceiling (B) | geography (C2) · sector (C3) · concentration (C5) · overlap (C6) · tolerance close to the limit (D1) |

### Still to decide or add

- **Thresholds (assumptions, for #5):** one country ≤ ~70% of equities · one sector ≤ 30%, or 15–20% for the
  client's job sector · effective number of holdings ≥ 8 · ETF overlap > 50% → ⚠ · satellite ≤ ~20% of growth.
- **Contract changes (`notes/contract.md`, draft):** profile field `employment_sector`; strategy field `split`.
- **New Guardian rules:** G14 geography, G15 sector + job sector, G16 concentration, G17 drawdown in $.
- **Data:** country and sector for ETF holdings. The QQQ and XIU issuer files have them; SPY's doesn't, so for now SPY
  counts as US with its sector unknown.
- **No separate "at least one non-equity asset class" rule:** G6 (defensive floor) already enforces it at every level.

## Input (GUI or text)

- **Text**: the client describes themselves; the Profiler extracts the profile and asks follow-ups for missing essentials.
- **Guided questions**: short wizard (see `intake-form.md`), essential questions first, optional ones folded.
- Both produce the same profile, so the rest of the pipeline doesn't care which was used.

## Testing (Will's notes)

- Fake profiles, including "trap" ones (short horizon but wants high risk, no emergency fund…): 16 of them with
  expected verdicts in `src/dh/agents/scenarios.py`. `make scenarios` runs them; `LOG=1` logs the pass rate.
- Show the steps between agents so each hand-off can be checked: every hand-off writes a plain-language
  description to the trace (`src/dh/agents/trace.py`), printed by `make scenarios`, shown in the app.
- The three official personas (Amira, Mateo, Robert) as the reference cases.

## Differentiators (what should make it stand out)

**1. The pushback moment (Robert).**
Robert asks for 25% in Tesla. The system shows the conflict with his numbers (his drawdown limit, how that mix
did in 2022) and proposes a version that fits him.

**2. Show the agents working (agentic 20%).**
- Don't hide the orchestration. Show a live trace in the app: the Profiler sets the limits, the Critic raises an
  objection, the Strategy revises, the Guardian flags something.
- Judges score "agentic" from what they can see. A visible debate and a visible veto beat a black box with ten agents.
- Follow-up questions: when the profile is missing something essential, the Profiler asks instead of guessing.
  That shows the agent adapting, and it costs little.

**3. Go beyond the starter data, in one targeted place (data 20%).**
- Everyone will use the starter pack as is.
- Look inside ETFs: what an ETF actually holds by country, sector and currency, and how much two ETFs overlap.
  This was the exact example from the BNCD workshop (ZEQT vs XSP), so the people grading know it.
  It shows that 3 ETFs can be one bet.
- Or, for Mateo, evidence of company controversies from public filings or sustainability reports, with sources cited.
- Pick one, not both.

## Open decisions (to settle together)

1. ~~Monte Carlo inputs in the intake?~~ Yes: capital, contribution, target are in the contract.
2. Asset universe: starter pack only, or add data (ETF holdings, ESG, fundamentals)?
3. How many LLM agents vs plain code? (The brief says the number of agents is not a goal in itself.)
4. Which AWS services (Bedrock for sure; S3, Lambda, Step Functions, Guardrails, hosting?) and whether we use Kiro.
5. Single objective per run, or several sub-portfolios per objective?
6. Who owns which agent / lane.
