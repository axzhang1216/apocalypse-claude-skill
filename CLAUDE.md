# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Apocalypse** is a real-time monitoring dashboard for Claude Code sessions. It shows all active/recent sessions on the machine with live status and full conversation transcripts.

Stack: Python 3 (stdlib only, no dependencies), vanilla JS + HTML, bash hooks.

## Running the Server

```bash
# Start (idempotent — safe to run multiple times)
bash skills_apocalypse/start.sh

# Dashboard at http://localhost:7749

# Stop
kill $(cat ~/.claude/apocalypse/server.pid)
```

Server logs: `~/.claude/apocalypse/server.log`

## Installing

```bash
bash skills_apocalypse/install.sh
```

This copies files to `~/.claude/skills/apocalypse/` and registers hooks in `~/.claude/settings.local.json`.

## Architecture

The project has two directories plus a CLI package:

- **`skills_apocalypse/`** — source files, committed to git
- **`runtime_apocalypse/`** — runtime data (events, session snapshots, PID file); not committed
- **`skills_apocalypse/apocalypse/`** — Python package with the new CLI subcommands
  - `__main__.py` — argparse dispatch and headless detection
  - `launcher.py` — existing menu code (moved from the top-level `apocalypse.py`)
  - `log_view.py` — `apocalypse log` subcommand (transcript pager)
  - `workspace_view.py` — `apocalypse workspace` subcommand (3-level project tree)
  - `tui.py` — shared TUI primitives (Style colour/glyph wrapper, Pager, RawInput)

The top-level `skills_apocalypse/apocalypse.py` is a 5-line wrapper
that calls into the package. Backward compatibility is preserved: all
existing flags (`--refresh`, `--update`, `--list`, `--codex`) and the
menu behaviour are unchanged.

### Data flow

1. **Hooks** (`hooks/on-tool.sh`, `hooks/on-stop.sh`) fire on every Claude Code tool call and session stop. They append JSON events to `~/.claude/apocalypse/events.jsonl` and copy transcripts to `~/.claude/apocalypse/sessions/`.

2. **`server.py`** serves the dashboard on port 7749. Key responsibilities:
   - `GET /api/sessions2` — scans `~/.claude/projects/` (Claude Code's native transcript store) and returns session metadata with tri-state status (green/yellow/grey)
   - `GET /api/sessions2/<id>` — parses a full transcript into user/assistant/tool messages
   - `GET /events/stream` — SSE endpoint; a background thread tails `events.jsonl` and pushes new lines to all connected clients
   - `DELETE /api/sessions2/<id>` — removes Apocalypse-managed artifacts (events + snapshots) without touching the original `~/.claude/projects/` transcripts
   - `GET /api/codex/sessions` — scans `~/.codex/sessions/**/*.jsonl` (OpenAI Codex CLI rollouts), reads each file's `session_meta` for id/cwd/timestamp, enriches with `thread_name` from `~/.codex/session_index.jsonl`. Read-only, no hooks.
   - `GET /api/codex/sessions/<id>` — parses a Codex rollout's `response_item` records into the same message schema as Claude (user/assistant/tool+output; developer/reasoning skipped; tool outputs linked by `call_id`)

3. **`dashboard.html`** — single-file frontend with no CDN dependencies. Connects to the SSE stream for live updates.

### Status determination (`_determine_status`)

Session status is inferred from the tail of the transcript JSONL:
- **Green** — last assistant record contains `tool_use` blocks, or last user record contains `tool_result` blocks (Claude is actively working)
- **Yellow** — last substantive record is an assistant text reply (waiting for user)
- **Grey** — stale (last activity >24 h ago) or nothing substantive found

### Hook mechanics

Hooks pass the Claude Code JSON payload via the `APOCALYPSE_INPUT` env var (not stdin) because the inline Python heredoc consumes stdin. Each hook writes one JSON line to `events.jsonl` and then re-emits the original stdin unchanged so Claude Code's hook pipeline is transparent.

### Windows / Git Bash notes

`start.sh` probes for `python3` vs `python` because Windows has a broken `python3` stub in the WindowsApps PATH. The same probe pattern is in both hook scripts.

## CLI Subcommands

`apocalypse` accepts a subcommand:

| Subcommand | What it does |
|---|---|
| `apocalypse` (no args) | Original menu (unchanged) |
| `apocalypse log <sid>` | Interactive pager for a full session transcript |
| `apocalypse log <sid> --raw` | ANSI text, no pager (pipe to `less -R`) |
| `apocalypse log <sid> --tail` | Watch the session live |
| `apocalypse workspace` | Multi-level project tree (top → project → points) |

See `SKILL.md` → "CLI Subcommands" for full keymaps and headless mode notes.

## Headless mode

SSH / no-GUI environments are detected via `SSH_CONNECTION` / `SSH_TTY` / `DISPLAY` / `WAYLAND_DISPLAY` (see `apocalypse/launcher.is_headless`). In headless mode:

- `apocalypse` (menu) shows a `[headless]` hint in the footer.
- The "resume" action prints the `cd <cwd> && claude --resume <sid>` line for the user to paste in another shell, instead of trying to launch a GUI terminal.
- `apocalypse log` and `apocalypse workspace` work unchanged (they are pure TUI / stdout output).

## Cross-platform support

Apocalypse runs on **Windows, macOS, and Linux**. All platform-specific behaviour is centralised in `skills_apocalypse/platform_utils.py` (`get_platform`, `get_python`, `launch_in_terminal`, `get_shell_rc_path`).

| OS | Terminal launch | Launcher alias destination |
|---|---|---|
| **Windows** (Git Bash / MSYS) | `wt.exe` (Windows Terminal) or `cmd /k` via `start` | `.bashrc` (Git Bash) + `~/bin/apocalypse.cmd` |
| **macOS** | Writes a `.command` script and `open`s it → Terminal.app | `.zshrc` (default) / `.bashrc` / `~/.config/fish/config.fish` |
| **Linux** | Probes `x-terminal-emulator` → `gnome-terminal` → `konsole` → `xfce4-terminal` → `alacritty` → `kitty` → `xterm` | Detected from `$SHELL` |

`install.sh` detects the platform via `$OSTYPE` and the user's shell via `$SHELL`, then writes the launcher alias to the right rc file. Windows-only artefacts (`apocalypse.cmd`) are skipped on Unix.

## Key Constants

| Constant | Location | Value |
|---|---|---|
| `PORT` | `server.py:7` | `7749` |
| `STALE_SECONDS` | `server.py:21` | `86400` (1 day) |
| `TRANSCRIPT_LIMIT` | `server.py:22` | 50 most recent sessions |
| `SKIP_TYPES` | `server.py:24` | Record types filtered out during transcript parsing |
| `CODEX_TRANSCRIPT_LIMIT` | `server.py` | 200 most recent Codex sessions |

## Workspace Visualization

The workspace visualization (`workspace.html`) features real astronomical nebula textures with shader-based atmospheric animation.

### Nebula Textures
- **Source images**: 10 PNG textures in `mesh/nebula/` (mesh_nebula0–9.png), processed to RGBA via `rembg` (for RGB originals) or used directly (for RGBA originals)
- **Processed files**: `skills_apocalypse/nebula_*.png` (512×512, RGBA, black fill in transparent areas)
- **Processing script**: Python with `rembg[cpu]` + Pillow. See `mesh/nebula/` README for details
- **Per-project assignment**: `hash(projectName) % nebulaCount` selects texture; random size (0.7–1.4×) and rotation per project
- **Server route**: `GET /nebula_*.png` in `server.py`

### Shader Animation (NEBULA_FS in workspace.html)
- **Curl noise**: Internal swirling gas currents (multi-octave FBM + curl operator)
- **Particle diffusion**: Edge particles blown outward by radial velocity field + tangential crosswind
- **FBM erosion**: Multi-scale noise erodes edges, creating wispy filamentary dissipation
- **Radial density**: Center opaque, edges transparent (atmospheric falloff)
- **Per-mesh phase**: Each nebula animates at its own time offset

### Liveness System
- `projectLiveness(lastActive)` returns 0–1 (dead→alive) based on days since last activity
- Alive projects: full brightness, breathing animation
- Dead projects: dim, static, noise overlay via mesh1.png

### Other Features
- **Entry animation**: Nebulae scale up from center outward on first load (0.8s)
- **Idle camera drift**: Subtle spherical-coordinate drift when not interacting
- **Left sidebar**: Project list with liveness dots, session counts, last active dates
- **Reset view button**: Returns camera to default position (bottom-right, fixed)
- **Scroll zoom**: Wheel controls camera radius (clamped 30–300)
- **Reduced motion**: `prefers-reduced-motion` disables all JS animation

### Layout Algorithm
- **Golden Angle Spiral**: Even distribution using golden angle (~137.5°)
- **Recency-ordered**: Sorted by `last_active` DESC; the most recent project sits
  closest to origin. Distance formula adds a `0.06` floor so no nebula is pinned
  at the rotation pivot (otherwise dragging the camera would spin an invisible point).
- **Auto-scaling**: Spacing adjusts based on project count
- **Collision Avoidance**: No overlap between projects
- **Camera Adaptation**: Auto-adjusts distance based on layout bounds

### Workspace gotchas (don't reintroduce these bugs)
- **Hover-grow must skip hovered mesh in `animate()`**: Breathing/per-frame
  scale writes overwrite `mesh.scale`, killing the `boostGlow` 1.4× hover
  effect. Both the breathing loop and entry animation must check
  `if (mesh === hoveredMesh) return;` before writing scale.
- **Nebula size = session count, log2-scaled**: `0.33 + log2(1 + n) * 0.22`.
  Don't reintroduce pure random sizing — it makes project importance invisible.
- **Click vs drag**: `OrbitControls` must track `mousedown` start position and
  set `_wasDrag` once cumulative movement > 5 px; `onClick` checks this flag
  and bails. Without this, releasing the mouse after a rotation accidentally
  enters a project.

### History-export gotchas (don't reintroduce these bugs)
- **`_roll_session_md` must hash-check before rolling**: Re-running `export`
  with unchanged points must not churn `.old.N.md`. Hash the new content
  and the existing main; if equal, return early. Without this, every export
  with an oversized session md produces a duplicate-content `.old.1.md`.
- **Never include `Exported: ...` timestamps in the rendered md**: They make
  every render produce different bytes, defeating the hash dedup above. File
  mtime is the export timestamp; no need to bake it into the body.
- **Use `iterdir()` for file existence, not `Path.exists()`**: On Windows,
  `Path.exists()` returns stale True for files that have just been renamed
  (open-file handle caching). Use `parent.iterdir()` snapshots to detect
  the true on-disk state before each rename.
- **Write tmp files in binary mode**: `tmp.write_text(content)` triggers
  CRLF normalization on Windows, adding `\r` to every newline and breaking
  the hash check. Use `tmp.write_bytes(content.encode("utf-8"))`.
- **Rolling filename pattern**: `base = main_path.stem`, sibling is
  `f"{base}.old.{N}.md"` — so `foo.md` rolls into `foo.old.1.md`, NOT
  `foo.md.old.1.md`. The export system uses the former.

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
