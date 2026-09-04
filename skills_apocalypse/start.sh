#!/usr/bin/env bash
# Apocalypse startup: starts the dashboard server if not running and registers
# Claude Code hooks (idempotent — running this twice has no extra effect).

set -e

SKILL_DIR="$HOME/.claude/skills/apocalypse"
DATA_DIR="$HOME/.claude/apocalypse"
PID_FILE="$DATA_DIR/server.pid"
LOG_FILE="$DATA_DIR/server.log"
PORT=7749

mkdir -p "$DATA_DIR"

# ── 0. Resolve a working python ─────────────────────────────────────────────
PY=python
if command -v python3 >/dev/null 2>&1 && python3 -c "" >/dev/null 2>&1; then
    PY=python3
fi

# ── 1. Start server if not running ──────────────────────────────────────────
server_alive() {
    [ -f "$PID_FILE" ] || return 1
    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null) || return 1
    [ -n "$pid" ] || return 1
    # kill -0 is the standard PID-liveness check on macOS/Linux. Under
    # Git Bash on Windows it may not see Windows PIDs; the port probe
    # below catches that case either way.
    if kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    return 1
}

spatial_alive() {
    curl -sf -m 1 "http://localhost:$PORT/api/world" >/dev/null 2>&1
}

start_server() {
    local entry="$SKILL_DIR/spatial_server.py"
    [ -f "$entry" ] || entry="$SKILL_DIR/server.py"
    nohup "$PY" "$entry" >"$LOG_FILE" 2>&1 &
    disown 2>/dev/null || true
    # Wait up to 3s for the server to bind. Spatial builds expose /api/world;
    # the legacy fallback continues to use /api/events.
    for _ in 1 2 3 4 5 6; do
        sleep 0.5
        if [ -f "$SKILL_DIR/spatial_server.py" ]; then
            spatial_alive && return 0
        elif curl -sf -m 1 "http://localhost:$PORT/api/events" >/dev/null 2>&1; then
            return 0
        fi
    done
    return 1
}

if server_alive; then
    if [ -f "$SKILL_DIR/spatial_server.py" ] && ! spatial_alive; then
        # Upgrade an Apocalypse-owned legacy process in place. We only kill the
        # PID from Apocalypse's own pid file; an unrelated process on 7749 is
        # never touched here.
        old_pid=$(cat "$PID_FILE" 2>/dev/null || true)
        echo "Upgrading Apocalypse server to Spatial OS (pid $old_pid)"
        kill "$old_pid" 2>/dev/null || true
        for _ in 1 2 3 4 5 6; do
            sleep 0.25
            kill -0 "$old_pid" 2>/dev/null || break
        done
        rm -f "$PID_FILE"
        start_server || echo "WARNING: server may have failed to start; check $LOG_FILE" >&2
    else
        echo "Apocalypse server already running (pid $(cat "$PID_FILE"))"
    fi
elif curl -sf -m 1 "http://localhost:$PORT/api/events" >/dev/null 2>&1; then
    echo "Apocalypse server already running on port $PORT"
else
    rm -f "$PID_FILE"
    if start_server; then
        echo "Apocalypse server started (pid $(cat "$PID_FILE" 2>/dev/null))"
    else
        echo "WARNING: server may have failed to start; check $LOG_FILE" >&2
    fi
fi

# ── 2. Register hooks in settings.local.json if not present (idempotent) ────
APOCALYPSE_SKILL_DIR="$SKILL_DIR" "$PY" <<'PYEOF'
import json, os
from pathlib import Path

settings_path = Path.home() / ".claude" / "settings.local.json"
skill_dir     = os.environ["APOCALYPSE_SKILL_DIR"].replace("\\", "/")

if settings_path.exists():
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
else:
    settings = {}

hooks = settings.setdefault("hooks", {})

on_tool = f'bash "{skill_dir}/hooks/on-tool.sh"'
on_stop = f'bash "{skill_dir}/hooks/on-stop.sh"'

def already_registered(hook_list, marker):
    for entry in hook_list:
        if not isinstance(entry, dict):
            continue
        if marker in str(entry.get("command", "")):
            return True
        for h in entry.get("hooks", []):
            if isinstance(h, dict) and marker in str(h.get("command", "")):
                return True
    return False

changed = False
for event, cmd in [("PreToolUse", on_tool + " pre"),
                   ("PostToolUse", on_tool + " post")]:
    lst = hooks.setdefault(event, [])
    if not already_registered(lst, "on-tool.sh"):
        lst.append({"matcher": ".*", "hooks": [{"type": "command", "command": cmd}]})
        changed = True
        print(f"Registered {event} hook")

stop_list = hooks.setdefault("Stop", [])
if not already_registered(stop_list, "on-stop.sh"):
    stop_list.append({"matcher": "", "hooks": [{"type": "command", "command": on_stop}]})
    changed = True
    print("Registered Stop hook")

if changed:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print("Hooks saved to ~/.claude/settings.local.json")
else:
    print("Hooks already registered")
PYEOF

echo ""
echo "🌋 Apocalypse → http://localhost:$PORT"
echo "   Legacy dashboard → http://localhost:$PORT/legacy/dashboard"
