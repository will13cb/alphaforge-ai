# portefeuille_existant — Joud (touches Will's lanes: agents, interface, contract)

**Goal:** the client can start from the portfolio they already own (ticker + dollars, one by one), get a critique
with the engine's own checks and the Critic, and see it rebuilt into a strategy that fits their limits. Gap #1 from
the BN workshop deck (slides 13-14: "what am I trying to improve?", the XSP case). Decision #42.
**Status:** merged (#10). Follow-up on the same branch: ZEQT left aside (see below).

## Done
- `src/dh/standins.py`: 22 funds not in our data measured with a fund that tracks the same/close index; CAD-hedged
  ones simulated (USD return + overnight rate gap). `canonical('xsp')` → `XSP.TO`. Validation results in
  `src/dh/standins_validation.json` (derived stats only), shown next to each stand-in.
- `scripts/validate_standins.py`: real fund vs stand-in (Yahoo), logs `standin-<ticker>` worst_drop_gap to results.csv.
- `src/dh/agents/existing.py`: `review()` → current (C-F + Guardian), critique (always says where the stocks are),
  target = first proposed strategy, moves in $ (with "you hold it as XSP.TO"), stand-ins, not_assessable,
  optional Critic pass. `public()` = the review without raw checks.
- `pipeline.run`: review + Critic step in the trace, review copied into `res["limits"]["existing_review"]` (Explainer,
  G12). Wrapped: a failure never blocks the proposals.
- `critic.review_existing`: same prompt/tools/validation, extra FACTS (`context`), disclose only.
- `explainer`: `existing_portfolio` facts + template section + one prompt line; `guardian._known_numbers` knows them.
- `analyst`: tools `existing_portfolio`, `what_if_existing(ticker, amount_cad, add)` (only when the client entered a
  portfolio); offline answers in EN/FR ("Et si j'ajoutais 40 000 $ de XSP à mon portefeuille actuel ?").
- Interface: Welcome tab "I already have a portfolio" (each line says "measured with SPY (currency hedge simulated)"
  or "no market data, left out"); results section with stand-in notices, Critic points, moves table.

## In progress / next
- Done (#44): fees (`dh.fees`), free-text holdings (extractor), requests via stand-ins (pipeline), look-through
  status + `bootstrap.ensure_holdings`, `make warm` existing-portfolio plan, Assistant suggestions.
- To run before the freeze: `make warm` with Bedrock (46 calls), commit cache/. Demo path: Welcome → "I already
  have a portfolio" → "Try an example portfolio" (don't press Continue) → "Step-by-step questions" → "Try with
  an example client" → Run.
- ZEQT.TO (fund of funds) is left aside: "no data", disclosed, out of the numbers. The composite stand-in
  (closed PR #11) needs BMO's weights, unreachable from the session. The input tab now lists the ETFs we have data
  for when a holding has none, and offers an example portfolio built only from them (`EXAMPLE`).
- Free-text extractor: read "I hold 10k in XIU" into `existing_positions`.
- `make warm` for a demo persona with an existing portfolio (Bedrock caches for Critic/Explainer/Analyst).
- Requests (`requested_positions`) don't use stand-ins yet: "put 10% in XSP" still says no data.

## Decisions made here
- #42 (notes/decisions.md).

## Contract changes
- `profile.existing_positions`: dict ticker → dollars. `res.existing_review` and `res.limits.existing_review`
  (public view). `critic.review(..., context=None)`: optional extra FACTS, default unchanged.

## How to check it
- `make test` (273 passed with data), `.venv/bin/python -m pytest -q tests/test_existing.py`.
- `.venv/bin/python scripts/validate_standins.py` (needs internet): XSP.TO real −27.5% vs stand-in −24.3%.
- `make ui` → Welcome → "I already have a portfolio" → xsp 20,000 · Royal Bank 40,000 · ZEQT 10,000 → Continue.

## Open questions / blocked on
- Will's OK to merge (agents + interface lanes, contract field).
