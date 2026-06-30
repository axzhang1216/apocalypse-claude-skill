### Task 3 report

- Added an explicit two-way permission choice before every Apocalypse-triggered launch:
  - `Standard permissions`
  - `All permissions`
- Applied the prompt to both resume and new-session paths.
- Kept provider-specific dangerous flags correct:
  - Claude: `--dangerously-skip-permissions`
  - Codex: `--dangerously-bypass-approvals-and-sandbox`
- Made cancel/back from the permission picker non-destructive:
  - cancel resume -> return to the current browsing flow
  - cancel new session -> stay in the current project session list

### Verification

- `python -m py_compile skills_apocalypse/apocalypse.py`
- direct command-builder assertions for standard/dangerous Claude/Codex commands
- monkeypatched launch flow assertions:
  - `dangerous launch flow OK`
  - `standard launch flow OK`
- CLI surface still intact:
  - `python skills_apocalypse/apocalypse.py --help`

### Residual notes

- The permission chooser itself is interactive, so full UI confirmation still needs manual clicking in a real terminal window if we want to visually inspect the menu.
