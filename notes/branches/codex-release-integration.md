# codex/release-integration

**Goal:** integrate completed activity and risk work with current main, preserving voice, accessibility and existing-portfolio review; close release-blocking regression gaps.
**Status:** integrated and verified for main (2026-11-15); user authorized merging suitable branches into main.

## Done
- Integrated feat/live-analysis-redesign with current main, retaining the current theme API, accessibility controls, mobile navigation and existing portfolios.
- Added Activity navigation, real trace observers, loaded-universe search and per-session jury results; no fabricated progress or storage claims.
- Profile review explains analysis-record storage. Voice documentation reflects the implementation already on main.

- Integrated the risk branch; retained existing portfolio features and moved the research dividend warning to G19 so G18 remains the consistency check.

## In progress / next
- Initial combined suite: 358 passed, 4 skipped, 2 failures; fixed existing-review loss-model mismatch and a SciPy-version-dependent failure test. Focused integration regression: 44 passed.
- Missing chart data is now caught without terminating Streamlit.
- Close explanation grounding, final acceptance and missing-data error-boundary gaps.
- Recheck remote main before publishing; preserve concurrent work.

## Decisions made here
- Preserve current cream/ink and violet themes; adopt the activity behaviour without replacing the newer interface.
- Keep experimental optimizers, accounts/tax exploration, incomplete income-target workflow and unsourced composite holdings out of main.

## Contract changes
- Optional on_step observer on pipeline.run and interface services.run_analysis; financial results do not depend on observer success.

## How to check it
- LLM_PROVIDER=mock python -m pytest -q
- Check voice controls, existing portfolio, theme and Activity navigation together.
- Live AWS speech, data and trace smoke tests require event credentials and are not claimed by offline tests.

## Open questions / blocked on
- Final data snapshot and live AWS smoke test remain deployment prerequisites.

## Release hardening
- Added bounded metric/sign checks for common financial percentage wording in Analyst and Critic; arbitrary prose remains outside what numeric validation can prove.
- Every Critic revision must also pass all blocking C-F checks. Existing reviews use the same simulated loss model as proposals.
- Unknown equity ETF holdings disclose incomplete assessment rather than assuming 100 verified holdings; scenario expectations reflect the disclosure.
- Analyst follow-ups and tool results are saved with a parent run reference.
- Targeted hardening regression: 53 passed. No AWS credentials available in this environment; Bedrock cache warming and live speech/storage verification remain operator checks.

## Final-data verification
- Rebuilt the 31-asset starter window with the official script and fetched issuer SPY holdings. Raw data remains ignored.
- Logged 55 final persona evidence rows against source commit 9a2febb.
- Preserved concurrent main updates through 20f4e66, including jury chart styling and the revised video script.

## Final checks
- Full combined suite on rebuilt starter data + issuer SPY holdings: **375 passed, 1 skipped**, no warnings (146.85 s).
- Voice/accessibility/activity regression with unhandled thread warnings treated as errors: **16 passed**.
- Fatal Python lint, compile checks and git diff whitespace checks passed.
- Preserved concurrent main through 18bab8d.
- No optimizer, tax exploration, dividend-target skeleton or unsourced composite branch merged.
