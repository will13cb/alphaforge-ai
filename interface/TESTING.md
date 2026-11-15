# Interface test report (Sun Nov 15, branch `interface`)

**Result:** 183 tests pass offline (`make test`), of which 41 new for the interface and 1 new for the Analyst.
Visual check with Playwright (Chromium) at 1280 px and 390 px (phone): no page error, no horizontal scroll.

## Automated tests

| File | What it covers | Tests |
|---|---|---|
| `test_interface_validation.py` | numbers as people type them (`10 000`, `10,000`, `1,5`, `10k`, `$5,000`), non-numbers, bounds from `extractor.NUMBERS`, messages (empty, decimals, out of range), money ≥ 0, %, choices, names (no `<script>`, ≤ 40 chars), dates and ranges, requested position | 21 |
| `test_interface_wizard.py` | every essential field asked and required; schema match; conditional questions (target, withdrawals, experience, advanced); a step blocks until fixed; hidden answers ignored; incompatible combination (nothing to invest); % ↔ fraction; full answers → complete profile; demo clients round-trip | 8 |
| `test_interface_services.py` | incomplete profile refused before the engine; missing data → plain message; `SystemExit` → user message; crash → reference shown, traceback only in the log; empty / long questions; history passed; analyst crash; free text; offline mode label | 7 |
| `test_interface_app.py` (AppTest) | navigation without results; errors only after "Continue", gone once fixed; Back keeps answers; conditional field appears; reset needs confirmation; full flow demo → review → results → assistant; context kept across turns; unclear question; very long question; new conversation; two questions queued; analyst failure shown as a message; thinking indicator cleared | 5 |
| `test_analyst.py` (+1) | conversation context, glossary, results overview, unclear question | 1 |

## Problems found and fixed

| # | Found by | Problem | Fix |
|---|---|---|---|
| 1 | Analyst check | "what about NVDA?" after "and with 5%?" lost the share: context read only the last raw question | context resolved through the conversation (`with_context` recursive, 6 turns) |
| 2 | Analyst check | "10-year horizon" not read (hyphen) | `_YEARS` accepts `10-year` |
| 3 | `test_analyst` | mocked agent without the new `history` argument | test mock updated |
| 4 | services test | log file not created when pytest had its own handlers on the logger | our handler is marked and looked up by marker |
| 5 | AppTest | thinking indicator "found" after clearing: the CSS contains the class name | tests look for `role="status"`, the indicator's own attribute |
| 6 | Screenshot | grey placeholders ("45", "Robert") looked like answers while the field was empty and in error | placeholders removed; the example stays in italics under the field |
| 7 | Screenshot | the user's chat bubble overflowed to the right | bubble `width: fit-content; max-width: 85%` |
| 8 | Screenshot | the step bar was hidden under Streamlit's header | top padding 4.5 rem |
| 9 | Screenshot | what-if chart bars overlapping, then squashed | one encoded base, height passed to Streamlit |
| 10 | Screenshot | the same disclosure shown three times on a strategy card (with/without check id, then as a notice) | shown once (`unique`, notices skip what the cons already say) |
| 11 | Screenshot | footnote "* Without assuming…" rendered as a bullet | asterisk escaped |
| 12 | Screenshot | disclaimer repeated under every chat answer | once in the page footer and the sidebar |

## Not covered / limits

- Offline, the assistant understands a fixed set of question types; it says so instead of guessing.
- Live Bedrock conversation not tested here (needs AWS): same code path as the single-question Analyst (#35), plus
  the last 6 turns in the prompt; numbers still code-checked.
- Screen reader: roles and `aria-live` on the indicator and errors, contrast ≥ 4.5:1 on text; not tested with a
  real screen reader.
- French: the interface is in English (team choice); the Analyst answers French questions in French.
