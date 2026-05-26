#!/usr/bin/env bash
# Apocalypse install script
# Usage: bash install.sh
# Installs the skill to ~/.claude/skills/apocalypse/ and registers hooks.

set -e

DEST="$HOME/.claude/skills/apocalypse"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Apocalypse to $DEST ..."

mkdir -p "$DEST/hooks"

cp "$REPO_DIR/SKILL.md"       "$DEST/SKILL.md"
cp "$REPO_DIR/server.py"      "$DEST/server.py"
cp "$REPO_DIR/dashboard.html" "$DEST/dashboard.html"
cp "$REPO_DIR/start.sh"       "$DEST/start.sh"
cp "$REPO_DIR/hooks/on-tool.sh" "$DEST/hooks/on-tool.sh"
cp "$REPO_DIR/hooks/on-stop.sh" "$DEST/hooks/on-stop.sh"

chmod +x "$DEST/start.sh" "$DEST/hooks/on-tool.sh" "$DEST/hooks/on-stop.sh"

echo "Files installed."
echo ""
echo "Starting server and registering hooks ..."
bash "$DEST/start.sh"
echo ""
echo "Done! Open a new Claude Code session and type /apocalypse to open the dashboard."
