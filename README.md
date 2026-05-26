# Apocalypse — Claude Code Agent Monitor

Real-time dashboard for all Claude Code sessions on your machine.

![dashboard](https://github.com/axzhang1216/apocalypse-claude-skill/raw/main/screenshot.png)

## What it does

- **Left panel**: lists every Claude Code session, with tri-state status:
  - 🟢 Green — Claude is actively running a tool
  - 🟡 Yellow — Claude finished replying, waiting for your next message
  - ⚫ Grey — inactive for more than 24 hours
- **Right panel**: full conversation transcript (user messages, Claude replies, tool calls collapsed/expandable)
- **Resume ID**: one-click copy of the full session UUID for `claude --resume <uuid>`
- **Export**: download the conversation as a `.txt` file
- **Delete**: remove a session from the dashboard (original transcript is never touched)
- **Live updates**: SSE push — no manual refresh needed

## Requirements

- Python 3 (stdlib only, no pip installs)
- Claude Code with hooks support
- Git Bash or any bash shell on Windows; bash on macOS/Linux

## Install

### Option A — from source

```bash
git clone https://github.com/axzhang1216/apocalypse-claude-skill.git
cd apocalypse-claude-skill
bash install.sh
```

### Option B — from zip

Download `apocalypse.zip`, unzip, then:

```bash
bash install.sh
```

## Usage

Open any Claude Code session and type:

```
/apocalypse
```

Dashboard opens at **http://localhost:7749**.

To stop the server:

```bash
kill $(cat ~/.claude/apocalypse/server.pid)
```

## How it works

- `start.sh` starts a Python HTTP server on port 7749 and registers three Claude Code hooks (`PreToolUse`, `PostToolUse`, `Stop`) in `~/.claude/settings.local.json`
- The hooks write events to `~/.claude/apocalypse/events.jsonl` and trigger SSE pushes to connected browsers
- The server reads session data directly from `~/.claude/projects/` (Claude Code's native transcript store) — no token usage, pure file I/O
- All hooks are idempotent; running `start.sh` twice is safe

## Files

```
apocalypse/
├── SKILL.md          # Claude Code skill definition (trigger: /apocalypse)
├── start.sh          # Startup script (server + hook registration)
├── server.py         # Python stdlib HTTP + SSE server (port 7749)
├── dashboard.html    # Single-file frontend (vanilla JS, no CDN)
├── install.sh        # One-step installer
└── hooks/
    ├── on-tool.sh    # PreToolUse + PostToolUse hook
    └── on-stop.sh    # Stop hook
```

## Data

- Runtime data: `~/.claude/apocalypse/` (events, snapshots, server PID)
- Session transcripts: read-only from `~/.claude/projects/` (never modified)
