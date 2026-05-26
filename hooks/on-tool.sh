#!/usr/bin/env bash
# Apocalypse on-tool hook: reads JSON from stdin (Claude Code hook format),
# appends one event line to events.jsonl, then re-emits stdin unchanged.

PHASE="${1:-unknown}"   # "pre" or "post"
DATA_DIR="$HOME/.claude/apocalypse"
EVENTS_FILE="$DATA_DIR/events.jsonl"

mkdir -p "$DATA_DIR"

# Resolve a working python (Windows has a broken python3 stub in WindowsApps)
PY=python
command -v python3 >/dev/null 2>&1 && python3 -c "" >/dev/null 2>&1 && PY=python3

# Read stdin once
INPUT=$(cat)

# Pass JSON via env var (stdin is used to deliver the python script via heredoc)
APOCALYPSE_INPUT="$INPUT" \
APOCALYPSE_PHASE="$PHASE" \
APOCALYPSE_ENV_SESSION="${CLAUDE_SESSION_ID:-}" \
APOCALYPSE_ENV_PROJECT="${CLAUDE_PROJECT_DIR:-}" \
APOCALYPSE_EVENTS_FILE="$EVENTS_FILE" \
"$PY" <<'PYEOF'
import json, os, datetime

phase        = os.environ.get("APOCALYPSE_PHASE", "unknown")
env_session  = os.environ.get("APOCALYPSE_ENV_SESSION", "")
env_project  = os.environ.get("APOCALYPSE_ENV_PROJECT", "")
events_file  = os.environ["APOCALYPSE_EVENTS_FILE"]
raw          = os.environ.get("APOCALYPSE_INPUT", "")

try:
    payload = json.loads(raw) if raw.strip() else {}
except Exception:
    payload = {}

session_id   = payload.get("session_id") or env_session or "unknown"
project_dir  = payload.get("cwd") or env_project or "unknown"
project_name = os.path.basename(project_dir.rstrip("/\\")) or "unknown"
tool_name    = payload.get("tool_name", "unknown")
tool_input   = payload.get("tool_input", {})
tool_output  = payload.get("tool_response", payload.get("tool_output", ""))

def preview(v, n=200):
    try:
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    except Exception:
        s = str(v)
    return s[:n]

event = {
    "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "session_id":   session_id,
    "project":      project_dir,
    "project_name": project_name,
    "type":         "tool_start" if phase == "pre" else "tool_end",
    "tool":         tool_name,
}
if phase == "pre":
    event["input_preview"] = preview(tool_input)
else:
    event["output_preview"] = preview(tool_output)

with open(events_file, "a", encoding="utf-8") as f:
    f.write(json.dumps(event, ensure_ascii=False) + "\n")
PYEOF

# Pass stdin through unchanged (Claude Code expects hook to be transparent)
printf '%s' "$INPUT"
