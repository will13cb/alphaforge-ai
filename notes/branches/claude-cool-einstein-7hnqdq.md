# Branch claude/cool-einstein-7hnqdq: interface visual directions

## Done
- Static mockups of the guided interface (`interface/mockups/`): 3 directions x 2 screens (Welcome, Results).
  A editorial light (Wealthsimple direction), B dark (Kraken direction), C light console with sidebar (Kraken Pro).
  No emoji, Inter font, illustrative numbers only (not from results.csv, not for the pitch).

- Directions A and B ported into the guided interface (`interface/ui/theme.py`): light editorial and dark,
  "Dark mode" switch in the sidebar (`st.toggle`, session key `dark_mode`), CSS injected at the top of each run.
- Engine charts recoloured per mode in the interface only (`theme.style_chart`, `ui.chart`); `src/dh/` untouched.
- Emoji and symbol glyphs removed from the interface: page icon, tabs, sidebar, status marks (now words: Passed,
  To know, Not met), pros/cons (For / Against).

- iPhone pass (checked in iPhone 14 emulation, both modes, full flow with data): section tabs at the top on phones
  (`app.mobile_nav`, hidden on wider screens), 16 px fields (no iOS zoom), 44 px tap targets, metrics three in a row,
  review rows and step buttons laid out for a phone (Continue first), Streamlit progress bar and chat input in the
  mode's colours, safe-area padding, new section or step opens at its top (`scroll_to_top_on_change`).

## Next
- Check the results and assistant pages in both modes with the market data installed (not available here).
- `app/app.py` (jury demo) still has the old look and the maple-leaf icon; untouched.

## Decisions
- Light = Wealthsimple-like editorial, dark = Kraken-like; user's choice, both kept with a switch.

## Contract changes
- None.

## How to check
`make ui`, then the "Dark mode" switch in the sidebar. Mockups: `python interface/mockups/build.py && NODE_PATH=$(npm root -g) node interface/mockups/shoot.js`
- (Sun evening) Mockups removed from the submission tree; they remain in git history (commit bec7e89).
