# codex/release-stability — Will

**Goal:** integrate release-ready fixes and sync the selected release to alphaforge-ai.
**Status:** ready after regression checks

## Done
- Readable assistant merged through PR #15.
- Submission-consistency branch is already in main; retain it.
- Apply the isolated zero-loss fix from commit `8c8c3773f98efd43f954aced7720a1f424743cba` on `dividende_cible`: accept a zero loss threshold in the loss model; handle zero company caps without division by zero.
- Include its five regression cases: no-loss clients get a fail verdict with reasons, existing holdings remain reviewable, and a zero company cap fails the rule rather than crashing.

## Branch selection
- Already incorporated: accessible voice, voice quality, KYC, product catalogue, existing portfolio, quantitative audit and earlier interface work.
- Excluded `dividende_cible` research feature: missing profile/explainer/UI integration; use only its isolated crash fix.
- Excluded `optimisation-markowitz` and `interface` optimizer experiments: main deliberately keeps them out of the demo.
- Excluded `exploration`: tax parameters unverified and engine incomplete.
- Excluded `claude/clever-shannon-ociuzg`: fund-of-funds implementation blocked on real issuer weights.
- Excluded `claude/wizardly-maxwell-52iwnb`: broad opt-in safety scaffolding needs policy choices and integration review.
- Excluded `claude/affectionate-clarke-jqdfg6`: changes allocation policy, defensive baskets and strategy ordering; requires regenerating final-data results, caches and deliverables; longer-horizon policy remains unresolved.
- Leave all source branches intact.

## Contract changes
- None. A zero accepted loss remains valid input; the result is an explained rejection when no portfolio fits.

## How to check
- `python -m pytest -q tests/test_agents.py tests/test_portfolio.py tests/test_risk_loss_model.py`
- Full offline suite and syntax checks before publishing.
- Sync source contents onto the public repository's own parent commit; do not import private repository history.

## Next / limits
- Live AWS speech, refreshed demo caches and final-data validation remain operator checks; no AWS credentials or S3 data are changed here.
