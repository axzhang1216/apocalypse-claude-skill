# Apocalypse — Claude Code Agent Monitor

> 监控所有 Claude Code 会话 · 3D 星图回顾你的项目历史 · 命令行快速恢复

> Real-time monitor for every Claude Code session · 3D workspace of your project history · CLI for quick session resume.

![workspace](https://github.com/axzhang1216/apocalypse-claude-skill/raw/main/demo_workspace.gif)

---

## 1 个初始化 · 1 Initialization: Building the Workspace

**构建 Workspace 是所有功能的数据底座。安装后只需运行一次，之后自动增量更新。**

The Workspace is the data backbone that powers all three features below. Build it once after install, and Apocalypse will keep it fresh automatically.

```bash
apocalypse --update       # 扫描新 session + 自动归类主题  /  Scan new sessions + auto-classify
apocalypse --refresh      # 静默重新扫描，无 UI  /  Silent re-scan, no UI
```

**`--update` 做了什么 / What `--update` does:**

- 📊 **Session classification** — Haiku analyzes every transcript → `user_goal`, `summary`, `outcome`, `category`
- 🏷️ **Thematic tags** — Per-project themes (e.g. `前端开发`, `AI工具开发`, `3D可视化`, `调试修复`)
- 💬 **Discussion-decision extraction** — User-topic-shift based cuts; long assistant replies pre-summarized
- 🌌 **Project → Galaxy mapping** — Each project becomes a nebula in the 3D workspace

The result is `~/.claude/apocalypse/workspace.json` — a single file that powers all three features below.

> Tip: First-time initialization may take a few minutes (Haiku calls scale with session count). Subsequent updates are incremental and fast.

---

## 3 个功能 · 3 Features

### 功能 1 · Dashboard 网页 — Real-time Session Monitor

**URL: `http://localhost:7749/`**

实时的 session 监控面板，左侧列表 + 右侧对话详情，SSE 推送，零刷新。

A live dashboard showing every Claude Code session running on this machine. No polling — events stream in via SSE.

**Left panel — Session list with tri-state status:**

| Icon | Status | Meaning |
|------|--------|---------|
| 🟢 | Green | Claude is actively running a tool |
| 🟡 | Yellow | Claude finished replying, waiting for your next message |
| ⚫ | Grey | Inactive for more than 24 hours |

**Right panel — Full conversation:**

- Full transcript with collapsible tool calls
- One-click **Resume ID** copy → `claude --resume <uuid>`
- **Export** as `.txt` for archival
- **Delete** from the dashboard (original transcript is never touched)
- Live updates via SSE — no manual refresh

---

### 功能 2 · Workspace 3D 星图 — Project Galaxy

**URL: `http://localhost:7749/workspace.html`**

3D 星图回顾所有项目，每个项目是一团星云，每个 session 是一颗星。点击进入项目 → 太阳系视图 → Discussion-Decision 详情面板。

A 3D nebula-field visualization of every project you've ever worked on. Click through to view individual sessions and the discussion-decision pairs within them.

**Universe view:**

- 🌌 Projects render as **nebula galaxies** on a golden-angle spiral
- 💫 **Liveness system** — alive projects breathe; stale projects dim and noise-over
- 🎨 **Shader-animated nebulae** — curl-noise + FBM erosion + particle diffusion

**Click a galaxy → Solar-system view:**

- Camera flies in to that project's session constellation
- Each session is a star node; click for a brief hover-card

**Click a session → Discussion-Decision Graph Panel:**

- 📂 **Sidebar switches** to that project's discussion-decision pairs (topic + date)
- 🖱️ **Click a pair** → opens pre-cut conversation thread (loads **instantly** — no runtime Haiku)
- 🚀 **"打开 Session" button** → `claude --resume <uuid>` in your system terminal

![panel](https://github.com/axzhang1216/apocalypse-claude-skill/raw/main/screenshot-workspace-panel.jpeg)

> Performance: discussion-decision threads are **pre-cut at init time** and pre-summarized, so opening a panel is instant. No API calls during browsing.

---

### 功能 3 · 命令行选择项目并打开 — CLI Launcher

**A keyboard-driven TUI to browse recent sessions or pick a project, then resume in your terminal.**

```bash
apocalypse              # 5 个最近 session → 详情 → claude --resume
apocalypse --list       # 输出 JSON（non-interactive）
```

**Two browsing modes:**

1. **Recent sessions** — shows the 5 most-recent sessions with goal + project + relative time
2. **Browse by project** — list of all projects (with thematic tags) → sessions within a project → start a new conversation OR resume an old one

**Detail view** shows: `user_goal`, `summary`, `outcome` (✅/△/✖), original user/assistant messages.

**Cross-platform terminal launch:**

| OS | Terminal |
|---|---|
| Windows (Git Bash / MSYS) | Windows Terminal (`wt.exe`) or `cmd /k` |
| macOS | Terminal.app via a generated `.command` script |
| Linux | XDG `x-terminal-emulator` → `gnome-terminal` → `konsole` → `xfce4-terminal` → `alacritty` → `kitty` → `xterm` |

---

## 🔌 插件 / Plugin — apocalypse-openclaw (Remote Control)

**Remote-control your local Claude Code sessions from anywhere — chat with them, ask them questions, unstick them, all from a remote interface.**

让远程 chat / 助手通过 Apocalypse API + `ccr code` CLI 操控本地 Claude Code session。

OpenClaw is a bridge that turns the Apocalypse HTTP API into a control surface for remote agents (e.g. OpenClaw chat). It treats every local Claude Code session as a queryable object.

**What you can do remotely:**

| Action | Method |
|--------|--------|
| 📋 List all sessions | `GET http://localhost:7749/api/sessions2` |
| 📖 Read any session's transcript | `GET http://localhost:7749/api/sessions2/<id>` |
| 💬 Ask a past session a question | `ccr code --resume <id> --print -p "your question"` |
| 🚨 Detect stuck sessions (waiting for input) | Check `status: "waiting"` in `~/.claude/sessions/<PID>.json` |
| 🛑 Kill stuck process | `Stop-Process -Id <PID> -Force` |
| ✅ Approve permission prompts / answer choices | `ccr code --resume <id> --print -p "y"` |
| 🔧 Fix corrupted JSONL (after concurrent writes) | Filter valid JSON lines from `.jsonl` |

**Requirements:**

- Apocalypse dashboard running at `http://localhost:7749` (this repo)
- `ccr code` CLI in PATH (Claude Code wrapped by [claude-code-router](https://github.com/musistudio/claude-code-router))

**Files:** `skills/apocalypse-openclaw/SKILL.md`

---

## Install

```bash
git clone https://github.com/axzhang1216/apocalypse-claude-skill.git
cd apocalypse-claude-skill
bash install.sh
```

Cross-platform: Windows (Git Bash), macOS, Linux.

The installer:
- Copies files to `~/.claude/skills/apocalypse/`
- Registers three Claude Code hooks (`PreToolUse`, `PostToolUse`, `Stop`)
- Adds `apocalypse` launcher to your shell rc (`.zshrc` / `.bashrc` / fish `config.fish`)

## Usage

Open any Claude Code session and type:

```
/apocalypse
```

Dashboard opens at **http://localhost:7749**. Workspace view at **http://localhost:7749/workspace.html**.

To stop the server:

```bash
kill $(cat ~/.claude/apocalypse/server.pid)
```

## How it works

- `start.sh` starts a Python HTTP server on port 7749 and registers three Claude Code hooks in `~/.claude/settings.local.json`
- The hooks write events to `~/.claude/apocalypse/events.jsonl` and trigger SSE pushes to connected browsers
- The server reads session data directly from `~/.claude/projects/` (Claude Code's native transcript store) — no token usage, pure file I/O
- Workspace init reads the same transcripts and produces `~/.claude/apocalypse/workspace.json`
- All hooks are idempotent; running `start.sh` twice is safe

## Files

```
apocalypse-claude-skill/
├── README.md            # This file
├── SKILL.md             # Claude Code skill definition (trigger: /apocalypse)
├── install.sh           # One-step installer (cross-platform)
├── start.sh             # Startup script (server + hook registration)
├── server.py            # Python stdlib HTTP + SSE server (port 7749)
├── dashboard.html       # Real-time session dashboard
├── workspace.html       # 3D workspace + discussion-decision panel
├── workspace_init.py    # Workspace builder (Haiku classification + extraction)
├── apocalypse.py        # CLI launcher
├── apocalypse.sh        # Unix launcher wrapper
├── apocalypse.cmd       # Windows launcher wrapper
├── platform_utils.py    # Cross-platform terminal + path helpers
├── hooks/
│   ├── on-tool.sh       # PreToolUse + PostToolUse hook
│   └── on-stop.sh       # Stop hook
├── skills/
│   └── apocalypse-openclaw/
│       └── SKILL.md     # Plugin: remote-control Claude Code via Apocalypse API
└── assets/              # Nebula textures, Three.js bundle
```

## Data locations

| Path | Purpose |
|------|---------|
| `~/.claude/apocalypse/events.jsonl` | Live event stream from hooks |
| `~/.claude/apocalypse/workspace.json` | Workspace data (projects, sessions, points) |
| `~/.claude/apocalypse/sessions/` | Session snapshots |
| `~/.claude/projects/` | Read-only: Claude Code's native transcript store |

## License

MIT
