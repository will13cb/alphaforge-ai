# interface — Joud (new GUI on top of the existing engine; agreed with Will before merging)

**Goal:** a guided, plain-language (English) application that any adult can use, with a step-by-step profile
form, validated inputs, results shown essentials-first, and a conversational Analyst. It reuses the engine as is.
**Status:** merged into main on Sun Nov 15 with Will's OK (after the post-audit branch, #31–#34). On main: the cards show what set each split (#33), texts use the data window (#31); `test_analyst` 450 000 $ fixed (missing Bank of Canada rate no longer crashes). Tomorrow: Will runs `make warm` from main, commits `cache/`, then `make backup` before 11:00.
Tonight's deliverable stays `app/app.py` on `main`: this branch is not merged before it is tested and Will agrees.

## Step 1 — Audit: what the interface reuses (no new business logic)

| Need | Existing function (reuse as is) | Note |
|---|---|---|
| Run an analysis | `pipeline.run(profile)` → limits, strategies, checks, Guardian, Critic, trace | raises `SystemExit` if the CSVs are missing → caught by the service layer |
| Client text | `explainer.add_to_trace(res, profile)` | demo cache offline, template fallback |
| Free text → profile | `extractor.extract(text)`, `extractor.questions(missing)` | already asks for missing essentials |
| **Field types and limits** | `extractor.NUMBERS` (min, max), `extractor.ENUMS`, `extractor.LISTS`, `extractor.SECTORS`, `rules.ESSENTIAL_FIELDS` | **the real business limits**: the form validates against these, nothing invented |
| Question wording | `extractor.QUESTIONS` (English), `notes/intake-form.md` (Will's step-by-step form) | French wording to write, same fields |
| Follow-ups | `analyst.ask(question, res, profile)`, `analyst.parse`, `analyst.short` | see "Analyst: what must change" |
| Charts | `market_charts.*`, `portfolio_charts.*` | Altair, already used by the app |
| Checks summary | `checks.summary`, `trace.ICON` | |
| Evidence on AWS | `tracestore.save_run` | the app doesn't call it yet |
| Demo clients | `scenarios.DEMO_PROFILES`, `personas.DISCLAIMER` | |

**To adapt (outside the interface):**
1. **Analyst conversation.** `analyst.ask` answers one question with no memory. A conversation needs: (a) the
   previous turns passed to the Bedrock agent; (b) in the offline analyst, a carried-over context ("and with 5%?"
   reuses the last asset); (c) two new deterministic abilities: explain a concept from a **written glossary** (no
   invented numbers) and explain the client's **own results** from the run. Without Bedrock, the offline analyst
   stays pattern-based: the interface must say so ("mode hors ligne : réponses limitées"), never pretend.
2. A French version of the client-facing texts the interface shows (limit reasons, check reasons are English today).
   Plan: French labels in the interface; engine texts shown as they are in an "details" expander until translated.

## Step 2 — Architecture

```
interface/                      new, self-contained Streamlit app (does not touch app/app.py)
  app.py                        entry point: 4 sections (Accueil · Mon profil · Mes résultats · Analyst)
  core/                         pure Python, no Streamlit, fully unit-tested
    validation.py               parse + check one value: int, decimal, %, money, date, choice; French messages;
                                bounds taken from extractor.NUMBERS / ENUMS (single source)
    questions.py                question catalog: id, step, French label, help (ⓘ), example, type, required /
                                optional / advanced, default, visible_if (depends on earlier answers)
    wizard.py                   state machine: steps, visible questions, progress, back / next / reset, what is
                                missing before "Lancer l'analyse"
    services.py                 the ONLY door to the engine: run_analysis, ask_analyst, extract_text; catches
                                every exception → UserError (shown) or InternalError (logged, short message);
                                technical log in logs/interface.log
  ui/
    theme.py                    palette tokens + CSS (Neige, Gris saule, Gris antarctique, Érable)
    components.py               reusable: field(), notice(), card(), metric(), nav(), thinking()
  views/
    profile.py                  the step-by-step form
    results.py                  essentials first, details in expanders, limits/warnings shown
    chat.py                     Analyst conversation (chat_message, chat_input with Enter, history, thinking)
  README.md                     architecture + how to launch (make ui)
tests/test_interface_*.py       validation, wizard, services (offline), AppTest end-to-end flows
```

- **Rules:** the interface computes no financial number; everything shown comes from `services` (engine results).
  Errors from the interface never reach the engine: values are validated before any call, and every call is inside
  one error boundary.
- **Palette (proposal, to confirm):** Neige `#F7F9FB` (background) · Gris saule `#A3AE9F` (panels, separators) ·
  Gris antarctique `#4E5D6C` (secondary text, borders, navigation) · Érable `#B5432A` (primary buttons, selection);
  errors `#B42318` in small text. Contrast of text on Neige checked (≥ 4.5:1).
- **Analyst UI:** messages user/Analyst distinct, input at the bottom (Enter sends), history kept in the session,
  "Nouvelle conversation" button, thinking indicator shown from send to answer and always cleared (try/finally),
  answers in Markdown (titles, lists, tables, `$…$` formulas), charts when a tool returns asset or portfolio data,
  each answer showing whether it came from Bedrock or the offline analyst, and its code-check status.

## Decisions (Joud, Sun Nov 15) — decision #36
1. New app in `interface/`; `app/app.py` untouched.
2. English (the team's language for deliverables); the Analyst still answers French questions in French.
3. Assistant after AWS closes: honest offline mode ("Offline: limited answers"), no other LLM provider.
4. Prototype now, merge only after tests and Will's OK; not part of the 23:59 submission.

## Done
- `interface/` (core, ui, views, app), `make ui` (:8502), `interface/README.md`, `interface/TESTING.md`.
- Analyst conversation (`analyst.ask(..., history=)`): last 6 turns in the Bedrock prompt and in the cache key;
  offline context ("and with 5%?", "what about NVDA?", "and with a 10-year horizon?"), glossary, `results_overview`.
- Tests: `tests/test_interface_{validation,wizard,services,app}.py` (41) + 1 in `test_analyst.py`.

## Contract changes
- None to `notes/contract.md`. `analyst.ask` gains an optional `history` (default unchanged); new tool
  `results_overview` (read-only, numbers from the run). `PROMPT_VERSION` analyst-v3 (old cache entries not reused).

## How to check
`make test` · `make ui` → "Try with an example client" → "Run the analysis" → "Ask the assistant".

## Next
- Will: review; decide whether the jury demo links to it. Bedrock `--save-demo` runs for the assistant's examples.
- Translate the engine's limit / check reasons if a French interface is wanted later.

## Notes for other agents
- Branch created from `main` at `a66f88b`. Nothing outside `interface/`, `tests/test_interface_*`, `notes/` and the
  Analyst's conversation support will change here.

## Sun evening — evidence and demo cache (Joud, to confirm with Will)
- **Done:** `services.run_analysis` saves each run's trace via `tracestore.save_run` (S3, local copy if S3 fails;
  a store error never blocks the client), 2 tests. `make warm` (`scripts/warm.py`): every Bedrock call the demo needs
  (Critic + Explainer × 4 demo clients, Extractor on the app's sample text, Analyst × suggested questions × 4 clients
  = 41 calls), copies valid answers to `cache/*/`; `DRY=1` lists them. Tested dry only (no Bedrock here).
  Draft tech-doc market-data sections: `notes/techdoc-market-data.md`.
- **Next (Will, Mon before 11:00):** `make warm` with `LLM_PROVIDER=bedrock`, commit `cache/`, then `make backup`.
- **Limits:** a suggestion asked later in a conversation has another hash (history) → live call, not the cache.
  `make warm`/`Makefile` are Will's lane: his OK needed. 1 analyst test fails without `data/raw` (already before).
