> Superseded: the team direction is a full multi-agent pipeline, see `system-design.md`. Kept for reference.

# Angle ideas (draft for William + Joud to pick from)

What the jury rewards (brief p.17): a relevant problem, **agentic** design that is actually justified,
**self-explaining** results tied to data, assumptions and limits, usefulness, creativity, clean execution.
It explicitly does NOT reward the highest backtest return or the most agents.
The personas' "what this tests" lines are the brief telling us what to demo:
- Amira: high risk ≠ "anything goes", still diversified.
- Mateo: preferences (ESG) count, not just return.
- Robert: **the system must push back** when a request conflicts with his profile.

---

## ⭐ Recommended: "The analyst that says no", a suitability-first second opinion

**One sentence:** An agentic analyst that takes an investor's request (e.g. "put 30% in NVDA"), checks it
against their profile, stress-tests it on real history (including 2022, when stocks and bonds fell together),
and answers with a verdict plus a "receipt" tracing every number to the data and every caveat to an assumption.

Why it fits: it hits Robert's test head-on (the hardest and most memorable one), is naturally agentic
(different roles, a governance check, a loop), and makes explainability the product, not an add-on.
Demo = same question asked by Robert vs Amira → different, justified answers (the brief suggests exactly this).

Agents (small, each with a clear job):
1. **Profiler**: turns persona + free-text request into a structured ask (assets, weights, horizon).
2. **Analyst**: calls tools only (`dh.returns`, `dh.summary`, `portfolio_returns`): vol, drawdown, correlation, concentration.
3. **Stress tester**: replays scenarios on the proposed vs a profile-consistent allocation: 2022 rate shock,
   worst 3-month window, CAD/USD move, crypto -50%.
4. **Governance**: deterministic rules (our labelled assumptions, e.g. "Robert: max 10% single stock,
   no crypto") + simulation-only boundary. Flags conflicts and missing info. Can send back to Analyst.
5. **Explainer**: writes the answer using ONLY numbers present in tool outputs; every number links to its
   source row. Separates fact / assumption / fiction.

Faithfulness check we can show (and log with `log_run`): an automatic test that every number in the explanation
appears in the tool outputs. "0 invented numbers across N persona scenarios" is a strong pitch line.

AWS: Bedrock (LLM + tool use, maybe Bedrock Agents/Guardrails), S3 (data + traces), Lambda (tools),
CloudWatch or S3 for the execution trace the judges can open.

Scope for 2 people: rules + tools are plain Python (fast), LLM only for parsing + explaining.

---

## Other options

**B. "What if 2022 happens again?": scenario stress-test coach.**
The user picks or describes a plan; the agents replay historical regimes from the starter data (2022 drawdown,
the rate-hike cycle via BoC/FRED series) and explain what would have happened and why for that persona.
+ Uses the data the organizers chose on purpose (5 years so 2022 is included). − Less "agentic" unless we add
planning.

**C. Evidence-traced allocation builder.**
Builds a fictional allocation per persona with a clickable explanation: every sentence carries a citation chip
(a data row, a computed stat, an assumption). + Very strong on explainability. − Portfolio builders are the
"standard" answer the jury says it won't over-reward.

**D. ESG screening agent for Mateo.**
Reads sustainability reports / filings (SEDAR+, EDGAR) via a Bedrock Knowledge Base and flags controversies
for ENB, CNQ, XOM vs ESGV. + Creative, uses documents + RAG. − Needs outside data and time; risky for 2 people.

**E. Hype detector for Robert.**
Compares a hyped name's (TSLA/NVDA) volatility, drawdowns and concentration risk to his profile and offers
calmer alternatives with the same theme. This is a narrower version of the recommended idea; it could be its first demo.

---

## How to decide (10 min)
1. Which demo moment do we want in the video? (Robert being told "no, here's why" is hard to beat.)
2. Can we have it running end-to-end by Saturday night with the starter data only? Extras later.
3. Write the chosen sentence in `CLAUDE.md` → "Our angle", plus a line in the decisions log.
