### Task 2 report

- Rebuilt `skills_apocalypse/apocalypse.py` from the last committed Claude-only version after the interrupted worker left the file syntactically broken.
- Added provider selection via `get_provider("claude" | "codex")`.
- Wired Codex-specific loaders and transcript preview:
  - `load_codex_projects`
  - `load_codex_recent_sessions`
  - `parse_codex_transcript_preview`
  - `update_codex_workspace`
- Made the recent/project/session/detail flows provider-aware.
- Added `--codex` so the launcher can browse Codex CLI history instead of Claude history.
- Kept launch semantics aligned with the brief:
  - Claude resume: `claude --resume <id> --dangerously-skip-permissions`
  - Claude new session: `claude --dangerously-skip-permissions`
  - Codex resume: `codex resume <id>`
  - Codex new session: `codex`

### Verification

- `python -m py_compile skills_apocalypse/apocalypse.py`
- provider smoke:
  - `providers OK Claude Codex`
- launch command smoke with monkeypatched `launch_in_terminal`:
  - `launch commands OK`
- real Codex cache/list verification with escalation:
  - `python skills_apocalypse/apocalypse.py --codex --list`
  - succeeded and produced Codex project/session JSON

### Residual notes

- Codex project/session content quality still depends on the cache module from Task 1, including how goals are derived from Codex transcripts.
- Permission mode prompting is intentionally not implemented here; that belongs to Task 3.
