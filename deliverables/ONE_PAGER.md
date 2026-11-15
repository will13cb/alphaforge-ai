# AlphaForge AI — an investment analyst that can say no, and shows why

William Caron-Bastarache · Joud Katbe · PolyFinances Datathon 2026 · Challenge by National Bank × AWS

Simulation only, fictional profiles, not financial advice.

**Problem.** Investors can see every price, but not what a portfolio means for *them*: how much they can lose, how
long they have, whether a hyped stock fits. A cautious 59-year-old asking for 25% in Tesla deserves a clear answer
with his own numbers, not a generic risk score or a quiet "yes".

**Agentic approach.** Specialised agents in a fixed order, so the controls always run: **Extractor** (agent: the
client's own words → profile; every number must be in their text) → **Profiler** (the client's limits, each with a
written reason) → **Market data** (risk facts per asset) → **Portfolio** (up to 3 strategies at different risk
levels) → **Guardian** (loss, diversification and consistency controls; a ✘ drops the strategy) → **Critic** (agent: investigates with 11 tools before
objecting; each objection must cite a tool result, and its one fix per strategy is recomputed by code and re-checked)
→ **Explainer** (agent: writes the answer and checks its own draft with the Guardian's rules) → **Guardian** again on
the text → **Analyst** (agent: follow-up questions, its what-ifs re-run the whole pipeline). The agents choose what
to check and how to say it; *code sets every limit and every number.*

**What's original.**

- **Limits move with the client and the data, not a fixed table, and say where they come from.** The stocks/bonds
  split is the strictest of a horizon rule (a stated judgment), money needed within 3 years, and the largest share
  whose simulated chance of exceeding the loss threshold over the horizon stays within a stated model threshold; the trace names the one that decided. Three
  strategies = three risk levels; the client chooses. One company's cap comes from its own worst drop: for Robert, Tesla fell −70.9%, so 25% alone would have cost −17.7% of the portfolio,
  more than his whole 15% loss limit; it fits up to 3.1%. The answer gives him these numbers; the choice stays his.
- **Look-through:** a company held directly *and* inside ETFs is counted once, for real.
- **Every number traced:** the Guardian rejects any explanation quoting a % the pipeline didn't compute; the
  Critic's and Analyst's numbers must come from tool results they cite.
- **Tested, then set aside:** a mean-variance optimiser (its weights moved with the window); we keep only what
  describes risk without forecasting (each holding's share of the risk).

The loss simulation uses cash plus a 3% annual premium on growth assets (team assumption), a 10% model exceedance threshold, and disclosed sensitivity. It is not a guarantee of future losses.

**Data sources.** Organizers' starter pack: daily prices for 31 assets 2021-11-12 → 2026-11-12 (Yahoo Finance),
USD/CAD and rates (Bank of Canada), U.S. macro (FRED); all returns in CAD. Issuer ETF holdings (State Street SPY,
as of 2026-11-12) for look-through. Sources, processing and limits documented in `data/README.md`.

**Explainability.** Each limit carries its reason ("horizon 4 years → at most 15% in stocks"); each strategy its
worst drop, 2022 behaviour and chance of a loss (risk-only view, not a forecast); each hand-off between agents is
written to a trace of steps, numbers and verdicts, never the model's raw reasoning.

**AWS (qualifying, each with a real role).** **Amazon Bedrock** runs Claude Opus 5.5 for the four agents;
the **Strands Agents SDK** gives them their tools and tool loop; **Amazon S3** stores every run's evidence as JSON
(`traces/`), so any answer can be audited after the fact; optional voice uses **Amazon Transcribe** and **Polly**.

**Validated.** 16 test profiles (the three personas + traps: a beginner asking for 100% Bitcoin, a 2-year horizon
wanting high risk, an explanation with an invented number…) → 16/16 correct verdicts (`results.csv`).

**Benefits for the user.**

- Sees what fits *their* limits, in their numbers (% and $), before deciding.
- Gets a respectful "here's what it would cost you" instead of a silent yes or a flat no.
- Can verify every claim: sources, assumptions and limits are shown with the result.
- Can start from the portfolio they already hold: same checks, fees in $, the moves to a strategy that fits.
- Two views of the same engine: a guided interface (typed or spoken) and a demo view with every hand-off.
