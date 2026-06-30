# Codex Dashboard Tab — Design Spec

**Date:** 2026-06-30
**Status:** Approved (brainstormed)
**Scope:** Minimal — historical browse only

## Goal

Add a `Claude | Codex` tab toggle to Apocalypse's web dashboard (`dashboard.html`).
The Codex tab lists every Codex CLI session found under `~/.codex/sessions/` and
shows its full transcript in the existing right-side detail pane.

## Confirmed requirements (from brainstorming)

1. Add a Claude/Codex tab toggle in `dashboard.html`.
2. Codex tab = **historical browse** of all Codex sessions (read-only).
3. Click a Codex session → render its transcript in the **shared** detail pane.
4. **No live status** (Codex has no Apocalypse hooks), **no resume button**,
   **no heatmap**, **no search** on the Codex tab.

## Non-goals (YAGNI)

- Real-time green/yellow/grey status for Codex (would require Codex hooks).
- "Open in terminal" / `codex resume` button.
- Codex full-text search endpoint.
- Counting Codex sessions toward the "Vib Coding 活跃度" heatmap.
- Deleting Codex records from the dashboard.

---

## Codex data sources

Codex CLI (OpenAI, v0.134) stores data in `~/.codex/` (`CODEX_HOME`).

- **`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`** — one file per session
  (257 files on this machine). Each line is a JSON record with a `type`:
  - `session_meta` (exactly 1 per file) — `payload` has `id`, `cwd`,
    `timestamp`, `originator`, `cli_version`, `source`.
  - `response_item` (the conversation) — `payload.type` ∈ `message`
    (`role` user/assistant/developer), `reasoning`, `function_call`,
    `function_call_output`, `custom_tool_call`, `custom_tool_call_output`.
  - `event_msg`, `turn_context` — not needed for browsing.
- **`~/.codex/session_index.jsonl`** — `{id, thread_name, updated_at}` for a
  subset of sessions (96 of 257). Used only as a title hint.

Filename pattern embeds both a timestamp and the session id:
`rollout-2026-06-22T11-53-59-019eed76-b155-7f40-a0fc-a3da78815170.jsonl`

### Content-item schema (verified)

`message.payload.content[*]`:
- user → `{type:"input_text", text}`
- assistant → `{type:"output_text", text}`
- developer → `{type:"input_text", text}` (system instructions — skipped)
- (possibly image items with no `text` — skipped)

→ **Extraction rule:** collect `.text` from any content item that is a dict
with a `text` key. Uniform across roles.

---

## Backend design (`server.py`)

Two new endpoints mirroring the Claude ones. Both return the **same message
schema** as `parse_conversation()` so the frontend renders them unchanged.

### Constants

```python
CODEX_DIR = Path.home() / ".codex"
CODEX_SESSIONS_DIR = CODEX_DIR / "sessions"
CODEX_INDEX_FILE = CODEX_DIR / "session_index.jsonl"
CODEX_TRANSCRIPT_LIMIT = 200
```

### `GET /api/codex/sessions`

Scan `CODEX_SESSIONS_DIR/**/*.jsonl`. For each file, read **only the first
`session_meta` line** (cheap — no full parse) to get `id`, `cwd`, `timestamp`.
Build a `{id: thread_name}` dict from `CODEX_INDEX_FILE` (loaded once per
request) for title hints.

Returns a list (sorted by `last_ts` desc, capped at `CODEX_TRANSCRIPT_LIMIT`):
```json
{
  "session_id": "019eed76-...",
  "cwd": "E:\\...\\CodeX_Workspace",
  "project_name": "CodeX_Workspace",
  "last_ts": "2026-06-22T03:53:59Z",
  "thread_name": "...",      // may be null
  "originator": "Codex Desktop"
}
```

`project_name` reuses the existing `_project_name(cwd)` helper. If
`~/.codex/` is absent, return `[]`.

### `GET /api/codex/sessions/<id>`

1. Validate `<id>`: reject if it contains `/`, `\\`, or starts with `.` (path
   traversal guard, same as Claude's `_find_transcript_path`).
2. Locate the file: `glob(CODEX_SESSIONS_DIR / "**" / f"*{id}*.jsonl")`. The id
   is a UUID; matching on filename substring is safe and avoids walking every
   line of every file.
3. Parse into the Claude-compatible message schema:

| Codex record (`response_item.payload`) | Output message |
|---|---|
| `message` role=`user` | `{role:"user", ts, text}` |
| `message` role=`assistant` | `{role:"assistant", ts, text}` |
| `message` role=`developer` | skip |
| `reasoning` | skip (encrypted_content is opaque) |
| `function_call` / `custom_tool_call` | `{role:"tool", ts, tool, input}` — `tool`=name, `input`=arguments/input string |
| `function_call_output` / `custom_tool_call_output` | backfill `output`+`is_error` onto the tool msg with matching `call_id` (or append standalone if no match) |

This mirrors `parse_conversation()`'s `tool_idx_by_id` linking logic, keyed on
`call_id` instead of `tool_use_id`. `ts` = top-level record `timestamp`.

If the file/id isn't found → `{"error":"not found"}, 404`.

### Routing

Add to `Handler.do_GET` (before the generic 404), mirroring existing order:
- `path == "/api/codex/sessions"` → list
- `path.startswith("/api/codex/sessions/")` → single (after the `/api/sessions2/`
  family so there's no prefix collision — `/api/codex/...` is distinct anyway)

No new POST/DELETE routes.

---

## Frontend design (`dashboard.html`)

### Tab toggle UI

Add a segmented control at the top of `#session-pane` (before
`#heatmap-section`):
```html
<div class="tab-bar">
  <button class="tab active" data-tab="claude">Claude</button>
  <button class="tab" data-tab="codex">Codex</button>
</div>
```
State: `let currentTab = "claude";`

### `switchTab(tab)`

- Toggle `.active` class on the pills.
- `currentTab = tab`.
- Hide `#heatmap-section` and `#search-box` when `tab === "codex"`; show on claude.
- Clear `#search-results` / search input when leaving claude.
- Clear `#detail-pane` to its empty state.
- Call `renderSessions()` to reload the list from the right source.

### Tab-aware functions

- `renderSessions()`: fetch `currentTab === "codex" ? "/api/codex/sessions" : "/api/sessions2"`.
  - Codex row HTML: replace the status dot with a small static "Codex" badge
    (no green/yellow/grey). Title = `thread_name || project_name`; meta = `cwd`.
    **No delete / copy action buttons** on Codex rows — only the row click.
- `loadConversation(id)`: fetch `currentTab === "codex" ? "/api/codex/sessions/" + id : "/api/sessions2/" + id`.
- `renderConversation(msgs, meta)`: **unchanged** — both sources produce the
  same `{role, ts, text, [tool, input, output, is_error]}` schema.

Row click delegation already reads `data-id`; switching to Codex just changes
the fetch URL, so the click handler needs only the `currentTab` branch in
`loadConversation`.

### Empty state

If Codex returns `[]` (Codex not installed / no sessions), show
"No Codex sessions found in ~/.codex/sessions/".

---

## Edge cases & safety

- `~/.codex/` missing → `/api/codex/sessions` returns `[]`; dashboard shows empty state.
- Malformed JSONL line → skip (don't crash the parse).
- `session_meta` missing or first-line-not-meta → fall back to deriving
  `id`/`ts` from the filename; skip file if unusable.
- Path traversal: any `/api/codex/sessions/<id>` with `/`, `\\`, or leading `.`
  → 400.
- Duplicate ids across files (shouldn't happen) → glob returns first match.

---

## Files touched

| File | Change |
|---|---|
| `skills_apocalypse/server.py` | +2 endpoints (`/api/codex/sessions`, `/api/codex/sessions/<id>`), +scan/parse helpers, +constants |
| `skills_apocalypse/dashboard.html` | +tab toggle UI + CSS, `currentTab` state, `switchTab()`, tab-aware `renderSessions()`/`loadConversation()`, Codex row template, empty state |

No changes to: hooks, `workspace.html`, `workspace_init.py`, `apocalypse.py`,
`install.sh`, Claude-side endpoints.

---

## Verification

1. `python -m py_compile skills_apocalypse/server.py` — syntax.
2. Restart server, open `http://localhost:7749/`.
3. Default Claude tab unchanged (regression: heatmap, search, session list, status dots all normal).
4. Click **Codex** tab → heatmap + search hidden; list shows ~257 Codex sessions sorted by recency, each with a "Codex" badge and `cwd`.
5. Click a Codex session → right pane shows its full user/assistant/tool transcript, tool calls collapsible with input/output.
6. Switch back to Claude → heatmap/search return, list restores.
7. Edge: temporarily point `CODEX_DIR` at a missing path (or test on a machine without Codex) → Codex tab shows the empty state, no server errors.
