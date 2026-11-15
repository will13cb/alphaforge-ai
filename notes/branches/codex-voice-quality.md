# codex/voice-quality

**Goal:** improve the voice quality and cumbersome playback/dictation reported by the user.
**Status:** integrated with current main; focused tests passed (2026-11-15).

## Done
- Polly neural Joanna/Gabrielle replace standard voices; SSML controls pacing and escapes user content.
- Recording language is independent of the displayed text's playback language.
- Listen requests playback in one click; unrelated reruns never request autoplay.
- Long explanations form one seekable WAV from PCM passages, preserving all text.
- Welcome reads the actual displayed introduction rather than a separate script.
- Transcription status updates automatically every two seconds; transcript review and submission remain explicit.
- Technical recording details move into an expander; AWS cleanup behaviour is retained.

## Decisions made here
- Retain AWS Transcribe recorded dictation and Polly playback; no claim of real-time conversation.
- No silent fallback to the robotic standard engine. No new packages or AWS permissions.
- Preserved concurrent main's KYC questions and interface changes.

## Contract changes
- No financial/profile changes. voice.narrate returns audio and MIME.
- read_aloud accepts the displayed text language (English default), independently of microphone selection.

## How to check it
- PYTHONPATH=src LLM_PROVIDER=mock python -m pytest -q tests/test_voice.py tests/test_accessible_ui.py tests/test_interface_app.py tests/test_interface_kyc.py tests/test_fixed_income.py
- Tests verify neural/SSML requests, escaped user text, complete seekable long audio, language separation,
  playback only on click, cache reuse, automatic transcript retrieval and retained review-before-submit.
- Fatal lint and whitespace checks pass.

## Open questions / blocked on
- No live AWS credentials in this workspace: neural synthesis and listening quality require a deployment smoke check.
- Browser autoplay policies can still require Play after the explicit Listen request.
- User will copy changes from datathon2026 into AlphaForge; no deployment changed here.
