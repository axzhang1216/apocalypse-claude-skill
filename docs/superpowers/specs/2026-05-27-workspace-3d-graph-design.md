# Workspace 3D Graph — Design Spec

**Date:** 2026-05-27  
**Project:** Apocalypse Claude Code Agent Monitor  
**Feature:** Workspace tab — 3D universe visualization of all Claude Code session history

---

## Overview

Add a "Workspace" view to Apocalypse that visualizes all historical Claude Code sessions as an interactive 3D universe. Projects appear as nebula spheres in a galaxy; clicking a project reveals its sessions as a solar system of stars and planets.

Initialization is triggered conversationally via the `/apocalypse` skill. Claude analyzes all historical transcripts using the Claude API and narrates findings to the user in real time.

---

## Data Layer

### Persistent Store

`~/.claude/apocalypse/workspace.json`

```json
{
  "version": 1,
  "last_full_init": "2026-05-27T10:00:00Z",
  "projects": {
    "apocalypse": {
      "name": "apocalypse",
      "cwd": "/path/to/apocalypse",
      "sessions": ["uuid1", "uuid2"],
      "total_messages": 342,
      "total_tool_calls": 89,
      "first_seen": "2026-05-20T00:00:00Z",
      "last_active": "2026-05-27T09:00:00Z",
      "analyzed_sessions": {
        "uuid1": {
          "summary": "用户要求新增 SSE 推送功能，Claude 修改了 server.py",
          "user_goal": "Add SSE push to dashboard",
          "outcome": "completed",
          "key_tools": ["Edit", "Write", "Bash"],
          "ts": "2026-05-25T12:00:00Z"
        }
      }
    }
  },
  "analyzed_session_ids": ["uuid1", "uuid2"]
}
```

**Fields:**
- `outcome`: one of `completed` / `partial` / `abandoned`
- `analyzed_session_ids`: flat list used for incremental update diffing
- `total_tool_calls`: sum of all tool_use blocks across all sessions in the project

### New API Endpoints (server.py)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/workspace` | Return full `workspace.json` content |
| `GET` | `/api/workspace/status` | Return `{ initialized: bool, project_count: int, session_count: int }` |

### Incremental Update

On every `/apocalypse` launch, after the server starts, the skill silently calls `/api/workspace/status`. If initialized:
- `workspace_init.py --incremental` runs in background
- Diffs `analyzed_session_ids` against current `~/.claude/projects/`
- Analyzes only new sessions, appends results to `workspace.json`
- No user-facing output unless new sessions were found (then: "已自动分析 N 个新 session")

---

## Initialization Harness

### Trigger Flow (SKILL.md)

```
1. bash start.sh                          # existing logic
2. GET /api/workspace/status
3. if initialized == false:
     Ask user: "发现你还没有初始化 Workspace。
     这会用 Claude API 分析所有历史 session，提取每个对话的目标和结果。
     可能需要几分钟。要现在开始吗？"
4. User yes → run workspace_init.py (full mode), stream output
5. User no  → report dashboard URL, done
```

### workspace_init.py

**Invocation:**
```bash
python workspace_init.py [--incremental]
```

**Algorithm:**
1. Scan all `~/.claude/projects/**/*.jsonl`
2. Group sessions by `cwd` → project
3. For each project, for each unanalyzed session:
   - Call `parse_conversation()` (reuse server.py logic)
   - Build prompt: first user message + last assistant message + tool call summary
   - Call Claude API (`claude-haiku-4-5-20251001`) with summarization prompt
   - Extract: `user_goal`, `summary`, `outcome`, `key_tools`
4. After each project completes, emit one JSON line to stdout:
   ```json
   {"type": "project_done", "project": "apocalypse", "sessions": 15, "top_themes": ["dashboard", "hooks", "SSE"]}
   ```
5. On full completion:
   ```json
   {"type": "done", "total_projects": 12, "total_sessions": 87}
   ```
6. Write/update `workspace.json`

**Summarization prompt template:**
```
You are analyzing a Claude Code session. Extract structured info.

First user message: {first_user_msg}
Last assistant message: {last_assistant_msg}
Tools used: {tool_list}
Total messages: {msg_count}

Reply in JSON only:
{
  "user_goal": "one sentence, what the user wanted",
  "summary": "one sentence, what was accomplished",
  "outcome": "completed|partial|abandoned",
  "key_tools": ["Tool1", "Tool2"]
}
```

**Skill reads stdout line by line and narrates:**
> "apocalypse 分析完了——15个session，主要在做 dashboard、hooks 和 SSE 推送。"
> "全部完成！共12个项目，87个session。打开 http://localhost:7749/workspace.html 查看。"

---

## Frontend: workspace.html

Standalone HTML file. No build step. Three.js and OrbitControls loaded from CDN.

### Two Scenes

**Scene A — Universe View (default)**

| Element | Mapping |
|---------|---------|
| Background | Three.js `Points` star field (decorative) |
| Project sphere radius | `log(total_messages) * k` |
| Project sphere distance from center | Inversely proportional to recency of `last_active`; >30 days → outer ring |
| Sphere color | `last_active` < 3 days → green (`#3fb950`); < 14 days → yellow (`#d29922`); else → grey (`#6e7681`) |
| Sphere glow | `PointLight` attached to each sphere |
| Hover | Glow intensifies + tooltip: project name, session count, last active |
| Click | Transition to Scene B (camera zoom + fade) |

Interactions: drag to rotate (`OrbitControls`), scroll to zoom, click blank space to deselect.

**Scene B — Solar System View (per project)**

| Element | Mapping |
|---------|---------|
| Center label | Project name |
| Star (per session) | Sphere; size ∝ message count; color by `outcome` (green/yellow/grey) |
| Star position | Spiral arrangement by time; newest sessions closest to center |
| Planet (per key tool) | Small sphere orbiting its star; one planet per distinct tool in `key_tools` |
| Star click | Right panel slides in: `user_goal`, `summary`, `outcome`, "Open in Sessions view" button |
| Back button | Top-left "← Universe"; camera animates back to Scene A |

### Data Loading

On page load: `GET /api/workspace` → render Universe View.  
If `workspace.json` is empty or missing: show centered message "Workspace not initialized. Run /apocalypse to get started."

### Navigation Link

`dashboard.html` header gets a "🌌 Workspace" link (`<a href="/workspace.html">`). No other changes to dashboard.html.

---

## File Changes

| File | Change |
|------|--------|
| `SKILL.md` | Add workspace status check + init conversation flow |
| `server.py` | Add `GET /api/workspace`, `GET /api/workspace/status` |
| `dashboard.html` | Add "🌌 Workspace" link in header |
| `workspace.html` | New file — Three.js 3D visualization |
| `workspace_init.py` | New file — initialization + incremental update harness |
| `install.sh` | Copy `workspace.html` and `workspace_init.py` to install target |

`start.sh` and `hooks/` are unchanged.

---

## Out of Scope

- Authentication / multi-user
- Editing or annotating session summaries from the UI
- Real-time updates to the 3D scene while it's open (workspace is historical, not live)
- Mobile layout
