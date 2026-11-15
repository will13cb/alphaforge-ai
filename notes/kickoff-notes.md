# Kickoff notes (cleaned up; originals by Will and Joud, Nov 14)

No access codes or emails in this file: the repo will be public.

## Challenge presentation (Banque Nationale case)
- Agentic, multi-agent: split the solution into agents specialised on precise tasks.
- Decide from signals; conclusions must be explainable; self-explaining.
- High risk ≠ accept everything.
- Efficient frontier mentioned.
- Explainability is the emphasis. Cite sources. Public data, chosen and justified.
- AWS environment: use at least one service (Kiro was mentioned; to confirm).
- Strong contrast between personas → show adaptability. Use several criteria to evaluate.
- Easy-to-use interface.
- Deliverables: prototype + code, video, documentation, one-page presentation.
- **Grading: 20% solution, 20% agentic, 20% data, 10% UX/UI, 15% AWS, 15% pitch.**

## Workshop 2 (understanding the investor, BNCD)
- Common language; understand how to structure a portfolio; which questions to ask.
- Ask the reason for investing: safety cushion, fund a major project, prepare retirement, generate income,
  pass on wealth. Look at what already exists on the market.
- Consider constraints such as liquidity.
- Product families: cash/liquid products, fixed income, equities (several sub-categories), funds,
  alternatives, crypto, derivatives / structured products.
- Horizon: short < 3 years, medium 3–10, long 10+. Capacity to absorb risk, horizon and age, tolerance.
- Risks: market, credit, liquidity, rates and inflation, currency; diversification (geography, sector,
  investment type, risk source, classification), inflation risk.
- Reliable data. Flow: raw data → observation → analysis → proposal → exploration.
- Frame the solution: objective before product. Return, risk and horizon are inseparable.
  Diversifying means checking the exposures. The investor sets the limits; a credible proposal must be explainable.

## Will's agent ideas
- Strategy agent → computes.
- Debate agent, but not too much.
- Persona agent: risk tolerance, capacity to absorb risk, user objective (the five above).
- Guardian agent that checks everything is correct (Canadian and international rules).
- Tests: fake profiles; describe the steps between agents to verify them.

## From Joud's research (summary)
- Workshop deck: profile before product; tolerance ≠ capacity; real diversification = exposures
  (asset class, country, sector, currency), not number of holdings; traceable data (source, date, currency,
  total return); explanations answer: which data, why this choice, what limits, what would change the answer.
- Literature: goals-based investing (Shefrin & Statman 2000; Das, Markowitz et al. 2010), loss aversion
  (Kahneman & Tversky 1979), human capital (Bodie, Merton & Samuelson 1992), asset allocation dominates
  (Brinson et al. 1986), 1/N often beats optimisation out of sample (DeMiguel et al. 2009).
- Canadian KYC/suitability (client focused reforms, NI 31-103): personal and financial situation, objectives,
  knowledge, risk profile (capacity + tolerance), horizon.
- Proposed agent architecture: Persona → Strategy (tools compute) → Critic (≤3 objections, 1 round) →
  Guardian (✔/⚠/✘, can send back) → Explainer (numbers checked against facts). See `system-design.md`.
- Proposed intake form: see `intake-form.md`.
- Practical: Windows has no `make`; use `python -m dh ...` / `python -m streamlit run app/app.py`.
  Event AWS credentials need access key + secret + session token (expires; renew).
