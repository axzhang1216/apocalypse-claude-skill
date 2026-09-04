#!/usr/bin/env bash
# Apocalypse install script
# Usage: bash install.sh
# Installs the skill to ~/.claude/skills/apocalypse/ and registers hooks.
# Cross-platform: Windows (Git Bash/MSYS/Cygwin), macOS, Linux.

set -e
DEST="$HOME/.claude/skills/apocalypse"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
case "$OSTYPE" in
    msys*|cygwin*|win32) PLATFORM="windows" ;;
    darwin*) PLATFORM="macos" ;;
    linux*) PLATFORM="linux" ;;
    *) PLATFORM="other" ;;
esac
if command -v python3 >/dev/null 2>&1 && python3 -c "" >/dev/null 2>&1; then PY=python3; else PY=python; fi
echo "Installing Apocalypse to $DEST (platform: $PLATFORM, python: $PY) ..."
mkdir -p "$DEST/hooks"
cp "$REPO_DIR/SKILL.md" "$DEST/SKILL.md"
cp "$REPO_DIR/server.py" "$DEST/server.py"
cp "$REPO_DIR/spatial_server.py" "$DEST/spatial_server.py"
cp "$REPO_DIR/spatial_os.html" "$DEST/spatial_os.html"
cp "$REPO_DIR/spatial_os.css" "$DEST/spatial_os.css"
cp "$REPO_DIR/spatial_os.js" "$DEST/spatial_os.js"
cp "$REPO_DIR/dashboard.html" "$DEST/dashboard.html"
cp "$REPO_DIR/start.sh" "$DEST/start.sh"
cp "$REPO_DIR/hooks/on-tool.sh" "$DEST/hooks/on-tool.sh"
cp "$REPO_DIR/hooks/on-stop.sh" "$DEST/hooks/on-stop.sh"
cp "$REPO_DIR/workspace.html" "$DEST/workspace.html"
cp "$REPO_DIR/workspace_init.py" "$DEST/workspace_init.py"
cp "$REPO_DIR/apocalypse.py" "$DEST/apocalypse.py"
cp "$REPO_DIR/codex_workspace.py" "$DEST/codex_workspace.py"
cp "$REPO_DIR/platform_utils.py" "$DEST/platform_utils.py"
if [ -d "$REPO_DIR/apocalypse" ]; then
    rm -rf "$DEST/apocalypse/__pycache__"
    mkdir -p "$DEST/apocalypse"
    cp "$REPO_DIR"/apocalypse/*.py "$DEST/apocalypse/"
fi
cp "$REPO_DIR/apocalypse.sh" "$DEST/apocalypse.sh"
chmod +x "$DEST/apocalypse.sh"
if [ "$PLATFORM" = "windows" ]; then cp "$REPO_DIR/apocalypse.cmd" "$DEST/apocalypse.cmd"; fi
for vendor in three.module.min.js OrbitControls.js; do
  if [ -f "$REPO_DIR/$vendor" ]; then cp "$REPO_DIR/$vendor" "$DEST/$vendor"; elif [ ! -f "$DEST/$vendor" ]; then echo "WARNING: $vendor not found" >&2; fi
done
for tex in mesh1.png mesh2.png mesh3.png; do [ -f "$REPO_DIR/$tex" ] && cp "$REPO_DIR/$tex" "$DEST/$tex"; done
chmod +x "$DEST/start.sh" "$DEST/hooks/on-tool.sh" "$DEST/hooks/on-stop.sh"
SHELL_NAME=""
case "$SHELL" in */zsh) SHELL_NAME="zsh";; */bash) SHELL_NAME="bash";; */fish) SHELL_NAME="fish";; *) [ "$PLATFORM" = "macos" ] && SHELL_NAME="zsh"; [ "$PLATFORM" = "linux" ] && SHELL_NAME="bash";; esac
write_alias(){ local rc="$1" line="$2" marker="$3"; [ -z "$rc" ] && return 0; if [ -f "$rc" ] && grep -qF "$marker" "$rc" 2>/dev/null; then echo "Launcher alias already in $(basename "$rc")"; return 0; fi; mkdir -p "$(dirname "$rc")"; touch "$rc"; { echo ""; echo "# Apocalypse launcher"; echo "$line"; } >> "$rc"; echo "Added 'apocalypse' alias to $(basename "$rc")"; }
if [ "$PLATFORM" = "windows" ]; then
    if [ -f "$DEST/apocalypse.cmd" ]; then mkdir -p "$HOME/bin"; cp "$DEST/apocalypse.cmd" "$HOME/bin/apocalypse.cmd"; fi
    ALIAS_LINE="alias apocalypse='PYTHONUTF8=1 $PY \"\$HOME/.claude/skills/apocalypse/apocalypse.py\"'"
    write_alias "$HOME/.bashrc" "$ALIAS_LINE" '.claude/skills/apocalypse/apocalypse.py'
else
    case "$SHELL_NAME" in
        zsh) ALIAS_LINE="alias apocalypse='PYTHONUTF8=1 $PY \"\$HOME/.claude/skills/apocalypse/apocalypse.py\"'"; write_alias "$HOME/.zshrc" "$ALIAS_LINE" '.claude/skills/apocalypse/apocalypse.py' ;;
        bash) ALIAS_LINE="alias apocalypse='PYTHONUTF8=1 $PY \"\$HOME/.claude/skills/apocalypse/apocalypse.py\"'"; write_alias "$HOME/.bashrc" "$ALIAS_LINE" '.claude/skills/apocalypse/apocalypse.py' ;;
        fish) FISH_LINE="alias apocalypse 'PYTHONUTF8=1 $PY $HOME/.claude/skills/apocalypse/apocalypse.py'"; write_alias "$HOME/.config/fish/config.fish" "$FISH_LINE" '.claude/skills/apocalypse/apocalypse.py' ;;
        *) echo "NOTE: could not detect shell ($SHELL). Add the apocalypse alias manually." ;;
    esac
fi
echo "Files installed."
echo ""
echo "Starting server and registering hooks ..."
bash "$DEST/start.sh"
echo ""
echo "🌋 Apocalypse Spatial OS → http://localhost:7749"
echo "Legacy dashboard → http://localhost:7749/legacy/dashboard"
echo ""
echo "Launcher: type 'apocalypse' to browse projects and resume sessions."
echo ""
echo "────────────────────────────────────────────────────────────"
echo "  Apocalypse 历史归档已默认开启"
echo "  每次 update workspace 会把聊天按讨论/决策切块，导出到"
echo "  各项目下的 .apocalypse/，并在 CLAUDE.md 插入说明段落。"
echo "  关闭方法：编辑 ~/.claude/apocalypse/config.json，"
echo "  设 \"export_history\": false"
echo "────────────────────────────────────────────────────────────"
