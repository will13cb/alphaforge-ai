# Decisions and why (long form)

One entry per decision. The one-line version goes in the `CLAUDE.md` decisions log. Code that implements it is named.

---

## 1. Strategies come from risk-level templates, not from the efficient frontier (Sat Nov 14)

> **Revised by #17:** strategies are defined by what they hold; their stocks/bonds split is computed from the
> client's limits and the data, not from a per-level template. The "no optimiser" part stands.

**Decision:** Portfolio builds each strategy from a template for its risk level (a mix of defensive / equity /
growth sleeves), then fills it with allowed assets and checks it against the limits. The efficient frontier is
drawn in the app as a chart, to show where the strategies sit. It does not choose the weights.

**Why, simply:**
- An optimiser picks weights from past returns. We have 5 years, and they include 2022, when stocks and bonds
  fell together. Change the window by a few months and the "optimal" weights jump. A client can't be told
  "60% in X because of the last 5 years".
- Research agrees: a simple equal split (1/N) often does as well as optimised portfolios on new data
  (DeMiguel, Garlappi & Uppal 2009), because the optimiser fits noise.
- Templates are explainable in one sentence ("Cautious = at least 50% in bonds/gold, then broad ETFs") and
  always respect the limits by construction.
- The frontier still earns its place: it shows the risk/return trade-off visually, and judges asked for it.

## 2. The Guardian is code; the Critic is the LLM (Sat Nov 14)

**Decision:** The Guardian is deterministic rule checks (`src/dh/agents/guardian.py`, rules G1–G13). The Critic
is the LLM making judgment calls (does it make sense, is it well diversified, what would a sceptic ask). One round.

**Why:** both were judging "suits the profile / makes sense". Splitting them gives one clean story:
**the LLM argues, code enforces.** A rule check gives the same answer every time, so it can be tested
(`make scenarios`) and the jury can trust a ✘. The Critic adds what rules can't see.

## 3. "Modelled on" Canadian rules, never "compliant with" (Sat Nov 14)

**Decision:** we say "suitability checks modelled on NI 31-103 KYC / suitability (s.13.2, s.13.3)" and list the rules
we actually check (G1–G13). We never claim legal compliance.

**Why:** a hackathon prototype can't prove legal compliance, and a jury from a bank will spot the claim.
Being explicit about what is checked (and what isn't) is itself part of explainability.

## 4. Knowledge score from rules, not from the LLM (Sat Nov 14)

**Decision:** `knowledge_score` (1–5) = declared level (none 1 … advanced 4), +1 for 5+ years in stocks/ETFs,
capped by the mini-quiz (0/3 → max 2, 1/3 → 3, 2/3 → 4). The LLM only extracts these answers from free text.
`src/dh/agents/profiler.py`.

**Why:** if the LLM scores knowledge, the same answers can give different limits on two runs, and we can't
explain why. With rules, every limit has a written reason the Explainer quotes.

## 5. Risk-level thresholds (Sat Nov 14) — team assumptions

> **Revised by #17:** the split and the drawdown limit now come from the client (own loss limit, goal, liquidity)
> and the data. Risk levels stay as a **label** ("Cautious"…), for the **diversification caps** (one company,
> crypto, satellite) and as a **safety net** in the Guardian. The scoring of tolerance and capacity below stands.

**Decision:** five risk levels, `src/dh/agents/rules.py`:

| Level | Name | Max drawdown | Target vol | Defensive ≥ | One company ≤ | Crypto ≤ |
|---|---|---|---|---|---|---|
| 1 | Preserve | 8% | 5% | 75% | 5% | 0% |
| 2 | Cautious | 15% | 8% | 50% | 8% | 0% |
| 3 | Balanced | 22% | 12% | 30% | 10% | 2% |
| 4 | Growth | 30% | 16% | 15% | 12% | 5% |
| 5 | Aggressive | 40% | 22% | 5% | 15% | 10% |

How a profile gets a level:
- **Tolerance** (1–5) = the more cautious of: reaction to a 20% drop (sell all 1, sell some 2, hold 4, buy more 5)
  and max acceptable loss (≤10% → 1, ≤15% → 2, ≤25% → 3, ≤35% → 4, more → 5).
- **Capacity** (1–5) = horizon (<3 y → 1, <5 → 2, <10 → 3, <15 → 4, 15+ → 5), minus 1 each for: emergency fund
  under 3 months, uncertain income, 25%+ may be withdrawn within 3 years. Safety-cushion objective → 1.
- **Risk level = the lower of tolerance and capacity** (standard KYC practice: capacity can veto tolerance).
- **Knowledge ≤ 2** → no crypto, single-company cap halved.
- **Money needed within 3 years** raises the defensive floor to at least that share.

**Why these numbers:** round steps that grow steadily and are easy to explain. They are a starting guess, not
calibrated yet. **To validate on our data:** run `make check` and compute
the 2022 drawdown of each template; if a Cautious template can't stay under 15% with this universe, adjust the
threshold (not the data) and log it. The "one company" cap counts exposure through ETFs (decision 6).

## 6. Single-company cap counts look-through exposure (Sat Nov 14)

**Decision:** caps on one company apply to direct weight + weight held through ETFs
(`dh.metrics.look_through`). Exclusions found only inside ETFs are a ⚠ (disclose), not a ✘.

**Why:** 10% NVDA + 30% QQQ + 20% SPY is not 10% NVDA. Without look-through the Guardian approves concentrated
portfolios. Exclusions inside broad ETFs are hard to avoid entirely, so we show them instead of hiding them.

**Data needed (not in the starter pack):** ETF holdings files from the issuers (SPY: State Street, QQQ: Invesco,
ESGV: Vanguard, XIU: iShares), one snapshot date. Limits to document: holdings are today's, not historical, so they are
used for exposure, never to rebuild past returns. Until loaded, G4 says "direct only".

**Status (Sat Nov 14):** loader `src/dh/holdings.py` (own file, not `data.py`), build `scripts/build_holdings.py`, sources
in `data/README.md`. SPY loaded from State Street (as of 2026-11-12). QQQ, ESGV, XIU must be downloaded by hand because
their pages load holdings with JavaScript. The Guardian uses real holdings by default; the 16 scenarios keep their
ILLUSTRATIVE holdings so the tests stay offline.

**ESGV fossil-fuel exclusion: not verified.** Vanguard's ESGV page didn't render for our fetch (JavaScript), so we
could not read its stated screens. Until someone reads the page or the FTSE US All Cap Choice Index methodology
and quotes it here with the URL, don't claim ESGV excludes fossil fuels.

## 7. Validation: 16 test profiles with expected verdicts (Sat Nov 14)

**Decision:** `src/dh/agents/scenarios.py` holds 16 fictional profiles (the 3 personas + trap cases: beginner asking
for 100% BTC, short horizon but wants high risk, no emergency fund, overconfident, large withdrawal coming, missing
horizon, an invented number in the explanation, missing disclaimer…), each with its expected verdict.
`make scenarios` runs them and prints every hand-off; `make scenarios LOG=1` logs the pass rate to `results.csv`.
Logged: 16/16 (commit `5f380e0`). Expectations were changed on purpose to confirm the tests can fail, and they did.

**What the number does and doesn't mean (say this in the pitch and the technical doc):**
- It tests the **rules** (Profiler + Guardian), not real portfolios: the scenarios use made-up strategy stats.
  Pitch wording: "16 test profiles, 16 correct verdicts", nothing about returns.
- **Limit of G12:** it checks that each number in the explanation exists among the computed outputs, not that it is
  attached to the right label.
- The risk-level thresholds (#5) are still a starting guess until checked on the 2022 data.

## 8. Lanes (Sat Nov 14)

**Decision:** Will owns everything (agents, app, AWS, pitch) except deterministic market data, which Joud owns
(`src/dh/data.py`, the market-data agent). `src/dh/metrics.py` and `notes/contract.md` are shared: ask before editing.

**Why:** Joud is already building the market-data layer; one owner per file avoids merge conflicts. Anything Will
adds that touches data (e.g. ETF holdings) goes in its own file, not in `data.py`.

## 9. What the brief rules out, applied to our outputs (Sat Nov 14)

**Decision:**
- The visible trace shows **steps, numbers and verdicts**, never the model's raw internal reasoning (brief p.17:
  explanations "without inventing justifications or exposing detailed internal model reasoning").
- The Explainer never presents historical numbers as predictions: "this mix lost X% in 2022" describes the past;
  it says so, and volatility is one indicator among others.
- AWS must do real, visible work in the flow (slide 7, qualifying requirement); each service justified.

**Why:** these are explicit in the brief and slides; breaking them can cost eligibility or credibility.

## 10. Market data: what is computed, and where (Sat Nov 14, Joud, `lane/market-data`)

**Decision:**
- The market-data agent (`src/dh/agents/market.py`) is deterministic: no LLM touches its numbers.
- **Base stats come from `dh.metrics`** (annualised return, volatility, Sharpe, max drawdown), so the agent quotes the
  same numbers as `make check` (rule 1). **Tail and stress measures come from `dh.quant_toolkit`** (Joud's toolkit:
  erk.py + evaluation.py, fixed and extended): CVaR 95%, worst rolling 12 months, the 2022 stress window,
  correlations, data-quality alerts.
- **2022 behaviour is shown two ways:** calendar year 2022, and the S&P 500 peak-to-trough window 2022-01-03 →
  2022-10-12 (return + deepest drop inside it). The window dates are indicative, labelled as such in `assumptions`.
- **CVaR on daily returns, 95%, historical** (no distribution assumed), reported as a positive loss.
- **Every rate is a fraction** (0.12 = 12%), so the Guardian's G12 can match each % in the explanation to a number.
- **`strategy_stats(weights)` uses the names the Guardian already reads** (`max_drawdown` for G7, `ann_vol` for G8):
  Portfolio can put its output straight into `strategy["stats"]`.
- Every output carries `sources`, `assumptions` and `limits`, so the Explainer can cite them without inventing.

**Why:** one owner for the numbers and one path to compute them; the toolkit adds what the brief asks for (risk beyond
volatility, 2022 behaviour, uncertainty) without a second, diverging copy of the base stats. Fractions and fixed
names make the hand-off to Portfolio and Guardian a copy, not a translation.

**Limits:** five years of daily data, so tail measures rest on few crises; the 2022 window is one episode, not a
stress model; nothing here predicts future returns (#9).

## 11. Starter CSVs are shared by hand, not through git (Sat Nov 14, revised)

**Decision:** the six starter-pack CSVs in `Datathon2026Infos/alphaforge_starter/` stay out of git. Will shares the folder
with Joud directly; `make data` copies them into `data/raw/`. Nothing under `data/` goes in git either.

**History:** they were committed briefly (`a24478b`) and removed in the next commit. They are still in this repo's history,
so the submission must be a **fresh repo** that doesn't carry this history.

**Why:** Yahoo Finance's terms don't allow redistributing its data, and the brief asks us to respect redistribution terms.
Sharing the folder by hand gives both lanes the exact same files without putting them in git.

## 12. Annualise with the observed rows per year, not a fixed 252 (Sat Nov 14, Joud, `lane/market-data`)

**Decision:** `dh.metrics.ann_return`, `ann_vol` and `sharpe` annualise by default with `periods_per_year(returns)` =
(rows − 1) / years between the first and last date. Fixed `TRADING_DAYS = 252` is kept only as a fallback (no date
index, or under 90 days of data). `periods=` still overrides. The market-data agent uses the same figure for the
rolling 12-month window and the correlation report.

**Why:** the weekday calendar in `harness.toml` keeps ~261 rows a year (holidays forward-filled as 0% days). With 252,
5 years were annualised as 5.18: a true 10%/yr CAGR came out at ~9.6%, volatility ~1.7% too low (relative). A judge
recomputing a CAGR by hand would not match our number. Options weighed: set 261 (magic number, breaks if the calendar
changes), drop holidays (US/CA holidays differ, crypto trades 7/7, touches `data.py` + `harness.toml` the day before
the deadline), document only (knowingly wrong numbers). Observed frequency is exact for any calendar, one function.

**Checked on the real starter data:** the row count depends on which tickers are loaded (union of their dates):
SPY alone = 1254 rows (~251/yr), SPY with the 31 assets = 1304 rows (~261/yr). With fixed 252, SPY's CAGR was 14.5%
alone but 14.0% inside the universe, so two agents could quote different numbers for the same asset. With the
observed frequency it is 14.5% both ways (vol 16.6% both ways).

**Limits:** volatility still includes the ~9 holiday 0% days a year (≈0.1% relative effect, negligible). `make check`
numbers shift slightly (return and vol up ~3% and ~1.7% relative); max drawdown, 2022 return and CVaR unchanged.

## 13. Risk-level thresholds checked on 2021-2026; goal outlook leads with "risk only" (Sat Nov 14, Joud, `lane/market-data`)

**Threshold check** (`experiments/data/threshold_check.py`, `results.csv` experiment `threshold-check`): for each level,
the riskiest mix `rules.py` allows with broad ETFs (defensive at `min_defensive`, crypto at `max_crypto`, rest in
XIU/SPY/QQQ), 2 defensive × 2 equity baskets = 20 cases.
- **G7 drawdown limits hold in 90% of cases** and grow with the level (worst: L1 −10.5%, L2 −14.7%, L3 −19.5%,
  L4 −23.8%, L5 −28.2%). Levels 2–5 always pass.
- **Level 1 "Preserve" (8%) fails with an equal-weight defensive basket** (−9.5% / −10.5%): AGG, XBB and GLD all fell
  in 2022. It passes only if the defensive part is short-term heavy (ZST.TO 60%).
- **G8 vol targets hold in 50%**: at `min_defensive`, L1 (5%) and L2 (8%) are exceeded in every case. G8 is a warning,
  so this is consistent, but these targets would rarely be met at the edge of the rules.
- In CAD, 100% XIU/SPY lost only −16% at worst (USD gains in 2022 cushioned it): for broad ETFs the drawdown limits of
  L3–L5 do not bind; they bind on single stocks and crypto.

**Proposed to Will (rules.py / Portfolio, not applied):** either level 1's defensive part is short-term heavy
(ZST.TO ≥ 60%) in the Portfolio template, or level 1's `max_drawdown` goes to 10%. Same for target_vol L1/L2 if we want
G8 to be quiet on compliant templates.

**Goal outlook** (`market.goal_outlook`): stationary block bootstrap of the strategy's own daily returns, fixed seed,
run twice: `replay` (2021-2026 as it was) and `risk_only` (same swings, average return replaced by cash = ZST.TO).
Lead with `risk_only`: on 30/30/30/10 XIU/SPY/XBB/GLD, 400k CAD, 4 years, `replay` gives a 1% chance of loss and
`risk_only` 23%. Replay alone would present 2021-2026 returns as a forecast (#9).

**Limits:** one 5-year window, one bear market; baskets chosen by us; no fees or taxes; bootstrap can't produce a crisis
worse than 2021-2026.

## 14. Strands agents for the steps that decide; our pipeline orchestrates; Bedrock + S3 + AgentCore (Sat Nov 14, Will)

**Decision:**
- **Agents that decide** which tools to call are built with **Strands Agents** (AWS's open-source agent SDK) on
  **Amazon Bedrock**: the free-text extractor, the Critic, the Explainer, and an analyst for follow-up questions in
  the app ("what if I add XSP?"). The Critic investigates with tools (`strategy_stats`, `correlations`,
  `look_through`, the 2022 stress window, `goal_outlook`) before objecting; every objection rests on a tool result it
  obtained. Tool calls are capped and written to the trace.
- **The deterministic core stays plain Python**: Profiler, market data, Portfolio, Guardian. The agents call it as tools.
- **Orchestration stays in `pipeline.py`**: fixed order, bounded loops. Not a supervisor agent, not AgentCore.
- **AWS:** Bedrock (models for the agents), S3 (input profiles, starter data, run traces), **Bedrock AgentCore
  Runtime** to host the pipeline as one endpoint the app calls, if it works by Sunday midday; otherwise local + S3.
- **Not used:** the older Bedrock Agents service (console-configured, hard to test and version, less control of the
  trace). LangGraph/ADK: Strands is the AWS equivalent and counts toward the AWS requirement.

**Why:**
- Only template-filling LLM calls would read as a workflow, not agents (agentic = 20%). Tool-using agents show real,
  observable agency where it adds value: investigating, arguing, answering follow-ups.
- Keeping the order in code guarantees the Guardian runs every time, so "code enforces" stays true and the 16 test
  scenarios stay reliable. A supervisor agent choosing the next step could skip it.
- AgentCore is a host (runtime, memory, observability), not an orchestrator.
- Strands + Bedrock + S3 (+ AgentCore) gives AWS a real, visible role in the flow (slide 7, qualifying).

**Limits / to check first:** that `strands-agents` installs and which Bedrock models with tool use are enabled on the
event account; that AgentCore is available. Agent runs vary between runs: cache and save the demo runs so Friday's
pitch doesn't depend on AWS (closed Monday). The app shows tool calls, results and verdicts, never raw reasoning (#9).


## 15. Deterministic market-data functions exposed as tools to the Strands agents; one calendar for every load (Sat Nov 14, Joud, `lane/market-data`)

Follows #14 (Critic and Analyst call the deterministic core as tools). **Market data stays deterministic code, not an
AI agent:** no LLM inside; the Strands agents only call these functions and read the result, they can't change it.

**Decision:**
- `src/dh/agents/market.py` exposes `AGENT_TOOLS` = `list_assets`, `asset_facts`, `portfolio_stats`, `stress_test`,
  `correlation_between`, `goal_check`: simple JSON arguments, compact JSON output (4 decimals), Google-style docstrings
  (Strands reads them as the tool description), and **errors returned as `{"error": ...}`, never raised**, so the agent
  can recover. Will wraps them with strands' `@tool`; this module doesn't import strands.
- **An asset outside the 31 is refused with a clear message** (+ the list of what is available). Example in #14,
  "what if I add XSP?": XSP is not in the starter data, so the Analyst must say it can't assess it (or that SPY is the
  closest asset we have, unhedged), never invent numbers. Adding XSP = new public data to document (source, licence).
- **`dh.data.price_panel` builds the calendar from the whole universe, then selects the tickers.** Before, the calendar
  depended on which tickers were loaded (SPY alone 1254 rows, with the universe 1304), so Portfolio's
  `strategy_stats(w)` and the Critic's `portfolio_stats(w)` could differ slightly and fail G12. Now identical.

**Why:** agents call tools with whatever the client said; a crash or a 15k-character matrix breaks the run or the
context. One calendar keeps rule 1 (every agent quotes the same numbers) true across tool calls.

**Limits:** `goal_check` uses 1000 scenarios (≈0.4 s) to stay fast as a tool; `goal_outlook` (2000) for the main run.

**Added (Sun Nov 15):** a 7th tool, `required_return` — the yearly return a goal needs, next to cash (ZST.TO, last 12
months) and the Bank of Canada policy rate; a calculation, not a forecast.

**Added (Sat Nov 14, for the Portfolio's C2 geography check):** every asset carries `country` = country of listing
(TSX → Canada, NYSE/NASDAQ/Cboe → United States, crypto → Global), in `asset_summary`, `list_assets`, `asset_facts`;
`market.countries(tickers)` works without the CSVs. For an ETF it is where it is listed, not its holdings' countries.

## 16. Market-data charts: data function + Altair chart, built from the trace's numbers (Sat Nov 14, Joud, `lane/market-data`)

**Decision:** `src/dh/agents/market_charts.py` (deterministic, no LLM) gives five charts, each as `*_data()` (tidy
DataFrame) + `*_chart()` (Altair, which ships with Streamlit; Will shows them with `st.altair_chart`):
growth of each strategy with the 2022 sell-off shaded; range of final values (`risk_only` vs `replay`, invested and
target lines); correlation heatmap; risk vs return of the 31 assets with the historical frontier; 2022 return per asset.
`experiments/data/export_charts.py` writes PNG + HTML for the video and one-pager into `experiments/data/figures/`
(gitignored; regenerate from the CSVs).

**Why:** the chart shows exactly the numbers the trace and the Explainer quote (tested: same drawdown, same p50), so
nothing on screen contradicts the text. The frontier is drawn, not used to build strategies (#1); its points are
recomputed with `dh.metrics` (CAGR, same vol) so it sits on the same axes as the assets.

**Limits:** the export script's strategies are illustrative until the Portfolio agent's output replaces them. The
frontier is hindsight on one 5-year window. PNG export needs `vl-convert-python` (dev extra).

## 17. The stocks/bonds split is computed from the client and the data, not from a table (Sat Nov 14, Will)

**Decision:** for each strategy, the split (growth vs defensive) sits between two bounds the client sets:

- **Risk ceiling (the most growth they can take):** test growth shares from 0% to 100% in 5% steps on the strategy's
  own baskets, on 2021–2026 data (2022 included). The ceiling is the largest share whose worst historical drop stays
  within the client's **loss limit** = the smaller of
  - **tolerance:** the drop they said they'd accept (`max_loss_pct`);
  - **capacity:** what they can afford to lose, in dollars, as a share of capital (capital minus money needed within
    3 years minus their emergency-fund gap). The exact formula is an assumption, written in `profiler.py`.
- **Goal floor (the least growth needed):** from capital, contributions, target amount and horizon, the yearly return
  the goal requires; compared with ultra-short bonds (ZST) today. If bonds alone reach it, the floor is 0%. Otherwise
  the floor is the smallest growth share with a reasonable chance at the target (`goal_outlook`, "risk only" view first,
  #13). Optional: no target amount → no floor.
- **Liquidity floor (hard):** money needed within 3 years stays defensive.
- **Conflict (floor > ceiling):** the system says so ("your goal needs about X% in stocks; the loss you accept allows
  at most Y%") and offers the options: longer horizon, lower target, more contributions, or accepting more risk.
- **Strategies are defined by what they hold** (e.g. broad core, income/dividends, growth tilt), each with its own
  growth and defensive baskets; each strategy's split is computed with its own baskets. A more volatile growth basket
  gets a smaller share for the same loss limit. Up to 3 strategies, each shown at its ceiling, with floor and outlook.
- **Risk levels stay** as the client-facing label, for the diversification caps (one company, crypto, satellite) and as
  a Guardian safety net (computed split above the level's broad maximum → flag). The level → split table is dropped.

**Why:** the workshop's framing ("objective before product", "the investor sets the limits", "return, risk and horizon
are inseparable"); brief p.17 (explanations faithful to data: "55% because more would have lost over 15% in 2022, your
limit" vs "70/30 because you're level 3"); data is 20% of the grade and now decides the split; a second, deeper
pushback (goal vs risk) that Canadian KYC expects (tell clients when expectations don't fit their profile).

**Limits:** one crash in the window (2022): "how it behaved in 2021–2026, not a guarantee"; show the "risk only" goal
view. Capacity in dollars and "reasonable chance" (e.g. 50%) are assumptions. Changes G6 (liquidity floor + safety net)
and G7 (client's own loss limit); about half of the 16 scenarios need new expected values.

## 18. Diversification: five measured dimensions, rules C3/C4/C6, look-through reused (Sat Nov 14, Joud, `lane/portfolio`)

**Decision:** `src/dh/agents/diversification.py` (deterministic, no LLM) measures each strategy on five dimensions:
asset classes (equity, bonds, gold, crypto), companies **through the ETFs** (Will's `dh.metrics.look_through` on the
issuer holdings, #6: largest company, top 5, effective number), sectors through the ETFs, currency (CAD/USD), and
correlation (diversification ratio = Σ wᵢσᵢ / σₚ, weighted average correlation, near-duplicate pairs, ETF overlap via
`dh.metrics.overlap`). The Portfolio enforces three rules (team assumptions):
- **C3** no sector above 40% of the portfolio, counted through the ETFs (Amira: "not exclusively technology");
- **C6** never two holdings correlated at 0.95 or more (SPY/ESGV 0.99 = the same bet twice);
- **C4** at least 2 asset classes of at least 1% each (a 60/40 passes; 100% equity does not).

**Why:** the brief asks every persona's solution to "maintain a logic of diversification and be able to explain its
choices"; volatility alone doesn't show it. Each dimension is a number the Explainer can quote and the Critic can check.

**Limits:** ETFs without holdings data stay as one block, so C3 is a **lower bound** for them and the check says so
(`look_through_coverage`); today only SPY's holdings are loaded. Holdings are a snapshot, used for exposure, never to
rebuild past returns. Thresholds 40% / 0.95 / 2 are ours, to check on the persona strategies.

## 19. Loss limit, defensive floor and goal floor: the formulas #17 left as assumptions (Sat Nov 14, Will, `lane/portfolio`)

**Decision (`profiler.py`, `rules.py`, `portfolio.py`):**
- **Loss limit** = min(tolerance: `max_loss_pct`/100, capacity: the `max_drawdown` of the client's **capacity** level in
  `RISK_LEVELS`). Shown in $ (`capital × loss_limit`), with which side set it (`loss_limit_source`). G7 reads it.
- **Defensive floor** = max(money needed within 3 years `withdrawal_share_3y`, **5% for everyone**
  (`SAFETY_MIN_DEFENSIVE`)). The level's own `min_defensive` (75/50/30/15/5%) is **no longer used**: the loss limit
  does that job with data. G6 reads the new floor. A 100%-growth strategy is still refused.
- **Goal floor** = smallest growth share (5% grid) whose risk-only `goal_outlook` gives ≥ 50% chance at the target
  (`GOAL_MIN_PROB`); none without a target amount; conflict if it doesn't exist or is above the ceiling.
- **Strategies** (block A): broad core, income/dividends (knowledge ≥ 3), growth tilt (interest in ai/tech/crypto,
  risk level ≥ 3, knowledge ≥ 3). ESG interest or fossil-fuel exclusion swaps SPY → ESGV. Loss limit ≤ 10% → short-
  term-heavy defensive basket (ZST 60%, #13). Single names trimmed so direct + through-ETF weight ≤ the cap (P5);
  crypto capped. Each strategy sits at its ceiling; the curve 0–100% is kept for the chart.

**Why:** capacity has no natural "% loss" without a model of the client's whole balance sheet; reusing the capacity
level's drawdown keeps it rule-based and explainable, and it's already validated on 2021–2026 (#13). A uniform 5%
safety floor avoids bringing back a per-level split table through G6.

**Limits:** the capacity side still depends on the level table's drawdowns (team assumption, #5/#13). 50% is a
convention. Tests run `goal_outlook` with fewer paths (100/200) for speed; the real run uses 500/2000.



## 20. Portfolio checks C-F: one shape, thresholds, reused by the Guardian (Sat Nov 14, Joud, `portfolio/checks`)

**Decision:** `src/dh/agents/checks.py` (deterministic, no LLM) runs 17 checks per strategy, all returning
`{check, value, limit, status, reason, source}`. They are stored in `strategies[i]["checks"]`, printed by
`python -m dh propose`, and reused by the Guardian, so each rule has one implementation.

**Blocks (✘):**
- **C1** company cap, through the ETFs.
- **C3** a sector above 40% (#18).
- **C3b** the client's job sector above **15%** (`profile.employment_sector`).
- **C4** fewer than 2 asset classes.
- **C6** two holdings correlated at 0.95 or more (#18).
- **D2** worst drop above the loss limit, in % and in $.
- **F2** growth above the horizon cap (#22), **F3** defensive below the withdrawals, **F4** a beginner holding a
  single stock or crypto, **F6** an excluded asset held directly.

**Disclosed (⚠):**
- **C2** one country above **70%** of the equities (holdings' countries where the issuer file has them, otherwise
  the country of listing).
- **C3** a sector above **30%**.
- **C5** fewer than **8** effective holdings (1/Σw² through the ETFs; an ETF without holdings data counts as 100
  equal lines).
- **C6** a pair correlated above **0.85**, or two ETFs sharing more than **50%** of their holdings.
- **D1** worst drop above **80%** of the loss the client said they'd accept.
- **D3** worst 12 months beyond the loss limit.
- **E** below a 50% chance of reaching the target (risk-only view).
- **F1** an income objective with less than 50% in bonds or dividend payers, **F5** an ESG interest while holding
  SPY or a fossil-fuel name, **F6** an excluded asset held through an ETF.

**Guardian:** **G14** geography (C2), **G15** sector and job sector (C3, C3b), **G16** concentration (C5) and **G17**
drawdown in $ (D2) call `checks.py`.

**Portfolio:** on a C6 ✘ it merges the duplicate into the larger holding; on a C3 ✘ it moves the excess from that
sector's single stocks to the broad core ETF. The change is undone if it would break the loss limit, and it is noted
in `adjustments`.

**Why:** the brief asks every persona's solution to keep "a logic of diversification" and to explain its choices.
One shape lets the trace, the Explainer and the Critic quote any check the same way. The ✘/⚠ split follows
system-design: what breaks a client constraint blocks, what is a judgment call is disclosed.

**Results on the personas (data 2021-2026):**
- No ✘ anywhere.
- ⚠ C2 on the "Income / dividends" strategies (78–80% Canadian equities, by design).
- Amira's "Growth tilt" gets ⚠ C2 (100% U.S.), ⚠ C6 (QQQ/SPY 0.95) and ⚠ D1 (worst drop 33% vs her 40%).

**Changes to existing tests:**
- Scenario `ROBERT_OK` splits its 15% equities Canada/U.S. (XIU 5, SPY 5, RY 5). All-Canadian equities would trip
  G14.
- 16/16 scenarios still pass.

**Limits:**
- Thresholds are team assumptions, **fixed for every client**. C2, C3, C3b, C4, C5, C6, D1's 80% and E's 50%
  don't move with the client's situation; making them do so is noted for Will in `notes/branches/portfolio-checks.md`.
- Holdings data covers SPY only, and SPY's file has no sector or country. Sector and country are therefore lower
  bounds, and the reasons say so.
- "Country" for an ETF without holdings data is where it is listed.

**Fix (Sun Nov 15, Joud):** C1 now compares each company with **its own** cap (`limits["company_caps"]`, #24), like
G4. It used the largest cap (`max_single`), so with 10% TSLA for Mateo C1 said ✔ (vs 12.3%) while G4 said ✘ (vs 8.8%).
Test `test_c1_uses_each_company_cap_and_agrees_with_g4`.

## 21. Protected strategy (CPPI): tested, then SET ASIDE (Sat Nov 14, Joud, `lane/market-data`)

(#18–#20 are taken by Will's Portfolio branches.)

**Decision:** no CPPI in the product. We stick to what the judges ask for: a simulated portfolio / decision-support
tool that explains itself. The brief says "sophistication and the number of agents are not ends in themselves"
(p.17), no transactions, simulation only. A CPPI is a dynamic rule that implies monthly rebalancing, i.e. an
ongoing management service, which is outside that frame and can't be shown with a dataset that ends on 2026-11-12.

**What was tested before setting it aside** (code in git history, commits `32d317a`, `70d7eee`; numbers in
`results.csv`, experiment `cppi-thresholds`):
- **Method:** hypothetical clients, never the personas. The test was out of sample: 2 halves × CAD/local ×
  risk-only/replay.
- **Loss limit:** a CPPI whose floor follows the peak kept it in all variants, breaking it at most 0.3% of the time.
  A static mix tuned on one period broke it in 15% of cases on another (median).
- **Dated project:** the reliable band was a PV(minimum)/capital of 70–85%.
- **Goal/risk conflict:** no reliable ratio.
- **The multiplier m:** it depended mostly on the period, so it is easy to overfit.

**What we keep from it:** static strategies tuned on one calm window can break out of sample (useful for Will's split
ceiling, see the Robert 80/20 note in `notes/branches/lane-market-data.md`).

## 22. Horizon directive: the sooner the money is needed, the less growth (Sat Nov 14, Joud, on Will's `lane/portfolio`)

**Decision:** a growth cap estimated per client from their own horizon (system-design A2), linear between two anchors
(team assumption, not fitted on any persona): **0% growth up to 2 years, 100% allowed from 15 years**:
3 y → 8%, 4 y → 15%, 5 y → 23%, 8 y → 46%, 10 y → 62%. `rules.horizon_max_growth(years)`.
The Profiler's defensive floor becomes the strictest of three: withdrawals within 3 years (#17), the horizon
directive, the 5% safety net. Its reason says which one binds ("horizon 4 years → at most 15% in stocks"). The
Portfolio's ceiling (1 − floor) and the Guardian's G6 apply it with no other change.

**Why:** the data-only ceiling (#17) gave Robert (59, 4 years, "preserve capital") 80% stocks. The 2021-2026 window
holds one bear market, and it was mild in CAD (100% XIU/SPY lost only −16% at worst), so the data alone barely
constrains. A short horizon can't wait for a recovery, whatever one calm window says. Results with the directive:
- **Robert:** 15/85, max drawdown −8.6% on 2021-2026.
- **Mateo:** 60/40.
- **Amira:** 95/5 (the directive doesn't bind at 15 years).

**Scenarios updated (same commit):**
- `ROBERT_OK` now holds 85% defensive (it held 55%) and its text quotes 85% and a 6% worst drop.
- `big-withdrawal` horizon 6 → 8 years, so its 60% withdrawals still bind as intended.
- 16/16 scenarios still pass.

**Limits:** the anchors 2 and 15 years are a directive, not a measurement; one five-year window can't calibrate
long horizons. Change them in `rules.py` (H_NO_GROWTH, H_FULL_GROWTH), with team agreement.

## 23. Explainer = Strands agent on Bedrock (Claude Opus 5.5), with a self-check tool, a template fallback and a demo cache (Sat Nov 14, Will, `agents/explainer`)

(#20 is reserved for the `portfolio/checks` thresholds.)

**Decision (`src/dh/agents/explainer.py`):**
- **Input:** only a `facts` dict built from the strategies, the limits with their written reasons, and the profile;
  every number is pre-formatted as the text should show it (e.g. "-12.3%"). The agent may quote nothing else.
- **Agent:** Strands `Agent` + `BedrockModel` (model id from `BEDROCK_EXPLAINER_MODEL_ID`, copied from the Bedrock
  console, us-east-1; no `temperature`, which Opus 5.5 rejects). One tool, `check_text`, runs the Guardian's
  G11–G13 on its draft; at most 3 calls, then it must answer.
- **Code enforces:** the final text is checked again (G11–G13 on all strategies at once). If it fails, or AWS/Strands
  errors, the deterministic template is used and the trace says why. The template passes G11–G13 by construction.
- **Caching:** answers keyed by a hash of (prompt version, model id, facts). Local cache `.cache/explainer/`
  (gitignored); **committed demo cache `cache/explainer/`** (`make explain P=robert SAVE=1`), replayed in mock mode, so
  the demo and Friday's pitch work without AWS.
- **Rule 5 exception:** Strands calls Bedrock itself, not through `dh.llm.ask`; caching and the mock live in
  `explainer.py` instead. `pipeline.py` is untouched: `explainer.add_to_trace(res, profile)` appends the Explainer and
  Guardian steps to a pipeline result.

**Why:** a writer that checks its own draft with the same rules the Guardian uses is real, visible agency (#14) without
giving up "code enforces"; the template guarantees a valid answer when the model or AWS isn't there.

**Limits:** G12 matches values, not labels (a made-up 9.7% passes if a real 10% weight exists): keep facts small.
Text varies between runs; the cache fixes the demo version. The cache key changes with any number, so re-save after
data or rule changes, before the AWS account closes.

## 24. Caps on one company and on crypto come from the client and the data, not from a table (Sat Nov 14, Will, `agents/explainer`)

**Decision:** the per-level caps (`max_single` 5–15%, `max_crypto` 0–10% in `RISK_LEVELS`) are no longer used.
Each company gets its own cap, computed by the Profiler (`rules.company_cap`, `profiler.derive_limits`):
- **loss budget:** if the company repeated its own worst 2021–2026 drop (CAD, `market.asset_summary`), that alone may
  cost at most **¼ of the client's loss limit** → cap = ¼ × loss limit / |worst drop|;
- **spread:** no company above **⅕ of what the client can hold in stocks** (1 − defensive floor, so the horizon
  directive #22 and liquidity feed in);
- cap = the stricter of the two, counted through ETFs (G4, Portfolio P5). Crypto (BTC + ETH) is one bet, same rule with
  the worse of the two drops. Knowledge ≤ 2 halves the budget and sets crypto to 0; a crypto exclusion sets it to 0.
- No market data → assume every asset can lose 100% (stricter, never looser).

Results on the real data: Robert ≈ 3.1% for every company (his ~15% stock room binds), TSLA request explained as
"worst drop −70.9%; at 25% that alone would be −17.7%, more than your whole 15% loss limit; fits up to 3.1%".
Mateo: TSLA 8.8%, NVDA 9.8%, others 12.3%, crypto 8.1%. Amira: TSLA 14.1%, NVDA 15.8%, others 19.0%, crypto 13.0%.

**Wording (Explainer prompt v2):** a request that doesn't fit is never "refused": the text gives the asset's worst drop,
what that weight alone would have cost, how it compares with the client's own limit, and how much fits; the client
decides. Portfolio notes mention ETFs only when an ETF really holds part of the company; left-out assets say why
("you excluded fossil fuels").

**Why:** Will's direction: no fixed rules; limits that move with the data and the profile. A flat 8% treated TSLA
(−71%) and JNJ (−16%) the same and couldn't be explained beyond "it's the rule".

**Limits:** ¼ and ⅕ are the two remaining assumptions (explainable diversification principles, in `rules.py`); one
5-year window decides the worst drops. Tests use a fixed copy of today's drops (`scenarios.DROPS_DEMO`,
`tests/conftest.py`) so they stay offline.

## 25. Every run's trace is saved to Amazon S3, with a local fallback (Sun Nov 15, Will, `aws/s3-traces`)

**Decision (`src/dh/tracestore.py`):** `save_run(res, profile, persona)` writes one JSON per run to
`s3://$S3_BUCKET/traces/<date>/<run_id>.json`: the client's facts, the limits and their reasons, the strategies, the
Guardian's checks, the Explainer's text (with its source and G11–G13) and every hand-off of the trace. Never the
model's raw reasoning (#9). The run's trace gets a last step, "Trace store → Amazon S3", with the location.
- **Fallback:** S3_BUCKET unset or any AWS error (expired session token, offline, after the account closes) → the
  same JSON in `outputs/traces/`, and the trace step says why. The demo never breaks.
- **Backup:** `make backup` syncs `s3://$S3_BUCKET/traces` into `outputs/traces/` and commits it with
  `cache/explainer/`, so the run evidence survives the AWS teardown (fictional profiles, no secrets).
- `python -m dh explain <persona>` saves by default (`--no-store` to skip).

**Why:** AWS must do real, visible work in the flow (slide 7, qualifying). S3 holds the evidence behind every answer,
which is also what makes the system auditable: the jury can open any run.

**Limits:** no retention policy or encryption settings beyond the bucket's defaults (the event account is temporary).


## 26. Crypto only if the client asks AND the profile allows it AND the model suggests it (Sun Nov 15, Will, `claude/jolly-gauss-vrakn3`)

**Decision:** the Growth tilt no longer holds BTC/ETH by default. `portfolio.crypto_decision` keeps crypto only if:
1. **asked**: `crypto` is in the client's interests, or they requested a crypto position (`portfolio.asked_crypto`);
2. **allowed**: the Profiler gave a crypto cap > 0 (not a beginner, not excluded; decision #24);
3. **model**: the computed growth ceiling (largest growth share whose 2021-2026 worst drop ≤ the client's own loss
   limit, decision #17) is at least as high with crypto as without. If crypto costs stock room, it is left out.

Each outcome writes one line in the strategy's `adjustments` (trace), with the two ceilings. A requested crypto
position also counts as a growth interest in `offered()`.

**Why:** an AI-curious client who never mentioned crypto shouldn't find it in their proposal; and even when asked,
crypto has to earn its place by the same numbers as everything else, not be added because the template had it.

**Limits:** the model test only compares ceilings (worst drop), not returns: by design, no return forecast decides.

## 27. Strict G12: the Explainer writes ids, never numbers; exact match everywhere else (Sun Nov 15, Will, `guardian/g12-strict`)

**Problem (measured):** G12 accepted a % if it was within ±0.5 point of any computed number. With ~30–90 known numbers,
a random invented % slipped through 23–36% of the time (the "9.7% passes because a real 10% weight exists" effect).

**Decision:**
- **Explainer (agent path):** every % and $ value in its facts is replaced by an id (`{n7}`); a NUMBERS table gives
  the values so it can compare them. It writes ids; code fills in the values (`explainer.render`). Any number it types
  itself, or any id that doesn't exist, is rejected (`strict_problems`) and the template is used instead, with the
  reason in the trace. **Invented numbers: 0% can pass, by construction.**
- **G12 on the final client text** (template, cached texts): every % / $ must be exactly one of the facts' values
  (no tolerance). Random numbers: ~3% (one decimal) to ~6% (whole numbers) happen to equal a real value.
- **Guardian's general G12** (hand-written texts, scenarios): tolerance 0.05 pt instead of 0.5 → ~4% instead of ~36%.
- **v4 (same day): no digit at all.** Every number in the facts (%, $, ages, years, dates, levels) is an id; any digit
  the agent types, any spelled-out amount ("eight percent", "a quarter of a dollar") or unknown id → rejected, template
  used. "8.6 percent", "60,000 dollars", "CAD 60,000" are recognised as numbers in the final-text check too.
- Prompt v4; the cache stores the raw text with ids and renders it on replay.

**Why:** "every number traced" is the core of the explainability claim; one in four is not a guarantee.

**Limits:** an id can still be put next to the wrong label (e.g. one strategy's worst drop quoted for the other);
that's a wording error, not an invented number. Comparisons in words ("twice as volatile", "much smaller") aren't
numbers and aren't checked. The demo cache must be regenerated (`make explain P=… SAVE=1`):
v2 texts no longer replay. Branch `portfolio/requests` must add its side-by-side numbers to `explainer.facts` (not
to G12's tolerance list) if the Explainer is to quote them.
## 28. Request side by side, selection and pros/cons (Sat Nov 15, Joud, `portfolio/requests`)

**Decision:** blocks G and H of layer 3, deterministic, in `src/dh/agents/requests.py`.

**G, the client's request side by side** (`compare`), laid on "Broad core" (always simple), otherwise on the first
strategy:
- **as asked:** the requested weights exactly. Room is made in the growth part first and in the defensive part only
  if the growth part is too small (Robert: 25% TSLA against 15% in stocks).
- **fits your limits:** each requested asset at what the Profiler says fits (#24), taken from the growth part only,
  so the defensive floor and the horizon cap still hold. Excluded assets and assets without data have no "fits"
  version, and the reason says why.
- Both versions run the same C-F checks (#20) and the Guardian. They show the real weight through the ETFs, the
  worst drop in % and in $, against the loss limit, and every failing check. The client decides; the wording never
  says "refused" (#24).

**H, selection and pros/cons:**
- A strategy is dropped if the Guardian **or** any C-F check gives ✘. The trace says which checks dropped it (P10).
- Pros and cons are filled from templates with the strategy's own `stats` and `checks`, never by the LLM:
  - comparisons, made only when one strategy strictly beats the others (no "best of 2" on a tie): smallest or
    largest worst drop, highest return in 2021-2026, best 2022, most spread out;
  - the worst drop against the loss limit;
  - the chance of a loss (risk-only view);
  - every ⚠ check, quoted.
- G12 now knows the C-F check numbers and the side-by-side numbers, so the Explainer may quote them.

**Results on the starter data** (logged in `results.csv`, experiments `proposal-*` and `request-*`,
`experiments/data/persona_numbers.py`):
- **Robert, 25% TSLA as asked:** worst drop −26.5%, i.e. 106,121 $ against his 60,000 $ limit; 9 checks fail (7 since #46: C1, D2, F2, G4, G6, G7, G9; D1 and G17 no longer fail separately)
  (C1, D1, D2, F2, G4, G6, G7, G9, G17).
- **Robert, TSLA at 3.1% (fits):** worst drop −9.6%, i.e. 38,241 $; nothing fails.
- **Amira, NVDA 20%:** fits at 15.8%.
- **Mateo, XOM** (an excluded fossil-fuel name): no "fits" version, the reason is his exclusion.

**Limits:**
- The comparison is laid on one strategy only.
- The 2021-2026 replay can still show the "as asked" version ending higher. The chart says so, and it ends higher
  with a drop beyond the client's limit.


## 29. Free-text extractor = Strands agent on Bedrock; code checks every field and every number (Sun Nov 15, Will)

**Decision (`src/dh/agents/extractor.py`):**
- **Agent:** Strands `Agent` + `BedrockModel` (Claude Opus 5.5, `BEDROCK_EXTRACTOR_MODEL_ID` else `BEDROCK_MODEL_ID`)
  reads the client's own words and fills only the `profile` fields they stated (contract §0/§1). One tool,
  `check_profile`, runs the code checks below on its draft (≤ 3 calls); it answers with JSON. It never scores anything:
  the Profiler (rules) sets the limits (#4).
- **Code enforces:** schema (types, ranges, contract enums), ticker aliases (Tesla → TSLA; unknown tickers such as XSP
  kept so the Profiler can say it has no data), and **grounding: every number in the profile must be written in the
  client's text** (digits, "400k", "400,000", "four years"). Anything else is dropped, written in `notes`, and asked.
- **Follow-up questions** are fixed text per missing KYC essential (`QUESTIONS`), shown as a form in the app; the
  answers are a trace step of their own ("Client → Profiler"). Ask, don't guess (G1).
- **Offline:** committed cache `cache/extractor/` (`make extract T="..." SAVE=1`), else a conservative rule-based parser,
  which is also the fallback when the agent or AWS fails (the note says why). Rule 5 exception as for #23.

**Why:** free text is the natural intake and shows agency (the agent decides what it can fill), but an LLM must not
make up a client's capital or loss limit: the grounding check makes "every number comes from somewhere" true at the
input as well as at the output (G12).

**Limits:** grounding checks that the number appears in the text, not that it is attached to the right field (same limit
as G12). The rule parser is English-only and pattern-based: it misses things and then asks. Same rounding note: the
Portfolio now steps capped lines down after rounding to 0.5% (found while testing the app: a 5.8% crypto cap became 6.0%
and the Guardian dropped the strategy).
## 30. Critic: a Strands agent that investigates, objects with evidence, and gets one recomputed fix per strategy (Sun Nov 15, Will, `claude/jolly-gauss-vrakn3`)

**Decision:** `src/dh/agents/critic.py`, run by `pipeline.run` after the Guardian has passed the strategies.
- **Agent:** Strands on Amazon Bedrock, Opus 5.5 by default (`BEDROCK_CRITIC_MODEL_ID` to switch to a faster model
  without code change). 9 deterministic tools: Joud's 6 (`market.AGENT_TOOLS`) + `look_through`,
  `strategy_checks`, `limit_reason`. At most 6 calls, at most 3 objections, guide of 6 sceptic questions.
- **Code enforces:** an objection is dropped if it cites no call it made or quotes a number no cited result
  contains. A fix comes from a menu (merge, trim, shift, disclose) and only TIGHTENS an input of the calculation:
  merge changes the growth basket, trim lowers one company's cap, shift raises the defensive floor. Then
  `portfolio.assemble` reruns the **whole** calculation (split search, build, diversification fixes, stats, goal
  outlook, checks C-F), the Guardian re-checks against the client's original limits, and if it fails or the worst
  drop breaks the loss limit the original stays (`kept, justified`). One fix per strategy, one round.
- **Shown in the trace only** (Critic → Portfolio with every tool call; Portfolio → Guardian for each recompute).
  Objections not fixed go to the strategy's `cons`.
- **Offline:** a deterministic mock critic makes the same kind of calls; it only merges a real same-bet pair
  (correlation ≥ 0.85) and discloses warnings, never shifts (strategies sit at their ceiling by design, #17).
  Bedrock reviews are cached by facts hash; `make explain P=… SAVE=1` commits them to `cache/critic/`.

**Why:** the brief rewards a relevant agentic approach and faithful explanations. A sceptic that checks before
speaking, and whose changes are recomputed and re-checked by code, is visible agency without letting the LLM set a
number or a limit (#2, #9, #14).

**Limits:** the number check matches values, not their labels (same limit as G12). A revision changes the
strategies, so the Explainer's demo cache must be re-saved after the Critic's.

## 35. Analyst: follow-up questions answered by tools that re-run the pipeline (Sun Nov 15, Joud, `lane/market-data`)

(#31–#34 are on Will's `claude/jolly-lovelace-yswcsi`.)

**Decision:** `src/dh/agents/analyst.py`, the last agent of the architecture (#14). It answers the client's follow-up
questions ("what if I put 10% in NVDA?", "what if my horizon were 8 years?", "why so few stocks?").

**How it works:**
- It is a Strands agent on Bedrock. It decides which tools to call, with a budget of 5 calls.
- Its tools are Joud's market tools (#15, including `required_return`) and the Critic's views on the run.
- It also has two what-ifs that **re-run the real pipeline** (Profiler → Portfolio → checks C-F → Guardian):
  - `what_if_position(ticker, weight)`: "as asked" vs "fits your limits", the same comparison as #25;
  - `what_if_profile(field, value)`: limits and growth shares, before and after.

**What code enforces, as for the Critic:**
- Every number in the answer must appear in a tool result the answer cites. Thousands separators are read as one
  number.
- No buy/sell advice, no forecast wording.
- The simulation disclaimer is added by code.
- If a rule is broken, the answer is replaced by the deterministic analyst, and `note` says why.
- **Only a valid answer is ever cached.**
- The modes are the same as the Critic's and the Explainer's: committed demo cache → local cache → Bedrock. `mock`
  (the default) is a deterministic analyst that reads the question with simple patterns and writes the answer from
  the tool results.

**Why:** the brief asks for an agentic solution useful to the client. A follow-up is where agency adds value (choosing
what to check), and re-running the pipeline keeps "code enforces" true: the agent never computes a number.

**Examples (starter data, mock analyst):**
- **Robert, "25% in TSLA?"** → worst drop −26.5%, about 106,121 $ against his 60,000 $ limit; 9 rules fail (7 since #46); the version
  that fits holds 3.1%.
- **Robert, "horizon 10 years?"** → stocks 15% → 60%.
- **Robert, "lose 25%?"** → nothing moves, and the answer says why: his situation caps the loss limit, and his horizon
  caps the stocks.
- **"XSP?"** → "no data".

**Improved (Sun Nov 15, analyst-v2):**
- **Names, not only tickers:** company and fund names ("Tesla", "Banque Royale", "bitcoin", "S&P 500", "l'or") are
  read through an alias table, plus the universe's official names when the CSVs are there.
- **Several requests in one question are checked together:** "10% NVDA *and* an 8-year horizon" calls
  `what_if_profile`, then `what_if_position` with `profile_changes`; several positions go in one call (`also`).
- **More questions:** the return a goal needs (`required_return`, target read from "450 000 $"), an asset's past risk,
  "same bet?" (correlation), the 2022 sell-off (`stress_test`), monthly contributions and capital, and advice
  questions ("should I buy?" → "I don't say buy or sell" + the asset's past facts).
- **The answer comes in the question's language** (French or English), with the disclaimer in that language.
- **Checks added by code:**
  - the advice/forecast filter covers French ("vous devriez acheter", "achetez", "va rapporter", "garanti", …);
  - a count ("9 rules", "2 strategies") must match a list of **that kind** in the cited results (rules, strategies
    or assets), not just any list;
  - a year must be inside the data (2021–2026) or in the results;
  - a number written next to an asset or a strategy must belong to **that** asset or strategy, or be client-wide;
  - French number formats (13,7 %, 106 121 $) are read correctly;
  - if even the deterministic answer breaks a rule, only the help text (no numbers) is shown.
- **Result on 15 test questions** (3 personas, both languages): all valid.

**Limits (still):**
- The attribution check works sentence by sentence: a sentence naming two assets accepts a number from either, and
  "before" vs "after" confusions are not caught. A wrong claim with no number in it is not caught.
- The Profiler's reasons are quoted in English inside French answers.
- The advice filter is a list of phrases: it catches the common ones, not every way of saying it.
- The deterministic analyst reads questions with patterns. A percentage is matched with the nearest asset within 40
  characters; unusual phrasing gets the help text, while the Bedrock agent reads anything.
- A Bedrock run is not tested here (no `.env`).
- **In the app since Sun:** a "Follow-up (Analyst)" tab: example questions, a free question, the answer with
  its code-check status and every tool call; follow-ups also appear at the end of the Trace tab (kept in the session,
  not in the cached run).
## 31. Longer histories: rebuild from 2004; missing history is missing, never 0% (Sun Nov 15, Will, after the audit)

**Problem (audit §3.3, §4):** 2021–2026 holds one mild bear market; the worst-drop test never binds for Mateo or Amira
and every measured risk comes from 2022. **Decision (Will):** rebuild the same 31 assets over a longer window, on Will's
laptop (this cloud session can't reach Yahoo, FRED or the Bank of Canada).
- `scripts/build_long_data.py` / `make data-long [START=…]`: runs the organizers' `build_dataset.py` **unchanged** with
  an earlier START (default 2004-11-18, GLD's first day) and USD/CAD from FRED DEXCAUS before the Bank of Canada series
  starts. Writes `data/raw/` (gitignored) + `BUILD_INFO.txt`.
- **`metrics.portfolio_returns` keeps only days on which every held asset has a return** (was `fillna(0)`: a young asset
  looked flat, hiding risk). Identical on the starter pack (tested).
- **Stand-ins only before an asset's first price** (`harness.toml [data.proxies]`): ZST.TO ← Bank of Canada overnight
  rate (V39079) accrued daily, ESGV ← SPY. Listed in `market_facts.assumptions` and the Explainer's data line.
  Single stocks and crypto get none: a strategy holding ETH starts in 2017.
- **FX is carried forward only** (no back-fill): a USD price before the first FX quote has no CAD value.
- Stress windows 2007-10-09 → 2009-03-09 and 2020-02-19 → 2020-03-23 (S&P 500 peak to trough) reported as
  `stress_2008` / `stress_2020` (+ `_drawdown`) **only when covered** (no key otherwise).
- Every "2021-2026" in texts now comes from the data (`data.period_label`; a company's worst drop names its own window).

**Limits:** the window is still chosen by us; survivorship bias stays (the 31 names are 2026's); company caps get
stricter with 2008 in the window; the cached Explainer texts must be re-saved after the rebuild (facts change).

## 32. The up-to-3 strategies are 3 risk levels (Sun Nov 15, Will, audit S3)

**Problem (audit P5):** each persona's strategies all had the same stock share (correlation 0.79–0.885): flavours, not
the risk levels the log and the video promised. **Decision (Will, option a):** level 1 = the most growth the client's
limits allow; levels 2 and 3 = 10 and 20 points more prudent (`portfolio.levels`, `LEVELS`). Each level is a full
`assemble` with a higher defensive floor (`level_limits`), so it can only be safer; the client's preferred flavour
(growth tilt > broad core > income) takes level 1. Levels < 5 points apart or below 5% growth are dropped. Strategies
carry `flavour` and `level`; `key` stays unique (the Critic's id); the Critic's fixes keep the level.

## 33. Each split says which constraint set it (Sun Nov 15, Will, audit S2 option a)

**Problem (audit P3/P4):** the pitch said "the data decides the split", but the horizon rule (#22) and the 5% safety
net decided for all three personas, and the worst-drop test is validated on the data it was chosen on.
**Decision (Will):** say it. `split_search` returns `set_by` (worst_drop · horizon · liquidity · safety · level),
`set_by_text` and `data_ceiling` (what the worst-drop test alone would allow); the Profiler names the binding floor
(`min_defensive_source`, `min_defensive_why`, "the horizon rule, a judgment rule not a data result"). The trace, the
app, the Explainer facts and the deliverables quote it. **Next (after submission):** add a bootstrap condition,
P(drawdown > limit) ≤ 5%, as a fourth constraint (S2 option d).

## 34. Technical fixes from the audit (Sun Nov 15, Will; no fundamental assumption changed)

From `notes/audit-2026-11-15.md`, each pinned by `tests/test_audit_fixes.py`:
- **P6 G12 sees gains:** a number written as a gain ("+6%", "gained", "rose", "earned", "grew", "up") must match a
  computed value ≥ 0; "gained 8.6%" for a −8.6% drop now fails. Plain wording of a loss ("a drop of 8.6%") still passes.
- **P9 Sharpe against cash:** risk-free = ZST.TO's average return over the same data (`market.cash_rate`); ZST was 6.03.
- **P10 one implementation per rule:** `diversification.check` takes C3/C4 from `checks.py` (it said ✔ at 35% tech where
  C3 said ⚠); F2/F3 use G6's tolerance; one fossil list (`rules.EXCLUSIONS`), one dividend list (`rules.DIVIDEND_PAYERS`).
- **C1 per company:** each company against its own cap (#24), like G4 (was: largest company vs largest cap).
- **P11 one client:** the persona card shows the numbers the pipeline runs (brief: Robert "3-5" years; simulated: 4).
- **P8/P13 no noise pros:** no "highest return" (gaps not significant) and no "most spread out" (an artifact of the
  100-lines-per-ETF assumption).
- **P15:** the pipeline no longer edits the Profiler's `limits` in place.
- **P21:** crypto pairs use weekly correlations in C6 (UTC vs New York close).
- **P16:** `notes/results-status.md` says which `results.csv` rows are obsolete.

**Not changed:** P20 (CNQ's 1.021 factor on 2022-08-22): the starter README says it likely reflects a special
distribution; if so, the adjusted return is right. **To verify** on CNQ's investor-relations page before touching it.
P19 (unused toolkit functions) kept: nothing proves they're unused by notebooks or future tools.

## 36. A guided interface for any adult, on top of the same engine (Sun Nov 15, Joud, `interface`)

**Decision.** A second Streamlit app in `interface/` (`make ui`): questions step by step (only those that apply,
advanced ones folded), each answer checked before it reaches the engine with the engine's own limits
(`extractor.NUMBERS` / `ENUMS` / `LISTS`), results essentials-first, and a conversation with the Analyst. One service
layer is the only door to the engine and the only error boundary: a person sees a sentence (and a reference), the
traceback goes to `logs/interface.log`. The Analyst gets the conversation (`history`): the live agent sees the last 6
turns; offline, follow-ups reuse the last asset or share, concepts come from a written glossary, "explain my results"
goes through a read-only `results_overview` tool, so every number is still code-checked.

**Why.** The jury demo (`app/app.py`) shows the agents to experts; the brief also asks for usefulness to users. The
offline assistant is labelled "Offline: limited answers" and says when it doesn't understand: no simulated AI.

**Limits.** English only; offline understanding is pattern-based; not merged before Will agrees. Tests and the fixes
they led to: `interface/TESTING.md`.


## 37. Mean-variance optimisers: tested on branches, kept off the demo (Sun Nov 15, Will)

Joud built two (branch `interface`: min-variance inside the client's limits + Monte-Carlo frontier; branch
`optimisation-markowitz`: KYC-scored risk aversion A + tangent portfolio). Both pass their tests and merge cleanly.
**Not merged for the submission; #1 stands** (no optimiser; the frontier is a chart). Why, from Joud's own results
(`results.csv` on `optimisation-markowitz`, experiment `markowitz-check`): the optimal portfolio changes completely with
the window, out of sample the optimised weights did worse than equal weights, and without per-asset caps the weights
concentrate. The tech doc presents it as tested and set aside, like CPPI (#21). Revisit after Monday if wanted.
(The branches' own proposed #37/#38 become #38+ if merged later.)

## 40. From Markowitz, keep what describes risk; KYC bets as a cross-check (Sun Nov 15, Will, `claude/jolly-gauss-vrakn3`)

Follows #37 (optimisers kept off the demo: with historical average returns the "optimal" weights move with the
window and lost to equal weights out of sample). Two pieces of Joud's `optimisation-markowitz` work don't depend on
average returns, so they are used:

1. **Risk contributions** (`dh.metrics.risk_contributions`): each holding's share of the portfolio's variance,
   w_i·(Σw)_i / w'Σw, from the covariance only. A new Critic tool (`risk_contributions`, 11 tools now) answers
   "where do the swings come from?" ("10% of the money, 24% of the risk"), as evidence for a `trim` or `shift`,
   which code still recomputes and the Guardian re-checks (#30). The Critic's prompt is unchanged, so its committed
   demo cache stays valid; the tool describes itself to the agent.
2. **KYC bets** (`dh.kyc`, Joud's, copied unchanged from his branch): three 50/50 bets → certainty equivalents →
   risk aversion A = 2(m − CE)/σ². The Profiler compares A's band (bold < 2 → tolerance 4–5, average 2–4 → 3,
   cautious > 4 → 1–2) with the tolerance from the other answers. **Cross-check only**: when the bets are more
   cautious than the other answers, or the bets contradict each other, the trace flags it "to clarify with the
   client"; no limit changes. Plus one **expected-value question** built from the first bet ("+25% or −5% with equal
   chances: what do you expect on average?", right answer 10%): wrong → knowledge capped at 3. The three personas
   have fictional answers that agree with their stories, so their limits, and the demo caches, are unchanged.

**Why:** the brief rewards explaining results and assumptions and a Canadian-advisor KYC (conflicting answers →
clarify). Risk contributions explain a strategy without forecasting; two independent measures of tolerance that
must agree are a check a judge can follow; the EV question tests understanding rather than trusting the declared level.

**Why not let A set the limits:** A from three hypothetical bets is noisy, and willingness is already measured twice
(#4, #19). A flag that asks the client is the advisor's move; silently lowering a limit is not.

**Limits:** no screen asks the bets yet (personas carry example answers; the interface can add them, Joud's lane).
`metrics.py` is shared (rule 1): Joud to review `risk_contributions`.

## 41. More products (CAD/USD), profile-driven baskets, dividend coverage — research mode, off by default (Sun Nov 15, Joud, `produit_cadusa`)

Everything below runs only with `harness.toml [data] extra = ["cadusa"]` (`make data-products`, `make
data-fundamentals`). Default `extra = []`: the demo's baskets, checks, tool list, caches and numbers are unchanged
(tested in two processes: proposals, verdicts and checks identical).

1. **60 products listed in Canada or the U.S.** (`dh.product_catalogue`), chosen for the simplest integration: the
   starter's classes only, full 2021-2026 window, no futures/crypto/multi-asset funds, no near-duplicate of a starter
   asset, no fossil-fuel producer. rules.py adds them to its groups (derived from data: same sets on the starter).
2. **Baskets driven by the profile or by an existing check, never by a persona's name** (`portfolio.baskets`):
   ESG interest → XIU.TO replaced by XESG.TO (replace, never add: correlation 0.956, C6); horizon ≤ 5 years → XBB.TO
   replaced by XSB.TO (2022: −11.7% vs −4.0%, 2021-2026 worst drop −15.5% vs −6.1%); one country above 70% of the
   equities (C2 ⚠) → the smallest 5%-step share moved to XEF.TO/XEC.TO (3:1) that brings it to the limit. No cash
   product added: ZST.TO already plays that role (PSA.TO ≈ ZST.TO).
3. **Dividend coverage** (`dh.fundamentals`): status on the last 3 fiscal years together (one year misleads: BCE.TO
   32% of 2025 earnings, 107% over 3 years, cut in 2025); covered ≥ 1.25× earnings, thin 1–1.25×, not covered < 1×
   (a definition), loss; free-cash-flow shortfall added to the reason (not for banks/insurers); REITs "not
   measurable" without FFO. A team rule, never called a regulation.
4. **Income names must be covered**: a dividend payer stays in the income strategy only if its dividends are ≤ 80% of
   its last 3 years' earnings; ENB.TO (130%) is left out by the rule, with the reason in the trace. New check
   **F7** (⚠ only): a single company held whose dividend is not covered (earnings understate some businesses' cash,
   so it discloses, never blocks).

**Why:** usefulness to users (international diversification, ESG, short-horizon protection) and faithful explanations:
the system applies to its own picks the rigour it applies to Robert's Tesla request. **Limits:** one 5-year window;
XESG.TO and ESGV are ESG tilts, not fossil-free (look-through needs their holdings); statements are a snapshot (never
in a backtest). Numbers: `results.csv` experiments `cadusa-persona-strategies` (logged without the SPY holdings file: look-through
direct only, which affects C1, not the splits, worst drops or volatilities), `dividend-coverage`, `cadusa-evidence`.

**Extended (Sun Nov 15, same research mode):** dividends reach the rest of the architecture.
- Guardian **G19** (⚠ only, same implementation as F7; renumbered on risk integration): a single company held whose dividend is not covered. The rule
  exists only in research mode (the demo keeps 17 rules).
- **F1** (income objective) counts bonds, dividend payers covered on 3 years (`fundamentals.covered_payers`) and
  dividend ETFs (sub_class `factor_dividend`), instead of the fixed `DIVIDEND_PAYERS` list.
- **Explainer** facts carry each held company's dividend status and 3-year payout (numbers become ids, strict G12);
  the template writes one line per strategy. Default facts unchanged, so the demo cache keys are unchanged (checked).
- **Funds**: the reason gives the 12-month distribution yield and the years distributions were lower.
- The default mode stays off: turning it on needs `make warm` (Bedrock), `make log-personas` and the deliverables'
  numbers redone, so it is left for the finals.


## 42. Existing portfolio: review, labelled stand-ins, rebuild (Sun Nov 15, Joud, `portefeuille_existant`)

**Why.** BN workshop (slides 13-14): a decision starts from "what am I trying to improve?" in what the client already
holds. Its own example, XSP.TO, is not in the starter pack.

**Decision.**
- Third way to start: the client enters holdings one by one (ticker + $). `existing.review` runs them through the same
  C-F checks and Guardian as any strategy, writes a critique from those numbers, and rebuilds them into the first
  proposed strategy (#32) with the moves in $. No new optimiser (#1, #37).
- A fund we have no data for is measured with a **labelled stand-in** (`dh.standins`, 22 funds tracking the same or a
  close index) or listed "no data" and left out. Never silent. A fund with its own mix (ZEQT) is not mapped.
- CAD-hedged funds (XSP.TO, VSP.TO, ZUE.TO, XQQ.TO, ZQQ.TO): the source's USD return (USD/CAD move removed) + the
  overnight rate gap (Bank of Canada − fed funds).
- Checked against each fund's real prices (`scripts/validate_standins.py`, results.csv `standin-*`): unhedged within
  ±0.4 pt of the real worst drop; hedged ones understate it by 1.0-3.2 pts (XSP.TO −24.3% vs −27.5% real). The real
  number is shown next to every stand-in; no correction applied to the series.
- Critic: same agent and tools on the current portfolio, disclose only (the rebuild is the fix). Explainer: section
  "The portfolio you already have" from facts (G12 strict). Analyst: `existing_portfolio`, `what_if_existing`.
- A run without an existing portfolio is unchanged (no new facts key: demo cache keys unchanged).

## 44. Existing portfolio, follow-ups: fees, free text, requests via stand-ins, look-through, demo cache (Sun Nov 15, Joud)

- **Fees** (`dh.fees`, `scripts/build_fees.py`): Yahoo net expense ratio per fund (the held fund's own: XSP.TO's,
  not SPY's), shown in $ a year today vs rebuilt. Not deducted from returns. Unknown → listed, never 0.
- **Free text**: the extractor reads holdings already owned ("I have 10k in XIU", "j'ai 10 000 $ dans XSP") into
  `existing_positions`, amounts grounded in the text; such an amount is never taken as the capital.
- **Requests**: "10% in XSP" is measured with SPY (stand-in, labelled; hedge not simulated for requests).
- **Look-through**: the review says which equity ETFs were opened; the hosted app builds SPY's holdings at start.
- **Demo cache**: `make warm` also warms Robert + the example portfolio (Critic ×2, Explainer, 2 Analyst questions),
  with the exact profile the guided interface sends.

## 45. Critic validation sees its FACTS; strategies named by what they hold; correlations at 3 decimals (Sun Nov 15, Joud, `claude/relaxed-edison-ihsi38`)
- **Problem (code audit, run on the 3 personas):** the Critic's validator only accepted numbers from the tool results
  an objection cited. It dropped Robert's own TSLA objection (25% asked, 15% loss limit: from the profile, not a
  tool), "worst 12 months" (a window) and Amira's "QQQ + SPY = 61.5%" (a sum of two weights).
- **Fix (`critic.validate`):** a number is backed if it is in a cited tool result OR in the FACTS the Critic was given
  (client, limits, that strategy's weights/split/stats) OR the sum of two of that strategy's weights. Integers followed
  by a duration ("12 months", "4-year") are not data. Inventions still drop (test). Prompt `critic-v2`.
- **"More prudent" was false for Robert:** 5% stocks (XBB/AGG) fell −9.5%, 15% stocks (with ZST) −8.6%. Levels 2 and 3
  are now "less in stocks" / "least in stocks": named by what they hold; the measured drops sit next to the name.
- **C6 at the edge:** QQQ/SPY = 0.948 passes C6 (✘ at 0.95) but was written "0.95". Correlations now shown with 3
  decimals; a Critic claim whose rounding crosses 0.85 or 0.95 gets the exact value written back by code.
- **One default model:** `dh.llm.DEFAULT_MODEL_ID` (Opus 5.5, verified) used by `ask` and every agent (was Nova Lite in `ask`).
- **Cost:** strategy names and the Critic prompt are in the cached facts → the Critic and Explainer demo caches no
  longer match. **Re-run `make warm` (valid AWS keys) and commit `cache/` before Sun 23:59.**

## 46. Quantitative audit fixes R0-R10 (Sun Nov 15, Joud with Claude, `claude/nice-volta-4dwcp4`)

Audit of the theory behind each tool (anomalies A1-A16, root causes and tests in `notes/risk-architecture.md`).
New package `src/dh/risk/` (contracts, loss_model, goals, levels, kyc_validation, frontier, sync, controls); the
agents call it, it never imports them (tested). Approved by Joud on the recommendations; **Will to review before any
merge** (most edits are in agent files).

- **R1 ceiling (A1).** The growth ceiling no longer comes from the one drawdown of 2021-2026: scanning up from 0%, it
  is the last share before P(drawdown over the client's horizon > loss limit) > 10%, stationary block bootstrap,
  average = cash + 3% on the growth part (central assumption), the same random paths for every share. The horizon
  rule (#22) stays. On known-parameter markets the realised breach rate falls from 39-71% to 15-24% for alpha = 10%:
  better, still above alpha (5 years cannot pin down a tail), so the range is shown.
- **R2 range.** The same rule on 3-year sub-windows, one year apart; the full-window ceiling is part of the range.
- **R3 central premium.** 3% a year over cash on growth assets (order of magnitude of the long-run equity premium over
  bills, Dimson-Marsh-Staunton; verify the current edition before quoting). An assumption, labelled as such.
- **R4 goals (A2).** Status instead of a floor in the risk-only view: reachable without equity / needs equity (smallest
  share, central, ≤ ceiling) / only if 2021-2026 repeats / insufficient (< 50%) / impossible (< 25%). Never "more than
  100%": the old message came from a view with no premium, where more stocks only add variance.
- **R5 levels (A3).** Levels 2-3 use level 1's defensive basket; a level not safer on worst drop AND chance of loss is
  dropped, a mixed one is flagged. Robert's "more prudent" was riskier (−9.5% / 5.7% vs −8.6% / 3.9%); now −7.7% / 1.8%.
- **R6 KYC (A4).** Bet options on a common A grid (0 to 4.8, the most the +40/−10 bet can express without a negative
  guaranteed return); consistency on option ranks (gap ≤ 0.3); the most cautious answer everywhere = A ≥ 4.8,
  consistent, no longer flagged.
- **R7 loss question (A8).** "Largest drop from a high point, at any time while invested": the measure the loss rule
  uses (drawdown over the horizon), instead of "in one year" compared with a 5-year drawdown.
- **R8 controls (A7).** G7 = D2 = the loss rule, simulated again on the FINAL weights (other seed, 2000 paths, 2 standard
  errors of tolerance); G17 (G7 × capital) merged into it; D1 shows the observed drop, never blocks; G18 checks that every
  section describes the final weights (A6, `dh.risk.sync`). The Critic and the request side-by-side use the same rule.
- **R9 inflation.** Goal chances also in today's dollars (Bank of Canada 2% target).
- **R10 frontier (A5).** One measure on the chart: arithmetic mean (the optimiser's); an optimiser failure leaves the
  chart without a frontier instead of raising.
- **A10.** `metrics.max_drawdown` counts a loss on day 1 (was missed; quant_toolkit already did).

**Effect on the personas (results.csv, commit after c019584):** Amira 95% → 40% growth (her 40% limit over 15 years:
a growth-tilted portfolio breaks it in more than 10% of simulated paths above that); Mateo 60% → 55%, two strategies
(the third was not safer than the second); Robert unchanged at 15%, his second level now really safer. Robert's TSLA
numbers (#28) are unchanged. Run time: Amira ~10 s (was ~4.5 s).

**R0 timing:** integrated on Nov 15 before the 23:59 submission freeze under the user's explicit merge authorization. Final deliverables and cached explanations must be regenerated on the integrated code and final dataset.

## 47. History from 2010 (Sun Nov 15, Will)

**Decision (Will):** the team's window starts 2010-01-04. `harness.toml [data] start = "2010-01-04"` is the one place it
is set: `make data-long` builds from it (organizers' script, unchanged), the hosted app's fallback rebuild
(`dh.bootstrap.build_start`) uses it, and `dh.data` drops anything earlier. With the 2021-2026 starter pack it changes
nothing. Covers the 2020 crash and 2022; not 2008 (use `START=2004-11-18` for that).

**Not done by this commit:** the data itself (built on Will's laptop: `make data-long`, then `make data-up` so the host
downloads it from S3); `results.csv`, the cached agent answers (`make warm`) and the deliverables' numbers are still on
2021-2026 and must be regenerated on the new data before they are quoted. Assets that did not exist in 2010 start later
(ZST.TO, ESGV with their stand-ins; SHOP.TO 2015, BTC 2014, ETH 2017 without).

## 48. The submission stays on the starter pack's window (2021-2026) (Sun Nov 15, evening)

**Decision:** `harness.toml [data] start = ""`, so a hosted rebuild downloads the starter's own window (2021-11-12 →
2026-11-12), not 2010 (#47 reverted for the submission; `make data-long` with a start still works for research).

**Why:** every number in the deliverables, `results.csv` (persona rows of commit 9a2febb), the video script and the
committed agent answers is on 2021-2026. With 2010 data on the hosted app, the screens judges open would contradict the
documents, and regenerating results, caches and every quoted number before the 23:59 freeze is the riskier path.
The S3 `raw/` folder must hold the same starter files (`make data-up` from the starter pack).

**Limit (unchanged, stated in the tech doc):** one 5-year window with one mild bear market (2022); 2008 and 2020 are
not in it.

## 49. Français ⇄ English switch in both apps, French by default (Sun Nov 15, evening)

**Decision:** `src/dh/i18n.py` + `src/dh/i18n_fr.py`. A "Langue · Language" switch at the top of the sidebar of both
apps; default from `AF_LANG` (French when unset). `i18n.install()` wraps Streamlit's display and widget methods, so
every label, button, tab, option, help text and message goes through one table: whole UI strings are matched
exactly, and only long, distinctive UI phrases are replaced inside text built at run time. Widgets get a key computed
from their English arguments, so switching language never resets the client's answers. Page routing keeps the English
values; only what is displayed changes.

**Not translated (said on screen):** text generated by the engine and the agents (the Profiler's reasons, check
details, the trace, Claude's cached explanations). Translating it would either mix languages inside one sentence or
change the facts the Guardian checks (G11–G13 run on the English text).

**Tests:** `tests/test_i18n.py` (the table, engine text untouched, both apps in French then switched to English); the
other app tests run in English (`AF_LANG=en` in `tests/conftest.py`).

**Update (Sun night, #49 extended):** the whole app is French in French mode. Engine text (Profiler reasons, checks,
splits, strategy names, trace) is translated at display time (`dh.i18n_engine_fr`: sentence patterns that copy every
number unchanged, then a phrase table; French number style only outside HTML tags). Claude writes in French when the
app is French (Explainer and Critic get a `language` field and a French instruction; the Analyst gets the French
question); French answers have their own cache keys, English keys are unchanged; `make warm` fills both. G11 accepts
the French disclaimer; G12 still checks the numbers before display formatting. The fallback template exists in French.
