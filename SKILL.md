---
name: apocalypse
description: Start the Apocalypse agent monitoring dashboard. Use when the user types /apocalypse or asks to open the agent monitor, view agent status, see what Claude Code sessions are doing, or check running Claude Code agents on this machine.
---

# Apocalypse

When this skill is invoked, run the startup script and report the URL.

## Steps

1. Run the startup script:

   ```bash
   bash ~/.claude/skills/apocalypse/start.sh
   ```

2. Tell the user:
   - The dashboard is at **http://localhost:7749**
   - It shows real-time status for every Claude Code session on this machine
   - Session history persists to `~/.claude/apocalypse/` and survives terminal close
   - To stop the server: `kill $(cat ~/.claude/apocalypse/server.pid)`

Hooks are registered on first run via `~/.claude/settings.local.json`. Running this skill again is safe — it will not duplicate hooks or restart an already-running server.
