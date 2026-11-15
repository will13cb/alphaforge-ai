> **Release status (Nov 15 integration):** activity, voice and existing-portfolio review are integrated with the quantitative risk fixes. Regenerate Bedrock caches with `make warm` on the final dataset. This review environment has no AWS credentials; fresh AWS execution is not claimed. Numeric validation also checks common metric/sign wording, but does not prove arbitrary prose.

# AlphaForge AI — Technical documentation

William Caron-Bastarache · Joud Katbe · PolyFinances Datathon 2026 (National Bank × AWS). Sections follow the brief
(p.15). Simulation only, fictional profiles, not financial advice.

> Every number quoted for the personas is in `results.csv` (experiments `persona-*`, `standin-*`, `guardian-scenarios`).
> Decisions referenced as #n are in `notes/decisions.md`.

## 1. Agents, roles and controls

**Overall logic** (graph: `aws/architecture.png`). `src/dh/agents/pipeline.py` runs the agents in a fixed order, with
one Critic round. Each one reads and writes plain JSON-ready dicts (`notes/contract.md`), and each hand-off is written
to a trace. The order is fixed on purpose: an agent decides *inside* its step (which tools to call, what to object to,
how to say it), never which step comes next, so the Guardian can't be skipped (#14). Four steps are **Strands agents on
Amazon Bedrock** (Claude Opus 5.5): they choose which deterministic tools to call. Everything that sets a limit or a
number is plain Python. *Agents investigate and argue; code enforces.*

| Step | Agent | How it works | Output |
|---|---|---|---|
| 0 | **Extractor** (`extractor.py`) | Strands agent, tool `check_profile` | profile fields from the client's own words; every number must appear in their text; missing essentials → questions (#29) |
| 1 | **Profiler** (`profiler.py`) | rules | risk tolerance, risk capacity, knowledge score; loss limit (% and $); defensive floor; one cap per company and for crypto; each with a written reason; flags requests that don't fit; KYC bets as a cross-check (#40) |
| 2 | **Market data** (`market.py`, Joud) | deterministic | per asset: return, volatility, worst drop, CVaR 95%, worst 12 months, 2022; correlations; goal outlook |
| 3 | **Portfolio** (`portfolio.py`, `checks.py`) | rules + data | up to 3 strategies with their split, stats, diversification checks C–F and the notes of every adjustment |
| — | **Guardian** (`guardian.py`) | loss, diversification and consistency rules | ✔ / ⚠ / ✘ after the Profiler, after each strategy, after the text |
| 4 | **Critic** (`critic.py`) | Strands agent, 11 tools, ≤ 6 calls | ≤ 3 objections, each backed by a tool result it obtained; one fix per strategy, recomputed by code (#30) |
| — | **Request side by side** (`requests.py`) | rules | the client's request "as asked" vs "what fits", same checks; pros and cons from the numbers only (#28) |
| 5 | **Explainer** (`explainer.py`) | Strands agent, tool `check_text` | the client text, written from facts where every number is an id (#23, #27) |
| app | **Analyst** (`analyst.py`) | Strands agent, tools, ≤ 5 calls | answers to follow-up questions; its what-ifs re-run the whole pipeline (#35) |
| app | **Existing portfolio** (`existing.py`) | rules + the same agents | what the client already holds, reviewed with the same checks C–F and Guardian, then rebuilt into the first proposed strategy with each move in $ (#42, #44) |
| — | **Trace store** (`tracestore.py`) | Amazon S3 | the whole run as JSON in `s3://<bucket>/traces/`, from both apps and the CLI (#25) |

**What a ✘ does.** On the profile (G1): no proposal, the client is asked. On a strategy: it is dropped and the trace
says which rule. On a Critic fix: the original strategy is kept. On the text: the deterministic template replaces it.
Nothing loops back (the Critic gets one round), so every run ends, and the trace says what happened.

**Controls (Guardian).** Suitability checks *modelled on* Canadian know-your-client and suitability duties
(NI 31-103 s.13.2–13.3); not a legal compliance test (#3).
- **Before any proposal:** G1, the essential facts must be known; otherwise ask the client.
- **On each strategy:**
  - G2 valid weights; G3 allowed assets only; G4 each company within its own cap, counted through ETFs; G5 crypto;
  - G6 defensive floor; G7 worst drop within the client's loss limit; G8 volatility (warning);
  - G9 a request that doesn't fit is never quietly applied; G10 exclusions held through ETFs (disclosed);
  - G14–G17 (from `checks.py`, #20): geography, sector and the client's own job sector, concentration, worst drop in $.
- **On the text:** G11 the disclaimer is present; G12 every % and $ in it is exactly one of the computed facts; G13
  every request that doesn't fit is explained.

**What each agent is allowed to do, and what code checks.**
- **Extractor:** fills only the fields the client stated. Code checks the schema, maps names to tickers (Tesla → TSLA),
  and drops any number not written in the client's text; what's missing is asked, never guessed (#29).
- **Critic:** chooses what looks doubtful and investigates with tools before objecting: Joud's market tools
  (`portfolio_stats`, `stress_test`, `correlation_between`, `goal_check`, `required_return`…), views on the run
  (`look_through`, `strategy_checks`, `limit_reason`) and `risk_contributions` (each holding's share of the risk,
  from the covariance only). Code drops an objection that cites no tool call it made, or quotes a number that is
  neither in its cited results nor in the facts it was given (the client, the limits, that strategy's numbers, or
  the sum of two of its weights) (#45). A fix comes from a menu (merge two holdings, trim one, shift growth to defensive, disclose)
  and can only **tighten** an input of the calculation; then the whole Portfolio calculation reruns (split search,
  stats, goal outlook, checks) and the Guardian re-checks against the client's original limits. If that fails, the
  original stays ("kept, justified"). One round, one fix per strategy (#30).
- **On an existing portfolio:** the Critic reviews it with the same tools, disclose only (the rebuild is the fix);
  the Explainer adds a section "The portfolio you already have"; the Analyst gets two tools, `existing_portfolio` and
  `what_if_existing` (#42).
- **Analyst:** answers follow-ups ("what if I put 10% in NVDA?") by calling tools, two of which re-run the real
  pipeline, Guardian included. Every number in its answer must appear in a tool result it cites; no buy/sell wording;
  the disclaimer is added by code; otherwise the deterministic answer replaces it (#35).

**The Explainer never types a number.** Every % and $ in its facts is an id (`{n7}`); it writes ids and code
fills in the values, so a number it typed itself is rejected (decision #27). **Its own control:** its one tool, `check_text`, runs G11–G13 on its draft; it may check up to 3 times
before answering. Then code checks the final text again: if it fails, or AWS errors, a deterministic template
(which passes by construction) replaces it and the trace says why (#23).

## 2. Methods, models and technologies, and why

- **Rules where the answer must be provable, an LLM where language matters** (#2). Limits, numbers and verdicts are
  deterministic, so the same answers always give the same limits and the 16 test profiles stay reliable. The LLM
  reads free text, decides what to investigate, argues and explains, inside guardrails; it never sets a limit or a number.
- **No optimiser** (#1, #37): optimised weights on 5 years that include 2022 are unstable (DeMiguel, Garlappi & Uppal 2009).
  We tested it (Joud's mean-variance optimiser, branch `optimisation-markowitz`): the "optimal" portfolio changed with
  the window and did not beat equal weights out of sample, so it stays off the demo. What doesn't need average
  returns is used (#40): **risk contributions** (each holding's share of the risk, from the covariance only) as a
  Critic tool, and Joud's **KYC bets** (three 50/50 bets → risk aversion A) as a cross-check of the client's tolerance,
  flagged "to clarify" when they disagree, never a limit; plus one expected-value question that caps knowledge if wrong.
  Strategies are defined by what they hold: broad core (XIU + SPY or ESGV, short and aggregate bonds), income
  (dividend payers + XIU, aggregate bonds), growth tilt (QQQ, large tech, short bonds and gold; only for an interest in
  AI/tech/crypto, risk level ≥ 3, knowledge ≥ 3). Crypto only if the client asked for it, the profile allows it, and
  the data agrees: with crypto, the growth share inside the loss limit must not be lower than without it (#26).
- **Split and final loss rule (integrated quantitative audit, decision #46).** The horizon rule and liquidity floor remain. The growth ceiling scans a stationary block bootstrap over the client's horizon, stopping before the simulated probability of exceeding their loss threshold rises above 10%. The central drift is cash plus a **3% annual premium on the growth part**, a team assumption, not a forecast. Sub-window sensitivity is disclosed. The final weights are checked with fresh simulated paths (G7/D2, including sampling tolerance); G17 is folded into G7, and G18 checks that statistics, outlook, risk and checks describe the final weights. Historical drawdown remains descriptive. The bootstrap cannot create unseen crises; the model's 10% threshold is not a calibrated guarantee of a 10% real-world breach rate.
- **Up to three strategies = three risk levels** (#32): the most growth the client's limits allow, then 10 and 20
  points less in stocks (each a full recalculation with a higher defensive floor, never above the client's limits).
  The client's preferred flavour (growth tilt, broad core, income) takes the first level. Levels closer than 5 points
  are dropped, so a client with little room (Robert) gets two, not three near-copies.
- **Longer history, optional** (#31): `make data-long` rebuilds the same 31 assets from 2004 with the organizers'
  script (USD/CAD from FRED before the Bank of Canada series). A strategy's numbers use only days when every asset
  it holds traded; ZST (2011) and ESGV (2018) get documented stand-ins before their first price (the overnight rate,
  SPY); the 2008 and 2020 sell-offs are reported when covered.
  If a goal needs more risk than allowed, the conflict is shown with the options.
- **Caps per company and per client** (#24): a company's own worst 2021–2026 drop, at its weight, may cost at most ¼
  of the client's loss limit, and no company exceeds ⅕ of what the client can hold in stocks. Crypto (BTC + ETH) is one
  bet under the same rule. Beginners get half the budget and no crypto.
- **Look-through** (#6): direct weight + weight held inside ETFs (issuer holdings files).
- **A portfolio the client already holds** (#42, #44): entered line by line or in free text ("I have 10k in XIU"; the
  amount must be in the text). It gets the same checks as any strategy, a critique written from those numbers, its
  yearly fund fees in $ (each fund's own net expense ratio; unknown fees listed, never 0), and the moves in $ to the
  first proposed strategy. No optimiser (#1, #37). A fund we have no data for is measured with a **labelled
  stand-in** tracking the same or a close index (22 funds, `dh.standins`); CAD-hedged funds (XSP.TO…) take the
  source's USD return plus the Canada–U.S. overnight-rate gap. A fund with its own mix (ZEQT) is left aside, said so.
- **Technologies:** Python, pandas/numpy/scipy; Strands Agents SDK; Amazon Bedrock (Claude Opus 5.5,
  `global.anthropic.claude-opus-5-5`, us-east-1, one default model for every agent, #45); Amazon S3; Streamlit for the
  two apps (hosted on Streamlit Community Cloud, data from S3 at first start). Optional voice in the guided interface:
  Amazon Transcribe (speech → text, English or French Canada) and Amazon Polly (text → speech), off unless
  `AF_VOICE_ENABLED=1`; audio goes through S3 under `voice/` and is deleted once transcribed.
- **Why these AWS services** (slide 7: real role, no services added to impress): **Bedrock** runs the four steps that
  need judgment or language (Extractor, Critic, Explainer, Analyst); the **Strands Agents SDK** gives each its tools and
  tool loop; **S3** keeps the evidence of every run, so any answer can be audited after the fact, and serves the data
  to the hosted app; **Transcribe and Polly** (optional) let a client speak instead of type, for accessibility. Bedrock AgentCore
  Runtime was planned to host the pipeline and is not deployed. Bedrock answers are cached and committed (`cache/`),
  so the demo replays the real agent outputs after the event account closes.

## 3. Sources, selected assets, processing, assumptions

- **Starter pack** (organizers): 31 assets (10 Canadian and 10 U.S. stocks, 9 ETFs including bonds, gold and an
  ESG-screened fund, BTC, ETH), daily 2021-11-12 → 2026-11-12, from Yahoo Finance; USD/CAD and Canadian rates from the
  Bank of Canada; U.S. rates, CPI and unemployment from FRED.
- **ETF holdings:** State Street SPY daily file, as of 2026-11-12 (503 holdings, `CONTEXT.md`). QQQ, ESGV and XIU not
  loaded: for those ETFs, look-through and sector checks are lower bounds, and the checks say so.
- **Processing:** daily simple returns on adjusted close; everything converted to CAD at the Bank of Canada rate; one
  weekday calendar for every asset (crypto weekends dropped); annualised with the observed rows per year (#12).
- **Assumptions (all written in `rules.py` and the decisions):** the horizon anchors (2 and 15 years); ¼ and ⅕ in the
  company caps; the capacity side of the loss limit (from the client's capacity level); the 50% chance used for a
  goal floor; diversification thresholds (#20). Profiles are fictional.
- **Licences:** data used for a non-commercial educational prototype; raw files not redistributed (#11).

## 4. Explainability mechanism, with one worked example

**Mechanism.** Every limit carries a written reason; every strategy carries its numbers and the notes of what was
adjusted; every hand-off is a trace step (who → whom, what, ✔/⚠/✘). The Explainer only sees `facts`, a small JSON
whose numbers are already formatted as the text must show them, so it copies instead of computing. The trace shows
steps, numbers and verdicts, never the model's raw reasoning (brief p.17, #9). Every run is saved to S3.

**Worked example: Robert asks for 25% in Tesla** (`make explain P=robert`).
1. **Profiler:** tolerance 2 (he'd hold through a 20% drop, but accepts at most 15%: the more cautious answer wins);
   capacity 2 (4-year horizon); loss limit 15%, 60,000 $ on 400,000 $; horizon 4 years → at most about 15% in stocks.
   Tesla: worst 2021–2026 drop −70.9%; at 25% that alone would be −17.7% of the portfolio, more than his whole 15%
   loss limit; it fits up to 3.1%.
2. **Portfolio:** broad core 15/85, worst drop −8.6%, 2022 −5.8%; income 5/95, worst drop −7.7% (final `persona-strategies` rows, source commit 9a2febb).
3. **Guardian:** both strategies are checked against the loss, diversification and consistency rules; missing ETF holdings are disclosed; Tesla isn't in either (G9).
4. **Critic** (Opus 5.5): calls its tools on the two strategies, e.g. correlations between holdings, the checks
   closest to their limit, each holding's share of the risk; each objection quotes a tool result; a fix, if any, is
   recomputed and re-checked. The trace lists every call and what happened to each objection.
5. **Request side by side:** 25% Tesla "as asked" vs "what fits", with the same checks.
6. **Explainer** (Opus 5.5, one self-check): "In 2021-2026, TSLA's worst drop was −70.9%. At 25%, that holding alone
   would have cost −17.7% of the portfolio, which is more than your whole 15% loss limit. TSLA fits your limits up to
   3.1%. The decision is still yours; we only show what fits the limits you gave us."
7. **Guardian on the text:** G11 disclaimer ✔, G12 every % traced ✔, G13 Tesla explained ✔. Run saved to S3.
8. **Follow-up (Analyst):** "what if I put 10% in Tesla?" re-runs the pipeline with that position and answers with
   the resulting numbers and the rules it breaks.

## 5. Validation, limitations, improvements

**Validation.**
- 16 test profiles with expected verdicts (`make scenarios`): 16/16 (`results.csv`). They include deliberate failures
  (a strategy that quietly applies Tesla, an explanation with an invented number, a missing disclaimer) to show the
  Guardian catches them. They test the rules, not real portfolios (#7).
- The offline regression suite (`make test`): synthetic data, faked AWS; e.g. the split never exceeds the loss limit and is the
  largest that fits; the Explainer's text is replaced when it breaks a rule.
- **The agents are tested against their controls** with a faked model: a Critic objection quoting a number no tool
  returned is dropped; more than 3 objections or 6 tool calls are cut; a fix that would break a limit is reverted;
  an Extractor number not in the client's text is dropped; an Analyst answer with an unbacked number is replaced;
  an AWS error falls back to the deterministic version and the trace says why.

**Limitations.**
- Historical numbers describe the data window: on the starter pack 2021–2026, one mild bear market in CAD (the long
  build adds 2008 and 2020); they are not predictions, and future drops can be larger. Survivorship bias: the 31
  assets were chosen in 2026, which flatters any past return (equal-weight stocks +21%/yr vs SPY +14.5%, audit).
- The horizon anchors (2 and 15 years) decide most splits; they are a stated judgment, not a measurement.
- The assumptions listed in §3 are explainable but not calibrated beyond this window.
- The Explainer can't type a number (it writes ids that code fills in), but it could put a real number next to the
  wrong label; G12 can't see that. The same holds for the Critic's and Analyst's number checks, and for the
  Extractor's grounding check (the number is in the text, not necessarily attached to the right field).
- The agents' answers vary between runs; the demo replays committed Bedrock answers, and a new run can differ.
- Only SPY's holdings are loaded; 3 of 4 equity ETFs are looked through as single blocks.
- Stand-ins for funds without data: unhedged ones match the real fund's worst drop within ±0.4 point; CAD-hedged ones
  understate it by 1 to 3 points (`results.csv`, `standin-*`). The real number is shown next to every stand-in.
- Fund fees are shown in $ but not deducted from the historical returns.
- No fees, taxes or account types (TFSA/RRSP); a single goal per run.

**Tested and set aside.** A protected (CPPI) strategy (#21) and two mean-variance optimisers (#37): on one 5-year window their weights changed with the period and did not beat equal weights out of sample, so the strategies stay defined by what they hold, with the split set by the client's limits.

**Improvements.** Independent calibration of the simulated loss model and its premium assumptions; company
caps from the worse of two sub-periods (S4); the capacity side of the loss limit from the client's own balance sheet;
the remaining ETF holdings; several goals per client; hosting the pipeline on Bedrock AgentCore; screens for the
KYC bets in the guided interface.

## Reproduce
```
make setup && make data && make check     # data: starter CSVs into data/raw/
make scenarios && make test               # validation, offline
make explain P=robert                     # full pipeline + Critic + Explainer (Bedrock with .env, cached otherwise)
make extract T="I'm 59, retiring in 4 years, put 25% in Tesla"   # free text → profile (Extractor)
make warm                                 # with .env: refill every Bedrock demo cache, then commit cache/
make log-personas                         # numbers quoted in the pitch → results.csv
make app                                  # demo app (agents, trace); make ui: guided interface
```
Windows: `python -m dh check`, `python -m dh explain robert`, `python -m pytest -q`, `python -m streamlit run app/app.py`.
