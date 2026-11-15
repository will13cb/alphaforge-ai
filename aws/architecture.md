> **Release update:** G7/D2 now uses a horizon bootstrap on final weights (10% model exceedance threshold, cash + 3% growth premium assumption); G18 checks consistency, research G19 dividends. Activity and optional Transcribe/Polly speech are integrated. Refresh the rendered PNG before presenting it.

# Architecture: what runs today (updated Sun Nov 15, evening; decisions #14, #30, #40)

**Strands agents for the steps that decide, a fixed pipeline for the orchestration, models on Amazon Bedrock, every
run's trace kept on Amazon S3.** The two Streamlit apps run locally and on Streamlit Community Cloud, which reads the
data from S3 at first start (`src/dh/bootstrap.py`); a CLI runs the same pipeline. Bedrock AgentCore Runtime
was planned "if working by Sunday midday" (#14) and is **not deployed**. "Agents investigate and argue, code enforces."
Dashed = not built / not deployed. Keep this in sync with what actually runs: the jury compares it to the demo.

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 320, "nodeSpacing": 40, "rankSpacing": 50}}}%%
flowchart TB
    %% ---------- 0 · Input ----------
    subgraph L0["0 · Input · app/ and interface/"]
        direction LR
        P0["Fictional personas<br/>Amira · Mateo · Robert"]
        Q["Guided questions<br/>checked with the engine's own limits"]
        VO["Voice, optional<br/>speak, hear the answer"] --> T
        H["'I already have a portfolio'<br/>holdings line by line or in words"]
        T["Free text"] --> EXT["Extractor · Strands agent<br/>tool: check_profile<br/>missing facts → ask, don't guess"]
    end

    O{{"Orchestrator · pipeline.py<br/>fixed order · one round · Guardian always runs"}}
    P0 --> O
    H --> O
    Q --> O
    EXT --> O

    %% ---------- Deterministic core ----------
    subgraph CORE["Deterministic core · no LLM"]
        direction TB
        PR["1 · Profiler<br/>tolerance · capacity · knowledge → limits, each with its reason<br/>loss limit · defensive floor · per-company and crypto caps<br/>KYC bets → A: cross-check only · expected-value question"]
        MD["2 · Market data<br/>31 assets in CAD · vol · worst drop · CVaR · correlations<br/>2022 stress (2008 / 2020 when covered) · goal outlook"]
        PF["3 · Portfolio<br/>up to 3 strategies = 3 risk levels<br/>split computed: largest growth share meeting the simulated horizon loss rule,<br/>capped by horizon, liquidity, safety net · says which one set it<br/>crypto only if asked + allowed + the data agrees"]
        CK["Checks C–F<br/>companies & sectors through the ETFs · geography ·<br/>duplicates · drawdown in % and $ · goal · profile fit"]
        EXR["Existing portfolio review<br/>same checks C–F and Guardian · fees in $ ·<br/>labelled stand-ins for funds without data ·<br/>rebuild into the first strategy, moves in $"]
        FI["Fixed-income lookup<br/>bond-only preference: sourced Canada / U.S.<br/>government bonds held to maturity, cash flows in CAD<br/>no invented offer, no guarantee promised"]
        RQ["Request side by side<br/>'as asked' vs 'what fits', same checks<br/>pros & cons from the numbers only"]
    end

    GU{{"Guardian · loss + consistency controls<br/>modelled on NI 31-103 KYC / suitability<br/>✔ pass · ⚠ disclose · ✘ block"}}

    %% ---------- Strands agents ----------
    subgraph AG["Strands agents · tools capped, traced"]
        direction TB
        CR["4 · Critic<br/>investigates before objecting · ≤ 6 tool calls<br/>≤ 3 objections, numbers backed by tools or facts<br/>fix menu: merge · trim · shift · disclose"]
        EX["5 · Explainer<br/>writes ids, never numbers ({n7})<br/>self-checks with G11–G13"]
        AN["Analyst · follow-up questions<br/>what-ifs re-run the whole pipeline"]
    end

    TOOLS["Tools = deterministic functions, JSON in / out<br/>market: asset_facts · portfolio_stats · stress_test · correlation_between ·<br/>goal_check · required_return · list_assets<br/>run views: look_through · strategy_checks · limit_reason ·<br/>risk_contributions (covariance only, no forecast)<br/>Analyst only: what_if_position · what_if_profile (re-run the pipeline)"]

    %% ---------- Flow ----------
    O --> PR
    O -- "bond-only preference" --> FI
    FI -- "matches or 'no supported match', with sources" --> UI
    PR -- "essentials missing (G1)" --> ASK["Ask the client"]
    PR --> MD --> PF --> CK --> GU
    GU -- "✘ strategy dropped, reason in the trace" --> DROP["Dropped"]
    GU -- "✔ / ⚠" --> CR
    CR -- "one fix per strategy:<br/>tighten an input, rerun the whole calculation" --> PF
    CR -- "objections not fixed → cons" --> RQ
    RQ --> EX
    PF -- "first strategy = rebuild target" --> EXR
    EXR -- "section 'the portfolio you already have'" --> EX
    CR -. "reviews it too, disclose only" .-> EXR
    EX --> GU2{{"Guardian G11–G13<br/>disclaimer · every number traced ·<br/>every request answered"}}
    GU2 -- "✘ → deterministic template, said in the trace" --> UI
    GU2 -- "✔" --> UI["Apps: limits & reasons · strategies & charts ·<br/>explanation · Analyst · trace"]
    UI -- "follow-up question" --> AN
    AN -- "what-if → same pipeline, Guardian included" --> O
    AN -- "answer: every number from a cited tool result, checked by code" --> UI

    CR -. calls .-> TOOLS
    AN -. calls .-> TOOLS

    %% ---------- Trace ----------
    TR[("Trace · one line per hand-off<br/>tool calls · numbers · verdicts<br/>never raw model reasoning")]
    O -. writes .-> TR

    %% ---------- AWS ----------
    subgraph AWS["AWS (slide 7)"]
        BR["Amazon Bedrock<br/>Claude Opus 5.5 · us-east-1"]
        S3[("Amazon S3<br/>traces/: one JSON per run<br/>raw/: data and bond catalogue for the hosted app<br/>voice/: audio, deleted once transcribed")]
        TP["Amazon Transcribe · Amazon Polly<br/>speech → text · text → speech<br/>optional (AF_VOICE_ENABLED)"]
        AC["Bedrock AgentCore Runtime<br/>planned, NOT deployed"]
    end
    AG -. "models" .-> BR
    EXT -. "model" .-> BR
    TR -- "every run (local copy if S3 is unreachable)" --> S3
    O -. "not deployed" .-> AC
    HOST["Streamlit Community Cloud<br/>the hosted apps"]
    UI -. "hosted on" .-> HOST
    S3 -. "raw/ data at first start" .-> HOST
    VO -. "audio" .-> TP

    style AC stroke-dasharray: 5 5
    style TP stroke-dasharray: 5 5
    style O fill:#fde68a,stroke:#b45309,color:#000
    style GU fill:#fde68a,stroke:#b45309,color:#000
    style GU2 fill:#fde68a,stroke:#b45309,color:#000
    style CR fill:#dbeafe,stroke:#1d4ed8,color:#000
    style EX fill:#dbeafe,stroke:#1d4ed8,color:#000
    style AN fill:#dbeafe,stroke:#1d4ed8,color:#000
    style EXT fill:#dbeafe,stroke:#1d4ed8,color:#000
```

Yellow = where code decides (orchestrator, Guardian). Blue = Strands agents (they decide which tools to call, never a
limit or a number).

## Layers at a glance

| Layer | Question it answers | Built with |
|---|---|---|
| Orchestration | In what order do the steps run, what happens on a ✘? | `src/dh/agents/pipeline.py`: fixed order, one Critic round, the Guardian can't be skipped. A ✘ on a strategy drops it (reason in the trace); a ✘ on the text swaps in the template |
| Agents that decide | Which tools to call, and when they're done | **Strands Agents** on Bedrock: Extractor, Critic, Explainer, Analyst. Tool calls capped and traced; demo answers cached and committed (`cache/`) so the demo replays without AWS |
| Deterministic steps | The numbers and the rules | Plain Python: Profiler, market data, Portfolio, checks C–F, request side by side, Guardian. The agents call them as tools |
| Model | The LLM | **Amazon Bedrock**: `global.anthropic.claude-opus-5-5` (Claude Opus 5.5), us-east-1, text and tool use verified 2026-11-14 (`make bedrock-check`). Critic/Analyst model switchable with `BEDROCK_CRITIC_MODEL_ID` |
| Hosting | Where the pipeline runs | **Streamlit Community Cloud** (the hosted apps) and **locally**: demo app (`make app`), guided interface (`make ui`), CLI (`python -m dh explain`). Data from `s3://$S3_BUCKET/raw/` (`make data-up`) at first start. Bedrock AgentCore Runtime: **not deployed** |
| Traces and data | Where runs and data are kept | **Amazon S3**: `traces/` every run from both apps and the CLI (`dh.tracestore`, #25; local copy if S3 is unreachable); `raw/` the data for the hosted app; `voice/` audio for transcription, deleted once done |
| Voice (optional) | Speak instead of type | **Amazon Transcribe** (speech → text, English or French Canada) and **Amazon Polly** (the answer read aloud), in the guided interface, off unless `AF_VOICE_ENABLED=1` |

| Component | LLM? | Output |
|---|---|---|
| Extractor | yes (Strands, tool `check_profile`) | `profile` fields from free text; follow-up questions for what's missing; code checks every field (#29) |
| Profiler | no | `limits`: risk level, loss limit, floors, per-company and crypto caps, each with a reason; KYC cross-check `limits["kyc"]` (#40) |
| Market data | no | per-asset facts, `strategy_stats`, stress windows, goal outlook (Joud) |
| Portfolio | no | up to 3 strategies = 3 risk levels (#32); growth ceiling = largest share whose simulated chance of a drop deeper than the loss limit over the horizon is ≤ 10% (#46), capped by the horizon rule, withdrawals and the safety net; says what set it (#33) |
| Checks C–F | no | one shape per check: value, limit, status, reason, source (#20) |
| Guardian | no | ✔ / ⚠ / ✘ per rule on each strategy (17 rules: G1–G16 and G18; G7 = simulated chance of a drop deeper than the loss limit over the horizon ≤ 10%, G18 = every number describes the final weights, #46); G11–G13 on the text |
| Critic | yes (Strands, 11 tools) | ≤ 3 objections, each number backed by a cited tool result or the facts it was given (#45); one fix per strategy that reruns the whole calculation, re-checked by the Guardian, original kept if it fails (#30) |
| Fixed-income lookup | no | for a bond-only preference: sourced Canadian and U.S. government bonds held to maturity (rate, maturity, cash flows in CAD); public references, not dealer offers; says when nothing matches |
| Request side by side | no | the client's request "as asked" vs "what fits", same checks; pros and cons from the numbers (#28) |
| Explainer | yes (Strands, tool `check_text`) | client text with number ids filled by code (strict G12, #27); template if a check fails (#23) |
| Existing portfolio review | no (+ Critic, Explainer, Analyst) | what the client holds, with the same checks C–F and Guardian, fees in $, labelled stand-ins, and the moves in $ to the first strategy (#42, #44) |
| Analyst | yes (Strands, tools) | answers to follow-ups; what-ifs re-run the pipeline, Guardian included; every number from a cited tool result (#35) |

**Not in the demo:** the Markowitz optimiser (branch `optimisation-markowitz`, Joud) was tested and set aside (#37):
with historical average returns its weights move with the window and lost to equal weights out of sample. What
doesn't depend on average returns is used: risk contributions (Critic tool) and the KYC bets (Profiler cross-check), #40.

Why not let an agent orchestrate: a supervisor agent choosing the next step looks more agentic, but nothing would
guarantee the Guardian runs every time, and the 16 test scenarios would stop being reliable (`notes/decisions.md` #14).
