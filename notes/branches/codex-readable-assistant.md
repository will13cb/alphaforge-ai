# codex/readable-assistant — Will

**Goal:** Make live, offline and saved assistant answers easier to scan without changing financial calculations.
**Status:** ready for integration

## Done
- Live Analyst prompt: takeaway first, brief sections, holdings on separate bullets, strategy comparisons in a table or list, relevant what-if sections.
- `results_overview` includes the existing strategy weights; deterministic results list holdings from these weights.
- Short, bulleted clarification help in English and French; separate what-if paragraphs.
- UI adds paragraph breaks to long saved plain prose using only whitespace; existing Markdown, every word, number, ticker and sign are preserved.
- Evidence details never show an empty bullet; voice playback and trace content keep the original checked answer.
- Analyst cache version changes to `analyst-v4-readable`, so future live replies follow the new prompt. Old demo caches remain untouched; offline answers can be rebuilt deterministically.

## In progress / next
- Merge into main and let Streamlit reload; no deployment setting is needed.

## Decisions made here
- Format with Markdown before the existing validators; no second LLM rewrite, no weakened numeric validation.
- Do not convert the ambiguous gold dollar question into a portfolio percentage; ask for clarification.

## Contract changes
- Analyst `results_overview` adds `weights` per strategy, copied from the run; engine and market contracts stay unchanged.

## How to check it
- `python -m pytest -q tests/test_answer_readability.py tests/test_analyst.py tests/test_accessible_ui.py tests/test_interface_app.py`
- Check that an allocation question produces a strategy comparison and per-holding rows, a what-if separates its points, and the fallback lists short examples.
- Tests ensure displayed legacy prose preserves all words, numbers and punctuation, authored Markdown is unchanged, and structured offline allocations pass the original validators.

## Open questions / blocked on
- Live Bedrock prose depends on model output; existing validation and deterministic fallback still apply.
