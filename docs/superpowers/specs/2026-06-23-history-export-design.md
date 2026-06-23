# Apocalypse History Export — Design Spec

**Date**: 2026-06-23
**Status**: Approved (awaiting implementation plan)

## Context

Apocalypse currently analyses every Claude Code session via `workspace_init.py`:
each session is summarised (goal, outcome, category, key decisions) and stored
in `~/.claude/apocalypse/workspace.json` under `projects[*].analyzed_sessions`.

It also runs an opt-in `--extract-points` step that uses Haiku to group each
session's user messages by topic and slice the transcript into
**discussion-decision pairs** (points). Each point carries `topic`, `decision`,
`messages[]` (with optional `summary` for long assistant replies), `ts`, and
`related_to` cross-references.

**The gap**: those `point.messages` only live inside `workspace.json`. When a
future Claude session opens the same project, it has no offline, in-project
record of what was previously discussed or decided. The current state of the
art is "re-derive from transcripts" — slow, costly, and lossy.

**The goal**: write those existing point.messages to disk inside the project
folder, in a form future Claude can read directly to recall prior discussions
and decisions, and tell future Claude (via the project's CLAUDE.md) that
this directory exists and what it's for.

## Design Decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Storage location | `<project-cwd>/.apocalypse/` (hidden subdir) |
| File granularity | One md per session, internal `##` sections per point |
| Trigger | Runs inside `update_workspace` after `--extract-points` |
| CLAUDE.md writing | Per-project, in a marked block (start/end tags) |
| Default behaviour | **opt-out** — on by default, can be disabled in config |
| Safety guardrails | install notice + config toggle + marked block isolation + auto `.gitignore` |

## Architecture

### Code organisation

All export logic lives in `skills_apocalypse/workspace_init.py` alongside the
`extract_points()` it depends on (single responsibility, no cross-module
coupling needed). New surface:

- `load_config()` / `save_config()` — read/write `~/.claude/apocalypse/config.json`
- `export_history()` — the main export function
- `--export-history` CLI flag for standalone invocations
- Hook into existing `update_workspace()` flow: incremental → extract-points
  (if needed) → export-history

### Configuration

`~/.claude/apocalypse/config.json`:
```json
{
  "export_history": true,
  "max_md_kb": 64,
  "old_kept": 3
}
```

- `export_history` (default `true`) — master switch
- `max_md_kb` (default `64`) — soft cap per session md before rolling
- `old_kept` (default `3`) — keep `.old.1.md` through `.old.3.md`; delete
  `.old.4.md` and higher (this rolling happens automatically when main md
  exceeds cap)

### Flow inside `update_workspace()`

```
1. (existing) incremental session analysis
2. (existing) extract-points, skip if all points have messages
3. (new) if config.export_history is true:
   a. for each project in workspace:
      - resolve cwd from project.cwd
      - render .apocalypse/<date>-<sid8>-<slug>.md from all its points
        (full re-render every time so re-extraction changes propagate)
      - apply rolling: split if md > max_md_kb (only deletes its own .old.N)
      - update project CLAUDE.md marked block (idempotent replace or append)
      - ensure .gitignore contains .apocalypse/ (idempotent append)

Note: v1 does **not** auto-prune session md files whose sessions were
deleted from workspace.json. Conservative — never deletes files we didn't
write in the current run. Users can `rm` manually or opt into a future
`--prune` flag.
```

If `export_history` is `false`, step 3 is skipped entirely.

### File layout inside each project

```
<project-cwd>/
├── .apocalypse/
│   ├── README.md                        # one-page human/machine description
│   ├── 2026-06-15-a1b2c3d4-init-react.md
│   ├── 2026-06-15-a1b2c3d4-init-react.md.old.1.md   # rolled out
│   └── 2026-06-18-e5f6g7h8-debug-extract.md
├── .gitignore                           # contains ".apocalypse/"
└── CLAUDE.md                            # contains APOCALYPSE-HISTORY block
```

### Session md naming

`<YYYY-MM-DD>-<sid8>-<slug>.md` where:
- `YYYY-MM-DD` = first user message date (`point.ts[:10]`)
- `sid8` = first 8 chars of `session_id`
- `slug` = slugified first point topic, max 40 chars

### Markdown format per session md

```markdown
# <project.user_goal — first sentence>

**Project**: <project.title>
**Session ID**: `<session_id>`
**Goal**: <session.user_goal>
**Messages**: <msg_count>
**Exported**: <UTC timestamp at export time>

---

## Discussion 1: <point.topic>

**Decision**: <point.decision>

**Related**: Discussion 2 (or "(none)")

### User
> <message text or summary>

### Assistant
> <message text or summary>

---

## Discussion 2: ...
```

- Title `#` uses session `user_goal` (semantic, lets Claude find by meaning)
- `##` per point, titled by `topic` (searchable)
- `### User` / `### Assistant` with blockquote for clean rendering
- Prefer `summary` over `text` when present (Haiku pre-summarised)
- `**Related**` maps `point.related_to` ids back to "Discussion N" in this file

### Rolling algorithm

Render strategy is **always full re-render of the main md**: each
`update_workspace` rewrites the main md with all of the project's current
points (so changes from re-extraction propagate). The rolling happens when
the rendered main md exceeds the size cap.

Per session md, after rendering:

1. Compute size of the just-rendered main md bytes.
2. If `<= max_md_kb * 1024` → write to disk. Done.
3. If `> max_md_kb * 1024`:
   a. Read existing siblings: `<basename>.old.1.md`, `<basename>.old.2.md`, …
   b. Shift them up by one (`.old.1` → `.old.2`, etc.), skip-on-conflict-and-warn
   c. Move current `<basename>.md` → `<basename>.old.1.md` (full prior content)
   d. Delete any sibling with index `> old_kept`
   e. Write the **full** newly-rendered main md (next update will roll again
      if it keeps growing)
4. In all cases, write atomically via `.tmp` + `os.replace`.

### CLAUDE.md marked block

Append or replace in each project's `CLAUDE.md`:

```markdown
<!-- APOCALYPSE-HISTORY:START -->
## Project History (Apocalypse)

此项目过往的 Claude Code session 已自动归档到 `.apocalypse/`，按"讨论/决策"
分章节组织（每 session 一个 md）。当用户问到本项目之前做过什么、决定过什么、
讨论过什么时，**先读** `.apocalypse/*.md`（不带 `.old` 后缀的）再回答。

- 主文件（活跃）= `.apocalypse/*.md`（无 `.old` 后缀）
- 历史滚动文件 = `.apocalypse/*.old.*.md`（默认不读，必要时翻）
- 目录说明 = `.apocalypse/README.md`

**不要修改** `.apocalypse/` 下的文件——下次 `update workspace` 会被覆盖。
<!-- APOCALYPSE-HISTORY:END -->
```

Update rules:
- Read `CLAUDE.md` if exists, else create with just this block
- Locate `APOCALYPSE-HISTORY:START` … `:END` (regex)
- **Found** → replace just that range (preserve everything else verbatim)
- **Not found** → append to file with one blank line separator
- Write atomically via `.tmp` + `os.replace`

### `.gitignore` update

Same idempotent pattern: ensure `.apocalypse/` line is present (regex
`^\.apocalypse/?$` in `re.M` mode). Create `.gitignore` if missing.

Always try to update `.gitignore` first, before writing any `.apocalypse/`
file, so that a subsequent crash doesn't leave md files untracked.

## Error Handling

| Failure | Behaviour |
|---|---|
| `cwd` missing / unwritable | Skip project, `print` warning, continue |
| `point.messages` empty for a session | Skip that session's md; include the project in README so it's not silently absent |
| `.apocalypse/` creation fails | Skip all writes for that project; do not partial-write |
| `.old.N.md` rename collision | Skip that file, warn, continue |
| `.gitignore` no write permission | Silent skip — md files still go out |
| `CLAUDE.md` no write permission | Silent skip — md files still go out |
| `extract-points` Haiku call fails | **Propagate** — export can't run on empty data; tell user |
| `workspace.json` write fails | **Propagate** — atomic save already in place; should not happen |

Workspace data is read-only during export. All writes are atomic via
`.tmp` + `os.replace` (existing `save_workspace` pattern).

## Safety Guardrails (the four user-selected ones)

1. **Install notice**: `install.sh` prints a clear line at the end telling the
   user what will happen and how to disable.
2. **Config toggle**: `~/.claude/apocalypse/config.json` with
   `export_history: true` (default). One-line edit to disable.
3. **CLAUDE.md marked block isolation**: block is bounded by sentinel
   comments; update logic only touches that range, never other content.
4. **Auto `.gitignore`**: every project's `.gitignore` is updated to include
   `.apocalypse/`, so full chat logs can't be accidentally committed.

## Testing (manual, no test framework in repo)

1. **happy path** — `bash install.sh` clean → run `--export-history` → spot
   check 3 projects for `.apocalypse/` contents, CLAUDE.md block, .gitignore
2. **rolling** — manually `dd` 70 KB of bytes into one md, re-run → confirm
   it splits into `.old.1.md` + fresh smaller main md
3. **opt-out** — set `export_history: false` → run update workspace → confirm
   no `.apocalypse/` writes
4. **permission refusal** — `chmod 000` one project root → confirm others
   export normally, that one skipped with warning
5. **stale session cleanup** — v1 explicitly does NOT auto-prune session
   md files for removed sessions. Verify by deleting a point from
   workspace.json, re-running, and confirming the old md is still present
   (this is intentional v1 behaviour; document the manual `rm` workaround)

## Non-goals (YAGNI)

- Cross-session related_to rendering (point.related_to already mapped within
  each session's md)
- Full-text search index (Claude reads md directly)
- Web UI for browsing archives (workspace.html already shows 3D graph)
- Multi-language handling (Haiku summarises in source language; md follows)
- Diff-based incremental render (full render + rolling is good enough)

## Performance Estimate

37 projects × ~50 sessions × ~10 points × ~5 messages = ~10k entries to render.
Plain string templating, well under 1 second wall time on a modern laptop.
No new Haiku calls (we only export what's already in `point.messages`).

Disk usage: with 64 KB cap and 3 old siblings, max 256 KB per session. 50
sessions × 256 KB = ~13 MB per project worst-case. Fine.