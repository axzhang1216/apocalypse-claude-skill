#!/usr/bin/env bash
# Apocalypse Stop hook: copies the session transcript to apocalypse/sessions/
# as an offline cache, and appends a stop event to events.jsonl.

DATA_DIR="$HOME/.claude/apocalypse"
SESSIONS_DIR="$DATA_DIR/sessions"
EVENTS_FILE="$DATA_DIR/events.jsonl"

mkdir -p "$SESSIONS_DIR"

PY=python
command -v python3 >/dev/null 2>&1 && python3 -c "" >/dev/null 2>&1 && PY=python3

INPUT=$(cat)

APOCALYPSE_INPUT="$INPUT" \
APOCALYPSE_ENV_SESSION="${CLAUDE_SESSION_ID:-}" \
APOCALYPSE_ENV_PROJECT="${CLAUDE_PROJECT_DIR:-}" \
APOCALYPSE_EVENTS_FILE="$EVENTS_FILE" \
APOCALYPSE_SESSIONS_DIR="$SESSIONS_DIR" \
"$PY" <<'PYEOF'
import json, os, shutil, datetime, glob
from pathlib import Path

env_session    = os.environ.get("APOCALYPSE_ENV_SESSION", "")
env_project    = os.environ.get("APOCALYPSE_ENV_PROJECT", "")
events_file    = os.environ["APOCALYPSE_EVENTS_FILE"]
sessions_dir   = Path(os.environ["APOCALYPSE_SESSIONS_DIR"])
raw            = os.environ.get("APOCALYPSE_INPUT", "")

try:
    payload = json.loads(raw) if raw.strip() else {}
except Exception:
    payload = {}

session_id      = payload.get("session_id") or env_session or "unknown"
project_dir     = payload.get("cwd") or env_project or "unknown"
project_name    = os.path.basename(project_dir.rstrip("/\\")) or "unknown"
transcript_path = payload.get("transcript_path", "")
stop_reason     = payload.get("stop_hook_active", payload.get("reason", ""))

# Resolve transcript: prefer the path the hook gave us, else search by session id
src = None
if transcript_path and Path(transcript_path).exists():
    src = Path(transcript_path)
else:
    projects_root = Path.home() / ".claude" / "projects"
    if projects_root.exists() and session_id != "unknown":
        for cand in projects_root.glob(f"**/{session_id}.jsonl"):
            src = cand
            break

snapshot_path = ""
if src and src.exists():
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    safe_session = session_id.replace("/", "_").replace("\\", "_")
    snapshot_path = sessions_dir / f"{date}-{project_name}-{safe_session}{src.suffix or '.jsonl'}"
    try:
        shutil.copyfile(src, snapshot_path)
        snapshot_path = str(snapshot_path)
    except Exception:
        snapshot_path = ""

event = {
    "ts":           datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "session_id":   session_id,
    "project":      project_dir,
    "project_name": project_name,
    "type":         "stop",
    "snapshot":     snapshot_path,
    "reason":       str(stop_reason)[:120],
}
with open(events_file, "a", encoding="utf-8") as f:
    f.write(json.dumps(event, ensure_ascii=False) + "\n")
PYEOF

# Pass stdin through (Claude Code expects hook to be transparent)
printf '%s' "$INPUT"
