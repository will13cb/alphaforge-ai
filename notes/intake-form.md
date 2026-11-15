# Intake form (DRAFT, from Joud's proposal, condensed)

Principle: a step-by-step wizard, ~6 minutes with essentials only. Ask facts; **compute** what can be computed
(risk capacity, net worth, emergency-fund target). Measure risk with concrete scenarios, not "what is your
risk tolerance?". Optional questions folded under "Add details". A live "Your profile" panel on the side.
E = essential, O = optional.

| Step | Questions (component) | E/O | Why |
|---|---|---|---|
| 0. Welcome | Consent to data use (checkbox); "simulation, not advice" | E | Quebec Law 25 / PIPEDA, expectations |
| 1. You | Birth date (date); province (dropdown); dependents (stepper); employment status (dropdown); income stability (segmented: very stable → uncertain) | E | Horizon, capacity to take risk |
| | Family situation; employment sector (`employment_sector`, a sector of `assets_universe.csv`) | O | Avoid concentration with own job's sector (C3b ✘ above 15%, decision #20) |
| 2. Finances | Gross income ($ or range); monthly expenses ($); liquid savings ($); current investments by account (TFSA, RRSP, FHSA, non-registered…); debts (type, balance, rate) | E | Savings capacity, emergency fund, high-rate debt first |
| | Unused TFSA/RRSP room; home owner; upload current portfolio (CSV/PDF) | O | Account placement, existing exposures |
| 3. Goals (cards, up to 5) | Type: safety cushion · major project · retirement · income · pass on wealth · other; target amount; target date; date flexibility; priority; starting capital; recurring contribution + frequency | E | Each goal has its own horizon and risk |
| | Retirement: age + desired income. Income: monthly amount + start date | E (if goal) | |
| 4. Liquidity | Large withdrawals in the next 3 years (toggle → amount + date); share that might be withdrawn without notice (slider) | E | Money not to expose to markets |
| 5. Relationship to risk | "Your $X drops 20% in 3 months, what do you do?" (sell all / sell some / nothing / buy more); pick one of 5 portfolios shown with best/worst year in % and $; max acceptable 1-year drop (slider, shows $ live); protect ↔ grow (5-level slider) | E | Tolerance from behaviour, not self-label |
| | Past crash experience (2020, 2022) and what they did | O | Actual vs declared behaviour |
| 6. Knowledge | Knowledge level (dropdown); products already held (chips) | E | Which products can be proposed |
| | Years of experience; 3-question mini-quiz | O | Corrects overestimated knowledge |
| 7. Preferences | Management style: automatic / guided / self-directed | E | Output format |
| | Interests (ETFs, CA/US/intl stocks, bonds, GICs, REITs, gold, crypto); exclusions (fossil fuels, weapons, tobacco…); ESG importance; currency; already-concentrated exposures | O | Filters the universe |
| 8. Confirm | One open question "anything else we should know?"; profile summary with Edit per section and alerts (e.g. unrealistic return target) | E | Client confirms accuracy (Canadian KYC) |

Computed, never asked: risk capacity, retained risk level (lower of tolerance and capacity), net worth,
savings rate, debt/income, emergency-fund target.

Merged or removed vs. the first idea list: "reason to invest" + "financial goal" → one Goals step;
one global horizon → a date per goal; "acceptable risk level" + "tolerance" dropdown → one scenario block;
amount + frequency → one combined field per goal.

Open question: how much of this fits the demo time? A "short mode" (≈8 essential questions) may be enough for
the video, with the full form shown as the product vision.
