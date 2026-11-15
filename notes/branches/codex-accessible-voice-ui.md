# codex/accessible-voice-ui — Will

**Goal:** Refresh the guided Streamlit interface and add optional accessible voice input/output using AWS.
**Status:** ready to merge after resolving latest-main conflicts; live AWS speech smoke test pending

## Done
- Merged with latest main: preserve its cream/ink light and violet dark redesign, chart palettes, mobile navigation, and existing-portfolio flow; add larger text and optional speech.
- Results reorganized into strategies/limits, plain-language summary, and checks/holdings tabs.
- Optional Amazon Transcribe dictation with editable transcripts and a separate submit step.
- Amazon Polly read-aloud for welcome, profile questions, results explanations and assistant answers; long text split into passages.
- Speech failures keep the text flow working. Private voice/ S3 prefix, bounded recordings and cleanup; running batch-job discard limitations documented.
- AWS setup and permissions: [aws/voice-accessibility.md](../../aws/voice-accessibility.md).
- Branch created from main at 6f20ddacf2cae88237ef2b87cc0b857b63563356.

## In progress / next
- Verify Transcribe/Polly live with event credentials; configure voice/ lifecycle before public use.
- User authorized merging into main on Nov 15; final regression checks run against combined code.

## Decisions made here
- Voice is opt-in and uses existing analysis/extraction checks; no automatic submission.
- Joud owns ingestion, S3 datasets and the expanded product universe; this branch changes presentation only.

## Contract changes
- None to market-data or portfolio contracts.

## How to check it
- `PYTHONPATH=src python -m pytest -q` (offline suite; data-dependent tests skip without CSVs).
- Browser checks: dark surfaces render, microphone panel appears, mobile has no horizontal overflow.
- Regression tests cover theme switching preserving answers, transcript review before submission, no duplicate question on rerun, speech failures and cleanup.
- `streamlit run interface/app.py`; follow aws/voice-accessibility.md for a separate branch deployment.

## Open questions / blocked on
- Live AWS speech permissions to be verified in the event account.


## Integration with latest main
- Resolve conflicts against `3e0d6a260b978471307d41d023071631d13147cf` by retaining current interface functions and adding voice hooks.
- Keep `theme.mode`, `palette`, `style_chart`, Dark mode toggle, mobile navigation and existing-portfolio review.
- Keep main configuration defaults; no data/market/portfolio files changed by this integration.
- Voice stays disabled unless `AF_VOICE_ENABLED = "1"`; live service permissions and voice/ lifecycle remain operator setup.
