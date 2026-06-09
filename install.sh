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
cp "$REPO_DIR/workspace.html"       "$DEST/workspace.html"
cp "$REPO_DIR/workspace_init.py"    "$DEST/workspace_init.py"
cp "$REPO_DIR/apocalypse.py"        "$DEST/apocalypse.py"
cp "$REPO_DIR/apocalypse.cmd"       "$DEST/apocalypse.cmd"

# Vendor JS for the workspace 3D view. workspace.html dynamically imports
# /three.module.min.js; without this file the workspace page fails to load.
for vendor in three.module.min.js OrbitControls.js; do
  if [ -f "$REPO_DIR/$vendor" ]; then
    cp "$REPO_DIR/$vendor" "$DEST/$vendor"
  elif [ ! -f "$DEST/$vendor" ]; then
    echo "WARNING: $vendor not found in $REPO_DIR — workspace.html will not load until you place it in $DEST" >&2
  fi
done

chmod +x "$DEST/start.sh" "$DEST/hooks/on-tool.sh" "$DEST/hooks/on-stop.sh"

# ── Add launcher alias to .bashrc if not already present ──────────────────────
ALIAS_LINE="alias apocalypse='PYTHONUTF8=1 python \"\$HOME/.claude/skills/apocalypse/apocalypse.py\"'"
BASHRC="$HOME/.bashrc"
if [ -f "$BASHRC" ] && grep -qF '.claude/skills/apocalypse/apocalypse.py' "$BASHRC" 2>/dev/null; then
  echo "Launcher alias already in .bashrc"
elif [ -f "$BASHRC" ]; then
  echo "" >> "$BASHRC"
  echo "# Apocalypse launcher" >> "$BASHRC"
  echo "$ALIAS_LINE" >> "$BASHRC"
  echo "Added 'apocalypse' alias to .bashrc"
fi

# ── Windows: copy .cmd to ~/bin (must be on PATH) ─────────────────────────────
if [ -f "$DEST/apocalypse.cmd" ]; then
  mkdir -p "$HOME/bin"
  cp "$DEST/apocalypse.cmd" "$HOME/bin/apocalypse.cmd"
  echo "Copied apocalypse.cmd to ~/bin (Windows launcher)"
fi

echo "Files installed."
echo ""
echo "Starting server and registering hooks ..."
bash "$DEST/start.sh"
echo ""
echo "Launcher: type 'apocalypse' to browse projects and resume sessions."
echo "  First time: open a new terminal, then type: apocalypse"
