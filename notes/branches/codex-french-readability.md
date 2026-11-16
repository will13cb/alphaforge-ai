# codex/french-readability — Will

**Goal:** natural, presentation-ready Canadian French throughout the submitted interface.
**Status:** reviewed on rendered synthetic-data screens; ready to publish before the freeze.

## Done
- Read the entire UI and engine translation dictionaries and the French explanation template.
- Replace literal phrasing (risk one can “carry”, “global” aggregate bonds, “elle a rendu”) with natural financial French.
- Translate complete HTML text fragments before phrase replacement; recognize exact labels inside dynamic captions.
- Remove the generic “and” replacement; preserve inline commands and HTML attributes.
- Translate metric labels, table headings, table display copies, option labels, score descriptions, graph labels and activity captions.
- Translate chart titles, categorical labels and tooltips in a display copy; use French numeric/date formatting without changing data fields or numeric values.
- Read-aloud follows the displayed French interface language.
- Rendered Welcome, every profile step, results and Activity with synthetic returns. Checked results, expanded details, explanation and recorded events for mixed English/French text.

## Contract changes
- None. No allocation, numerical calculation, data, saved trace, cache or validation rule changed. French template wording changes only; numeric facts are copied unchanged.

## How to check
- `AF_LANG=en LLM_PROVIDER=mock python -m pytest -q tests/test_french_readability.py tests/test_i18n.py tests/test_explainer.py tests/test_answer_readability.py tests/test_accessible_ui.py tests/test_voice.py`
- French tests explicitly select French; existing English tests keep their normal language.
- Regression checks cover HTML boundaries, untouched commands/tickers, copied tables, chart numbers, field identifiers and language switching.

## Next / limitations
- Free-form live model text depends on the model; this review covers the translation files, deterministic template and rendered interface.
- Check current Montreal time immediately before changing the submitted main branch; never push after Sunday Nov 15 23:59 Montreal time.
