# claude/eager-knuth-hwk00z — Claude (for Joud)

**Goal:** list what is still missing against the brief and the README, and build what can be built offline before
the 23:59 freeze: the KYC bets screens in the guided interface.
**Status:** merged into `main` on Sun Nov 15 at the user's request (Joud), before the 23:59 freeze. Touches Will's lane (`interface/`):
Will to review after the merge.

## Done
- **KYC bets in the guided interface** (decision #40; the README and the technical doc listed it as missing).
  The engine already scored them (`profiler.kyc_check`, `expected_value_check`); the form never asked them.
  - `interface/core/questions.py`: new optional step "Three quick choices" (after "Your experience") with the three
    `dh.kyc.BETS`, wording and options taken from `dh.kyc` (same grid of attitudes on every bet, R6), plus
    "I'd rather skip this one". The expected-value question (`ev_answer_pct`, +25% / −5% bet) is in "Your experience",
    shown when the person has some experience.
  - `interface/core/wizard.py`: all three bets or none (`dh.kyc.score` needs the three); `to_profile` sends
    `kyc_bets` / `ev_answer_pct`; `from_profile` prefills them (demo clients keep their answers).
  - `interface/core/services.py` `kyc_lines` + `interface/views/results.py`: "Why these limits?" says in plain words
    what the three choices point to and whether they agree with the other answers; read from `limits["kyc"]`,
    nothing scored in the interface.
  - `tests/test_interface_kyc.py` (5 tests); `tests/test_interface_app.py` no longer hard-codes the review step index.
- Checked: for the 4 demo clients, `derive_limits` is identical with and without the KYC answers (only the `kyc`
  key differs), and neither `explainer.facts` nor `critic.facts` reads it, so the Bedrock demo caches keep their keys.

## Inventory: what is still missing (Sun 17:00)
Blocking or near-blocking for the freeze (need AWS keys or data, not possible in this session: Yahoo, issuer sites,
BoC and FRED are refused by its network):
1. **Public deployed app link for Devpost** (CLAUDE.md, CONTEXT.md): instructions in the README; no deployed URL is
   recorded in the repo. Check it opens and runs a persona before 23:59.
2. **Demo caches on the final data** (`make warm`, then commit `cache/`): the data moved to 2010+ (#47), so the
   cached Critic/Explainer/Analyst answers no longer match; offline, the app falls back to template text.
3. **Numbers on the final data** (`make log-personas`, `notes/results-status.md`): `results.csv` persona rows are from
   `9a2febb`, before #47. Deliverables quote "TSLA −70.9%, fits up to 3.1%" (2021-2026 window).
4. **Amira gets less growth than Mateo** (`results.csv` @ `9a2febb`: Amira 40%, Mateo 55%). Being worked on in
   `claude/affectionate-clarke-jqdfg6` (xfail tests, causes: loss simulated over the whole horizon, ladder anchored
   on the top flavour). Needs a team decision; visible in the demo.
(Decision #11 is already met: `a24478b`, the commit with the starter CSVs, is not in this repo's history.)

Features listed as missing in the README / technical doc:
5. ~~KYC bets screens in the interface~~ (this branch).
6. **Bedrock AgentCore Runtime**: "planned, NOT deployed" (`aws/architecture.md`). Needs the event account.
7. **ETF holdings for QQQ / ESGV / XIU** (SPY only): look-through is a lower bound for Amira's tech via QQQ and
   Mateo's fossil-fuel exclusion via ESGV/XIU. Issuer files by hand (`data/README.md`).
8. **Mateo's "avoid controversies"**: only a fossil-fuel ticker list + SPY→ESGV; no controversy or ESG data source.
9. **Macro "as published" view** (lane-market-data next #4): macro is dated by reference month.
10. Voice (Transcribe / Polly) not smoke-tested live; `app/app.py` keeps the old look.

Unmerged branches with work (not reviewed here): `dividende_cible`, `exploration`, `claude/clever-shannon-ociuzg`,
`claude/wizardly-maxwell-52iwnb`, `feat/live-analysis-redesign`; `univers_produit` is a plan only.

## Decisions made here
- None new: the screens apply #40 (cross-check only, wrong expected value → knowledge ≤ 3).

## Contract changes
- None: `kyc_bets` and `ev_answer_pct` were already in `notes/contract.md` §1; the interface now fills them.

## How to check it
- `LLM_PROVIDER=mock .venv/bin/python -m pytest -q tests/test_interface_kyc.py tests/test_interface_wizard.py`
- `make ui` → "Step-by-step questions" → "Try with an example client" → Edit "Three quick choices": Robert's
  answers are prefilled; answer only one → "Answer all three choices, or skip all three"; run → "Why these limits?"
  shows the cross-check.
- On merge, Will: `deliverables/TECHNICAL_DOC.md` "Improvements" still lists "screens for the KYC bets in the guided
  interface" (deliverables are Will's lane, left untouched here).

## Open questions / blocked on
- Merged at the user's request; Will to review the interface change (his lane).
