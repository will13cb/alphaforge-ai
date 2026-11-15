# codex/explanation-headings

**Goal:** give the plain-language explanation a clear title, section headings and strategy subtitles in datathon2026; user will copy it into AlphaForge.
**Status:** ready for main.

## Done
- Guided view: Your investment summary title, semantic section headings and strategy subtitles.
- Shared display formatter supports live/cached bold labels, italic strategy names and deterministic-template bullets; also used by the jury view.
- Original explanation, numbers, audit records, cache keys and read-aloud text remain unchanged.

## Decisions made here
- Presentation-only formatting; no model or financial changes, no AlphaForge deployment.

## Contract changes
- None.

## How to check it
- Example formatting checks and Python compile/lint checks; existing accessible UI regression.

## Open questions / blocked on
- User copies the changes into AlphaForge separately.
