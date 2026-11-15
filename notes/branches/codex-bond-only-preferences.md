# codex/bond-only-preferences

**Goal:** let a client request sourced Canadian/U.S. fixed income held to maturity, separately from traded bond funds.
**Status:** merged with latest main; verified and ready to publish (2026-11-15).

## Done
- Added deterministic fixed-income lookup agent, sourced catalogue builder and schema validation.
- Added bond-only selection, requested rate and country preference to guided profile; retained market path.
- Added simple allocation/rate/maturity results, expandable source/pricing details and catalogue search.
- Added clean-price/accrued-interest cashflows, CAD/USD conversion and explicit maturity/payment assumptions.
- Added independent hosted S3 catalogue loading, uploader support and trace persistence.
- Corporate/provincial/municipal and explicitly specified deposit offers can extend the CSV; no invented offers.

## Decisions made here
- Follow the user's requested simplicity: identify an instrument or explain no supported match; never promise 18% guaranteed.
- Public government terms/benchmark/auction data are references, not dealer inventory or executable prices.
- A zero-loss preference does not require a bond fund to pass a drawdown test for this distinct contractual scenario.
- No raw financial data committed; user will upload generated files to S3. No AlphaForge deployment changes.

## Contract changes
- Optional investment_mode/fixed_rate_pct/fixed_income_market in profile; fixed_income_scenario result sidecar.
- Deterministic explanation source fixed_rate, warning verdict, no market-history or LLM prerequisite.
- See notes/contract.md and data/README.md.

## How to check it
- PYTHONPATH=src LLM_PROVIDER=mock python -m pytest -q tests/test_fixed_income.py tests/test_interface_services.py tests/test_interface_wizard.py tests/test_extractor.py tests/test_tracestore.py tests/test_s3_data.py
- python scripts/build_fixed_income.py; inspect source dates/quality report, run a 3%/10-year and 18% request.

## Validation
- Built 409 sourced government instruments (56 Canada, 353 U.S.), zero rejected rows.
- Fixed-income regressions: 29 passed, including actual results-screen rendering.
- Combined feature/service/UI regression: 79 passed. Preserved current-main risk update: 17 passed, 1 skipped.
- Fatal lint, compile and whitespace checks passed. Rebuilt catalogue: 409 instruments, zero rejected rows.
- No live AWS upload/test claimed; user will supply S3 data.

## Open questions / blocked on
- Complete dealer inventories and executable offers need sourced uploads; not claimed as available publicly.
- User will upload catalogue to S3 and copy changes into AlphaForge.
