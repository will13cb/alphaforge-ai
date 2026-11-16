# codex/sync-alphaforge-main

**Goal:** carry current datathon2026/main into alphaforge-ai/main, as explicitly requested by the user.
**Status:** verified and ready to push.

## Done
- Compared source main 276fc7f with AlphaForge main 3d02f00 using its last synchronized source snapshot 024431d.
- Applied source snapshot changes on top of AlphaForge, preserving its French polish, voice language handling, French regressions and the newly approved video script.
- Integrated the three-persona Tesla comparison, assistant subject handling and bilingual navigation/pipeline display fixes.
- Resolved graph layout and French dictionary overlaps by retaining existing French labels and adding the new layout/translation entries.
- Carry only current file changes; do not import the development repository's history into the public submission repository.

## Contract changes
- No new contracts beyond the source commits; deployment configuration is preserved.

## How to check
- AF_LANG=en LLM_PROVIDER=mock PYTHONPATH=src python -m pytest -q tests/test_contrast.py tests/test_analyst.py tests/test_flow_graph.py tests/test_french_readability.py tests/test_i18n.py tests/test_interface_app.py tests/test_accessible_ui.py tests/test_explainer.py
- Fatal lint, compile and whitespace checks; compare target-only file hashes before push.

## Validation
- Initial affected regression: 70 passed; updated the old graph-label assertion for wrapped French text.
- Final focused French/layout/real-data UI/persona comparison check: 17 passed, 1 skipped.
- Fatal lint, compile and whitespace checks passed; verified target-only video script, voice, French engine wording, explainer and activity files unchanged.

## Next / limitations
- Verify the deployed Streamlit restart separately; this sync does not verify live AWS account availability.
