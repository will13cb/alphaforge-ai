# Branch design docs

One doc per branch: `notes/branches/<branch-name>.md`, with `/` replaced by `-`
(`lane/agents` → `lane-agents.md`, `lane/market-data` → `lane-market-data.md`).
Each file name is unique, so merging to `main` never conflicts; on `main` this folder is the record of what each
branch did. Example: `lane-agents.md`.

Create it when you create the branch. Update it before each merge. Decisions still go in `notes/decisions.md`
and the `CLAUDE.md` decisions log; the branch doc links to them by number.

## Template

```markdown
# lane/<name> — <owner>

**Goal:** one sentence.
**Status:** in progress / ready to merge / merged (date, commit)

## Done
- what's built, with file paths

## In progress / next
- …

## Decisions made here
- one line each, with the number in notes/decisions.md (#9 …)

## Contract changes
- fields added or changed in notes/contract.md (the other lane must know before the merge)

## How to check it
- command to run (make test, make scenarios, make check …) and what you should see

## Open questions / blocked on
- …
```

"Contract changes" matters most: both lanes work in parallel, and that's where a field change gets noticed
before the merge, not after.
