#!/usr/bin/env bash
# Compatibility shim. Apocalypse UI startup is now owned by apocalypse_ui.py
# and does not perform workspace analysis, invoke an LLM, or register hooks.

set -e
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
PY=python
if command -v python3 >/dev/null 2>&1 && python3 -c "" >/dev/null 2>&1; then
    PY=python3
fi

exec "$PY" "$SKILL_DIR/apocalypse_ui.py" start --no-open
