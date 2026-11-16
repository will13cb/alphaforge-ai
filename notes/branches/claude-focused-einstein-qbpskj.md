# claude/focused-einstein-qbpskj — Joud

**Goal:** fix four display bugs and one assistant bug seen on the hosted app (Streamlit 1.67, which the host installs from `streamlit>=1.50`).
**Status:** ready to merge

## Done
- **Crash on language switch** (`ValueError` in `interface/app.py` `mobile_nav`). Recent Streamlit sends a choice back
  as its displayed label; after Français ⇄ English that label is in the other language and came back as plain text
  ("Accueil" for "Welcome"). `src/dh/i18n.py` now maps such a label back to its option for every choice widget and
  rewrites the choice on a language change so the browser redraws it (the selection also went blank before).
  `interface/app.py` falls back to the first section on an unknown value.
- **Multiselect items black on black** and **chat avatars as empty squares** (`interface/ui/theme.py`): the new
  Streamlit markup (`span[data-tag]`, icon-font avatars, react-aria select boxes) was not covered by the CSS. Old
  selectors kept, new ones added; dropdown lists also follow dark mode again.
- **Pipeline graph text outside its boxes** (`interface/ui/flow.py`): labels are translated in the graph, a long
  title wraps on two lines, a subtitle shrinks to fit, the Guardian's box grows to its text.
  French labels added to `src/dh/i18n_fr.py`.

- **Assistant answered "I'm not sure I understood" to a strategy name** ("Orientation croissance"), in English in
  the French app (`src/dh/agents/analyst.py`). A text not phrased as a question is now read as a question about what
  it names: one of the client's strategies (English or French name) → that strategy's results; a notion or an asset
  typed alone → its definition or its facts. A text with no clear French or English words is answered in the app's
  language. Only a text that names nothing we know still gets the "not sure I understood" help.
  The live agent is told the same, and a reply that is plain text instead of JSON is kept (its numbers are still
  checked by code) instead of falling back to the offline assistant. `PROMPT_VERSION` is unchanged on purpose: the
  committed demo answers in `cache/analyst/` stay replayable.

## In progress / next
- The hosted app is built from `will13cb/alphaforge-ai`, which holds graph labels this repository does not have.
  These fixes reach the hosted app only once they are synced there.

## Decisions made here
- None (bug fixes).

## Contract changes
- None.

## How to check
- `python -m pytest -q tests/test_flow_graph.py tests/test_i18n.py tests/test_interface_app.py tests/test_analyst.py`
- `make ui`, switch Français ⇄ English on any page: no error, the chosen answers stay selected.
