# Guided interface (branch `interface`)

A second front end for the same engine, for any adult: questions one step at a time, checked as you type, results
essentials-first, and an assistant you can talk to. `app/app.py` (the jury demo) is untouched.

## Launch

```bash
make data      # once: the starter CSVs in data/raw/ (shared by hand, decision #11)
make ui        # http://localhost:8502   (LLM_PROVIDER=bedrock in .env for the live assistant)
```

Offline (default, and after the AWS account closes) the assistant is the deterministic analyst: the screen says
"Offline: limited answers" and explains what it can and cannot understand. Nothing pretends to be an AI.

## Architecture

```
interface/app.py            sections Welcome · Your profile · Your results · Assistant; last error boundary
interface/core/             pure Python, no Streamlit, unit-tested
  validation.py             typed text → value or a short message; limits from extractor.NUMBERS / ENUMS / LISTS
  questions.py              the questions: wording, ⓘ help, example, required / optional / advanced, visible_if
  wizard.py                 visible questions, step checks, cross-checks, progress, answers ↔ engine profile
  services.py               the ONLY door to the engine (pipeline, explainer, extractor, analyst, charts);
                            UserError (shown) vs InternalError (logged in logs/interface.log, short message + ref)
interface/ui/theme.py       palette Neige / Gris saule / Gris antarctique / Érable, CSS, chat bubbles, animation
interface/ui/components.py  field(), notice(), card(), metric(), steps_bar(), thinking() (cleared in a finally)
interface/views/            profile.py (wizard + review), results.py, chat.py (conversation)
```

Rules: the interface computes no financial number (everything comes from `services`); a value reaches the engine
only after it passed `validation`; a Python traceback never reaches the screen.

## The assistant

`chat.py` → `services.ask_analyst` → `analyst.ask(question, res, profile, history=…)`.
- **Live** (Bedrock): the Strands agent sees the last 6 turns; every number it writes must come from a tool result it
  obtained for this answer (code-checked, else replaced by the deterministic answer, and said).
- **Offline**: follow-ups reuse the last asset or share ("and with 5%?", "what about NVDA?", "and with a 10-year
  horizon?"); concepts come from a written glossary (no numbers); "explain my results" calls `results_overview`.
- Questions are queued, answered in order; the thinking indicator always clears; failures show one sentence.

Tests: `tests/test_interface_*.py` (`make test`). Test report: `interface/TESTING.md`.

## Next: voice
A voice conversation with the assistant (speak your situation or a question, hear the answer): microphone input
(`st.audio_input`) → speech-to-text (Amazon Transcribe) → the same Extractor / Analyst, checked by the same code →
the text answer read aloud (Amazon Polly). Not built yet: it needs AWS after the event account closes.
