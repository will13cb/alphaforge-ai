# codex/french-profile-extraction

**Goal:** fill the French profile form from explicit French client text, including the reported complete Amira example.
**Status:** verified and ready to publish.

## Done
- Added conservative French extraction for age, name, horizon, amounts, emergency fund, loss tolerance, reaction, experience, preferences and explicitly selected KYC answers.
- French thousands separators, decimal commas and contextual number words are accepted by numeric grounding.
- Added expected-value and KYC fields to the model schema and validation; only supported, explicitly grounded options survive.
- Complete facts omitted by model/cache responses using validated explicit-text patterns; never replace valid model values or infer risk scores.
- Preserve the distinction between hypothetical quiz amounts/returns and actual capital, target, loss limit and investment requests.
- Show the actual extraction source in the form rather than only the global Assistant mode.
- Kept existing raw caches readable: cached facts are revalidated and explicit missing fields completed.

## Contract changes
- Optional ev_answer_pct and kyc_bets now survive extraction using the existing profile fields already accepted by the wizard and Profiler.
- Extraction metadata adds supplemented_fields and failure_type (safe exception class, no credential values).

## How to check
- AF_LANG=en LLM_PROVIDER=mock PYTHONPATH=src python -m pytest -q tests/test_french_extractor.py tests/test_extractor.py tests/test_interface_wizard.py tests/test_interface_services.py tests/test_interface_app.py tests/test_french_readability.py tests/test_fixed_income.py
- Tests paste the exact client text through Streamlit and validate all required wizard steps, including the three risk choices.

## Validation
- Affected extraction/form/service/French/fixed-income regression: 80 passed, 1 skipped.
- Exact French Amira regression also passes with collapsed whitespace and a successful but incomplete model response.
- Final safety checks distinguish quiz capital and hypothetical losses from actual client facts.
- Fatal lint, compile and whitespace checks pass.

## Limitations
- Conservative local patterns do not understand arbitrary prose; missing/unsupported answers still require review.
- The failing deployed request's actual Bedrock error was not available; no claim is made that credentials expired.
