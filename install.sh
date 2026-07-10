#!/usr/bin/env bash
# Apocalypse install script
# Usage: bash install.sh
# Installs the skill to ~/.claude/skills/apocalypse/ and registers hooks.
#
# Cross-platform: detects Windows (Git Bash / MSYS / Cygwin), macOS, Linux.
# Skips Windows-only files on Unix and writes the launcher alias to the
# correct shell rc file (.zshrc / .bashrc / fish config.fish).

set -e

DEST="$HOME/.claude/skills/apocalypse"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Platform detection ───────────────────────────────────────────────────────
case "$OSTYPE" in
    msys*|cygwin*|win32) PLATFORM="windows" ;;
    darwin*)             PLATFORM="macos"   ;;
    linux*)              PLATFORM="linux"   ;;
    *)                   PLATFORM="other"   ;;
esac

# Resolve a working python (Windows has a broken python3 stub in WindowsApps)
if command -v python3 >/dev/null 2>&1 && python3 -c "" >/dev/null 2>&1; then
    PY=python3
else
    PY=python
fi

echo "Installing Apocalypse to $DEST (platform: $PLATFORM, python: $PY) ..."

mkdir -p "$DEST/hooks"

# ── Cross-platform file copies ───────────────────────────────────────────────
cp "$REPO_DIR/SKILL.md"               "$DEST/SKILL.md"
cp "$REPO_DIR/server.py"              "$DEST/server.py"
cp "$REPO_DIR/dashboard.html"         "$DEST/dashboard.html"
cp "$REPO_DIR/start.sh"               "$DEST/start.sh"
cp "$REPO_DIR/hooks/on-tool.sh"       "$DEST/hooks/on-tool.sh"
cp "$REPO_DIR/hooks/on-stop.sh"       "$DEST/hooks/on-stop.sh"
cp "$REPO_DIR/workspace.html"         "$DEST/workspace.html"
cp "$REPO_DIR/workspace_init.py"      "$DEST/workspace_init.py"
cp "$REPO_DIR/apocalypse.py"          "$DEST/apocalypse.py"
cp "$REPO_DIR/platform_utils.py"      "$DEST/platform_utils.py"
cp "$REPO_DIR/apocalypse.sh"          "$DEST/apocalypse.sh"
chmod +x "$DEST/apocalypse.sh"

# Windows-only launcher: skip on macOS / Linux
if [ "$PLATFORM" = "windows" ]; then
    cp "$REPO_DIR/apocalypse.cmd" "$DEST/apocalypse.cmd"
fi

# Vendor JS for the workspace 3D view. workspace.html dynamically imports
# /three.module.min.js; without this file the workspace page fails to load.
for vendor in three.module.min.js OrbitControls.js; do
  if [ -f "$REPO_DIR/$vendor" ]; then
    cp "$REPO_DIR/$vendor" "$DEST/$vendor"
  elif [ ! -f "$DEST/$vendor" ]; then
    echo "WARNING: $vendor not found in $REPO_DIR — workspace.html will not load until you place it in $DEST" >&2
  fi
done

# Texture assets for workspace visual effects.
# workspace.html references mesh1/mesh3 plus several nebula_mesh_nebula*.png
# files; server.py serves any /nebula_*.png from the skill dir. Copy all
# textures present in the repo so the workspace starfield renders fully.
for tex in "$REPO_DIR"/*.png "$REPO_DIR"/*.jpg; do
  [ -f "$tex" ] || continue
  cp "$tex" "$DEST/$(basename "$tex")"
done

chmod +x "$DEST/start.sh" "$DEST/hooks/on-tool.sh" "$DEST/hooks/on-stop.sh"

# ── Launcher alias: pick the right rc file for the user's shell ─────────────
# Detect shell from $SHELL; fall back to platform default.
SHELL_NAME=""
case "$SHELL" in
    */zsh)  SHELL_NAME="zsh"  ;;
    */bash) SHELL_NAME="bash" ;;
    */fish) SHELL_NAME="fish" ;;
    *)
        # No $SHELL or unknown — fall back to platform default
        if [ "$PLATFORM" = "macos" ]; then
            SHELL_NAME="zsh"
        elif [ "$PLATFORM" = "linux" ]; then
            SHELL_NAME="bash"
        fi
        ;;
esac

write_alias() {
    local rc="$1" line="$2" marker="$3"
    if [ -z "$rc" ] || [ -z "$line" ]; then return 0; fi
    if [ -f "$rc" ] && grep -qF "$marker" "$rc" 2>/dev/null; then
        echo "Launcher alias already in $(basename "$rc")"
        return 0
    fi
    mkdir -p "$(dirname "$rc")"
    touch "$rc"
    {
        echo ""
        echo "# Apocalypse launcher"
        echo "$line"
    } >> "$rc"
    echo "Added 'apocalypse' alias to $(basename "$rc")"
}

if [ "$PLATFORM" = "windows" ]; then
    # Windows: copy .cmd to ~/bin (must be on PATH)
    if [ -f "$DEST/apocalypse.cmd" ]; then
        mkdir -p "$HOME/bin"
        cp "$DEST/apocalypse.cmd" "$HOME/bin/apocalypse.cmd"
        echo "Copied apocalypse.cmd to ~/bin (Windows launcher)"
    fi
    # Also keep the .bashrc alias (Git Bash users on Windows use bash).
    ALIAS_LINE="alias apocalypse='PYTHONUTF8=1 $PY \"\$HOME/.claude/skills/apocalypse/apocalypse.py\"'"
    write_alias "$HOME/.bashrc" "$ALIAS_LINE" '.claude/skills/apocalypse/apocalypse.py'
else
    # macOS / Linux: write to the right rc file based on shell
    case "$SHELL_NAME" in
        zsh)
            ALIAS_LINE="alias apocalypse='PYTHONUTF8=1 $PY \"\$HOME/.claude/skills/apocalypse/apocalypse.py\"'"
            write_alias "$HOME/.zshrc" "$ALIAS_LINE" '.claude/skills/apocalypse/apocalypse.py'
            ;;
        bash)
            ALIAS_LINE="alias apocalypse='PYTHONUTF8=1 $PY \"\$HOME/.claude/skills/apocalypse/apocalypse.py\"'"
            write_alias "$HOME/.bashrc" "$ALIAS_LINE" '.claude/skills/apocalypse/apocalypse.py'
            ;;
        fish)
            # fish syntax differs — no `=` form
            FISH_LINE="alias apocalypse 'PYTHONUTF8=1 $PY $HOME/.claude/skills/apocalypse/apocalypse.py'"
            write_alias "$HOME/.config/fish/config.fish" "$FISH_LINE" '.claude/skills/apocalypse/apocalypse.py'
            ;;
        *)
            echo "NOTE: could not detect shell ($SHELL). Add this alias manually:"
            echo "  alias apocalypse='PYTHONUTF8=1 $PY \$HOME/.claude/skills/apocalypse/apocalypse.py'"
            ;;
    esac
fi

echo "Files installed."
echo ""
echo "Starting server and registering hooks ..."
bash "$DEST/start.sh"
echo ""
echo "🌋 Apocalypse → http://localhost:7749"
echo ""
if [ "$PLATFORM" = "windows" ]; then
    echo "Launcher: type 'apocalypse' to browse projects and resume sessions."
    echo "  First time: open a new terminal, then type: apocalypse"
else
    echo "Launcher: type 'apocalypse' to browse projects and resume sessions."
    case "$SHELL_NAME" in
        zsh)  echo "  First time: run 'source ~/.zshrc' (or open a new terminal), then: apocalypse" ;;
        bash) echo "  First time: run 'source ~/.bashrc' (or open a new terminal), then: apocalypse" ;;
        fish) echo "  First time: open a new shell, then: apocalypse" ;;
        *)    echo "  First time: open a new terminal, then: apocalypse" ;;
    esac
fi
