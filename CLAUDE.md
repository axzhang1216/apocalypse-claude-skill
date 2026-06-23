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

The project has two directories:

- **`skills_apocalypse/`** — source files, committed to git
- **`runtime_apocalypse/`** — runtime data (events, session snapshots, PID file); not committed

### Data flow

1. **Hooks** (`hooks/on-tool.sh`, `hooks/on-stop.sh`) fire on every Claude Code tool call and session stop. They append JSON events to `~/.claude/apocalypse/events.jsonl` and copy transcripts to `~/.claude/apocalypse/sessions/`.

2. **`server.py`** serves the dashboard on port 7749. Key responsibilities:
   - `GET /api/sessions2` — scans `~/.claude/projects/` (Claude Code's native transcript store) and returns session metadata with tri-state status (green/yellow/grey)
   - `GET /api/sessions2/<id>` — parses a full transcript into user/assistant/tool messages
   - `GET /events/stream` — SSE endpoint; a background thread tails `events.jsonl` and pushes new lines to all connected clients
   - `DELETE /api/sessions2/<id>` — removes Apocalypse-managed artifacts (events + snapshots) without touching the original `~/.claude/projects/` transcripts

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
- **Auto-scaling**: Spacing adjusts based on project count
- **Collision Avoidance**: No overlap between projects
- **Camera Adaptation**: Auto-adjusts distance based on layout bounds
