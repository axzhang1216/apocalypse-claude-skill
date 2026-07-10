#!/usr/bin/env bash
# Apocalypse Unix launcher (macOS / Linux).
# Mirror of apocalypse.cmd for non-Windows platforms.
#
# install.sh usually adds a shell alias instead, so users will rarely
# invoke this file directly. It exists for symmetry and for users who
# want a plain binary to call from scripts.

PYTHONUTF8=1 exec python "$HOME/.claude/skills/apocalypse/apocalypse.py" "$@"
