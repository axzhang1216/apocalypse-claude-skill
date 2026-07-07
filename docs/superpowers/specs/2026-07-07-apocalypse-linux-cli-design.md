# Apocalypse Linux CLI — Design

**Status**: Draft
**Date**: 2026-07-07
**Author**: Apocalypse dev (brainstorming session)

## 1. Problem

Apocalypse is a real-time monitoring dashboard for Claude Code / OpenAI Codex sessions. Its web UI (dashboard.html + workspace.html) requires a browser — useless on SSH / headless Linux servers or in tmux without a forwarded display.

The existing CLI launcher (`apocalypse.py`) is already cross-platform: it works on Linux and shows a menu of recent sessions, project picker, session detail, and resumes in a new terminal. But two things the web UI does have no CLI equivalent:

1. **Full session transcript** — the web dashboard shows every user/assistant turn and tool call for any session, live or past. The CLI only shows a 1-line goal/summary.
2. **Workspace map** — the web workspace.html renders a 3D nebula of all projects with drill-down into sessions and discussion-decision points. The CLI has no project map; users have to remember project titles or use `--list` JSON.

This design adds a Linux-first, SSH-friendly CLI version that keeps the existing menu 100% intact and adds the two missing views.

### Non-goals

- Replacing the web UI. The web stays the primary interface for desktop users.
- TUI parity with all 3D nebula features (camera, particle physics, etc.) — spatial info is intentionally sacrificed.
- Re-architecture of hooks, server.py, or workspace.html.
- Supporting non-stdlib Python dependencies.

### Target environment

**Primary**: SSH session on a Linux server with no DISPLAY, no GUI terminal, no local browser.
**Secondary**: Local Linux desktop where the user happens to prefer the terminal.
**Maintained for compatibility**: macOS, Windows (existing menu keeps working).

## 2. Architecture

Convert the top-level `skills_apocalypse/apocalypse.py` (currently 1172 lines) into a thin wrapper around a new `apocalypse/` Python package:

```
skills_apocalypse/
├── apocalypse/                # NEW package
│   ├── __init__.py            # version, expose main
│   ├── __main__.py            # argparse dispatch, headless detection, resume routing
│   ├── launcher.py            # MOVED from apocalypse.py: existing menu code
│   ├── log_view.py            # NEW: interactive pager for session transcripts
│   ├── workspace_view.py      # NEW: multi-level project tree
│   ├── tui.py                 # NEW: shared TUI primitives (pager, colour, keymap)
│   ├── platform_utils.py      # unchanged
│   └── codex_workspace.py     # unchanged
├── apocalypse.py              # 5-line wrapper: from apocalypse.__main__ import main; main()
├── apocalypse.sh              # unchanged
├── SKILL.md, install.sh, start.sh, hooks/, ...   # unchanged
└── tests/                     # NEW
    ├── fixtures/              # sample jsonl transcripts
    ├── snapshots/             # rendered-output snapshots
    └── ...                    # unittest files
```

**Why a package, not a longer single file?** TUI primitives (termios cbreak loop, ANSI colour, SIGWINCH handling) are the core of the new views. Duplicating them across top-level modules invites divergent bug fixes (the existing `Menu._loop_tty` already shows the cost — Windows and Linux code paths diverged into `_win_run`).

**Why not a separate `apocalypse-tui` binary?** The user's request explicitly says "保留 apocalypse 的所有命令行功能" — keeping the menu is non-negotiable. A separate binary either duplicates the menu or doesn't integrate with it.

## 3. CLI Surface

### Subcommands

| Invocation | Behaviour |
|---|---|
| `apocalypse` (no args) | Existing menu (unchanged) |
| `apocalypse log <sid>` | Interactive pager for a session transcript |
| `apocalypse log <sid> --raw` | ANSI-coloured transcript, no pager (for `less -R` piping) |
| `apocalypse log <sid> --tail` | Watch the session live (SSE-style tail) |
| `apocalypse workspace` | Multi-level project tree |
| `apocalypse workspace --search=<q>` | Pre-fill filter query |
| `apocalypse --update` | Existing |
| `apocalypse --refresh` | Existing |
| `apocalypse --list` | Existing (JSON) |
| `apocalypse --codex` | Existing (use Codex source) |

`--codex` flag still works with the new subcommands: `apocalypse --codex workspace` browses Codex sessions, `apocalypse --codex log <sid>` views a Codex transcript.

### Entry dispatch

```python
# apocalypse/__main__.py
def main():
    args = parse_args()
    if args.subcommand == "log":
        return log_view.run(args.session_id, raw=args.raw, tail=args.tail)
    if args.subcommand == "workspace":
        return workspace_view.run(search=args.search, codex=args.codex)
    # No subcommand: existing menu
    return launcher.run(args)
```

### Headless detection

```python
def is_headless() -> bool:
    """True when the user has no usable GUI terminal launcher."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return True
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return True
    return False
```

In headless mode:

- `launch_session()` does **not** call `launch_in_terminal()`. It prints:
  ```
  Resume command (paste in your other shell):
    cd <cwd> && claude --resume <sid>
  ```
  and waits for the user to press Enter before returning to the menu.
- `launch_new_conversation()` behaves identically.
- The menu footer adds `[headless mode] Resume prints the command only — copy & paste in another shell`.

In GUI mode (default behaviour) the existing `launch_in_terminal()` is used unchanged.

## 4. TUI shared layer — `tui.py`

### Style

```python
class Style:
    """ANSI colour wrapper. NO_COLOR=1 or TERM=dumb → empty strings."""
    def __init__(self):
        self.enabled = (
            sys.stdout.isatty()
            and not os.environ.get("NO_COLOR")
            and os.environ.get("TERM") != "dumb"
        )
    def bold(self, s): return f"\033[1m{s}\033[0m" if self.enabled else s
    def dim(self, s): return f"\033[2m{s}\033[0m" if self.enabled else s
    def red(self, s): return f"\033[31m{s}\033[0m" if self.enabled else s
    # ... green, yellow, blue, magenta, cyan
```

Visual characters. When `Style.enabled` is False, every glyph falls back to ASCII so the output stays terminal-portable:

| Glyph | ASCII fallback | Used for |
|---|---|---|
| `▁▂▃▄▅▆▇█` | `--------` (same length) | bar charts |
| `▣` | `*` | project marker |
| `⚙` | `#` | tool_use |
| `📖` | `R` | Read tool |
| `▶` | `>` | action |
| `⏎` | `@` | enter |
| `↩` | `<` | back |
| `▸` | `*` | point/discussion |
| `»` | `>>` | filter match |
| `✅` | `+` | tool ok |
| `❌` | `x` | tool error |
| `→` | `->` | arrow |

Colour is independently suppressed (no `\033[…m` sequences emitted).

### Terminal size

```python
def term_size() -> tuple[int, int]:
    """Returns (cols, rows). Handles missing stty gracefully."""
    try:
        s = shutil.get_terminal_size((80, 24))
        return s.columns, s.lines
    except Exception:
        return (80, 24)
```

A SIGWINCH handler updates an internal cache; the next render uses the new size. No exception path on resize.

### Raw key input

```python
class RawInput:
    """Wraps termios cbreak (POSIX) or msvcrt (Windows).
    read_key() returns one of:
      single character: 'j', 'q', 'G', ...
      named: 'UP', 'DOWN', 'PAGE_UP', 'PAGE_DOWN', 'HOME', 'END', 'ESC', 'ENTER', 'BACKSPACE'
    """
```

Mirrors the existing `Menu._loop_tty` / `Menu._win_run` split. Escape-sequence parsing is unified (single helper that reads `\x1b[A` style sequences).

### Pager

```python
class Pager:
    """Generic full-screen pager. Accepts a list of pre-rendered lines
    plus a search highlight callback. Manages the key loop."""
    def __init__(
        self,
        lines: list[str],
        *,
        status: Callable[[PagerState], str] | None = None,
        search_match: Callable[[str], bool] | None = None,
        on_key: Callable[[str, PagerState], PagerState | None] | None = None,
    ): ...
    def run(self) -> None: ...
    def quit(self) -> None: ...
```

`on_key` lets a caller add custom keys (e.g. `t` for "toggle tool expansion" in log view) without subclassing.

`Pager.run()` guarantees on exit:
- `termios.tcsetattr` restores the original state.
- `\033[?25h` shows the cursor.
- `\033[0m` resets all attributes.

## 5. Log view — `apocalypse log <sid>`

### Data source

A new `load_messages(sid) -> list[Message]` function in `log_view.py`:
- Locates the jsonl via `_find_transcript(sid)` (imported from `apocalypse.py` during migration, then re-exported from `launcher.py`).
- Applies the existing `_is_noise` filter and `NOISE_PREFIXES` list.
- Normalises each surviving record into a `Message(role: Literal["user", "assistant"], ts: str, blocks: list[Block])`.
- `Block` is one of:
  - `TextBlock(text: str)`
  - `ToolUseBlock(tool_name: str, summary: str, full_input: str)`
  - `ToolResultBlock(content: str, is_error: bool, truncated: bool)`
- Extended thinking blocks (if any) are kept as a separate `ThinkingBlock` and rendered dim/collapsed by default. (Most transcripts don't have them, but Haiku extended thinking can produce them.)

This loader is structurally similar to `server.py:parse_conversation` (the dashboard's transcript parser) but lives separately in `log_view.py`. Unifying them is a future refactor — server.py is explicitly out of scope here.

### Rendering

`messages_to_lines(messages, *, expanded_tools: bool, width: int, style) -> list[str]` — pure function, fully unit-testable.

Default (collapsed) rendering:

```
[14:32:05] user
  我想给 apocalypse 加一个 Linux 版本...
[14:32:18] assistant
  好，我先看看现有 menu 跟 Linux 平台探测...
  ⚙ Bash
  📖 Read
  全平台代码看起来已经分流得很清楚...
[14:32:24] tool result
  ✅ Bash exited 0
  $ ls -la skills_apocalypse/
  drwxr-xr-x 12 user  user  4096 ...    [↓ 11 more lines]
```

With `expanded_tools=True`, tool_use and tool_result show their full input/output JSON.

### Colour scheme

| Element | Style |
|---|---|
| `[hh:mm:ss]` timestamp | dim |
| `user` | bold green |
| `assistant` | bold blue |
| `⚙ tool_name` (tool_use) | yellow |
| `✅ tool result ok` | yellow dim |
| `❌ tool result error` | red |
| `>>` search hit marker | bold black on yellow |
| `»` filter match marker | bold cyan |

All suppressed when `Style.enabled` is False.

### Keymap

```
j / ↓            next line
k / ↑            prev line
d                half-page down
u                half-page up
PgDn / Space     next page
PgUp / b         prev page
g                top
G                bottom
/ text           search forward
? text           search backward
n / N            next / prev match
t                toggle tool expansion (per-session, persists in memory)
q / Esc          quit
? / F1           help overlay
```

### `--raw` mode

No pager; no interaction. Output is identical ANSI-coloured text on stdout. Suitable for `apocalypse log <sid> --raw | less -R` or `apocalypse log <sid> --raw > transcript.ansi`.

If stdout is not a TTY and `--raw` is not given, automatically switch to `--raw` behaviour and write a one-line stderr note:

```
[apocalypse log] stdout is not a TTY — falling back to --raw mode. Pass --raw explicitly to silence this.
```

### `--tail` mode

Watch `events.jsonl` for new lines matching the session's `session_id`. When one arrives, re-parse the jsonl and refresh the display from the new tail position. (Same trick `server.py:tail_events` uses.)

## 6. Workspace view — `apocalypse workspace`

### Level 1: Top (all projects)

Provider auto-detection:

```python
def detect_provider() -> str:
    if args.codex: return "codex"
    codex_root = Path.home() / ".codex" / "sessions"
    claude_ws = WORKSPACE_FILE.exists()
    if codex_root.exists() and not claude_ws:
        return "codex"
    return "claude"
```

Renderer:

```
▣ Climate penalty论文  ▁▂▃▅▆▇  7 sessions  5d ago  学术, 气候, LaTeX
▣ Apocalypse监控仪表盘 ▂▃▅▆▇█  8 sessions  2h ago  前端, 3D可视化, AI工具
▣ Claude Code skill探索  ▁▁▂▂  3 sessions  2w ago  工具开发
```

- `load_projects()` is reused (Claude) or `load_codex_projects()` (Codex) — no re-implementation.
- Bar height = `int(log2(1 + n) * 2)` (clamped to 0..7) where `n` is session count. Same log-scaling the web uses for nebula size.
- Bar colour gradient: blue (small) → green → yellow (large). All suppressed when `Style.enabled` is False; bar becomes `...` of the same width.
- Tags: pick first 3 from `project["tags"]`, comma-separated.
- Sort: `last_active DESC` (existing behaviour from `load_projects`).
- `selected` row gets `>` prefix and bold title.

### Level 2: Project (sessions + aggregate items)

```
─── Climate penalty论文 ───────────────────────────────
  path: ~/workdir/climate-penalty
  sessions: 7    first: 05-07    last: 06-04

  > Sessions
    [06-04] 写第三节"方法"再投 Nature Climate Change     [done]  4 messages
    [06-02] 和导师过 rebuttal letter 第二轮               [done]  12 messages
    ...
  > Discussion points (12)
    [06-04] 怎样处理 IOA 表里的异常值
    ...

  Press Enter on a session to peek, or 'l' on the points row to drill in.
```

`Sessions` and `Discussion points` are aggregate items that drill into sub-lists. Individual session rows can also be Entered to peek.

### Level 3a: Session peek (read-only)

```
─── [06-04] 写第三节"方法"再投 Nature Climate Change ───
  project:  Climate penalty论文
  outcome:  completed
  category: 文档写作
  tool calls: 18 (Bash×9, Edit×6, Read×3)
  messages:  42

  ▶ View full chat           calls apocalypse log <sid>
  ⏎ View discussion points   next level
  ↩ Back                     previous level
```

### Level 3b: Discussion points (per session)

```
─── [06-04] Points ──────────────────────────────────────

  ▸ §3 方法部分的叙事顺序
    └ discussion  现有叙事是先讲模型再讲数据，是否需要反向？
    └ decision    保持现顺序；加一小节过渡说明

  ▸ 异常值的处理
    └ discussion  IOA 表里有几个极端 outlier
    └ decision    IQR 过滤后取中位数；表注里说明

  ...
```

Source: `workspace.json → projects[<key>].points[]`. Fields: `topic`, `decision`, `related_to`, `session_id`.

### Keymap

```
↑/k ↓/j            up / down
Enter / →/l        enter current row
← / h              previous level
g / G              top / bottom of current list
/                  enter filter mode (substring match)
/ then text        filter
Enter (in filter)  confirm filter
Esc (in filter)    clear filter
? / F1             help
Esc (top level)    quit workspace
q                  quit workspace
```

### Filter behaviour

- Substring match against title / goal / summary / tag (all visible text).
- Non-matching rows render dim; matching rows render normal with `»` marker.
- `Enter` always acts on the current row's real semantics (the marker is decorative, not a substitute).
- Filter persists across level changes within the same `apocalypse workspace` invocation; cleared on quit.

## 7. Error handling

| Scenario | Behaviour |
|---|---|
| `workspace.json` missing | exit 1 + stderr "Run `apocalypse --update` first" |
| `<session-id>` not found | exit 1 + stderr lists 3 closest session IDs from `--list` |
| jsonl record parse error (one row) | skip that row, stderr warn, continue |
| TTY not interactive + `apocalypse log` (no `--raw`) | auto-fall-back to `--raw` mode with stderr notice |
| Terminal < 60 cols or < 10 rows | one-line stderr warning, render at actual size (don't crash) |
| `Ctrl+C` in pager | catch SIGINT, restore termios, exit 130 |
| `NO_COLOR=1` or `TERM=dumb` | Style.enabled = False; bars and symbols become ASCII (see `tui.py` table); colour sequences suppressed |
| `SSH_CONNECTION` set + no DISPLAY | headless mode active; resume prints command only |
| Both Claude and Codex data sources empty | exit 1 + stderr "No apocalypse data found. Run `apocalypse --update` or launch a Claude/Codex session first." |
| `apocalypse workspace` with no projects in workspace.json | exit 1 + same "run --update" hint |

## 8. Testing strategy

### Unit tests (stdlib `unittest`, no pytest dependency)

| Test file | Coverage |
|---|---|
| `test_parse_messages.py` | jsonl → Message list: noise filtering, tool_use/result extraction, NOISE_PREFIXES |
| `test_render_log.py` | `messages_to_lines` outputs correct line counts, tool collapse/expand states, search highlight, NO_COLOR paths |
| `test_render_workspace.py` | top/project/points/peek renderers — snapshot text comparison against `tests/snapshots/*.txt` |
| `test_pager_keymap.py` | mocked stdin feeds key sequences; assert scroll position, search results, quit path |
| `test_headless.py` | `is_headless()` with various env-var combinations |
| `test_args_dispatch.py` | every (subcommand, flag) combination → correct handler |

### Fixtures & snapshots

- `tests/fixtures/sample_session.jsonl` — a hand-crafted session with at least one of each: user text, assistant text, tool_use, tool_result, error result, system noise.
- `tests/snapshots/log_collapsed.txt`, `log_expanded.txt`, `workspace_top.txt`, etc. — golden output captured via `Style(enabled=True)` for deterministic comparison.

### Manual test plan (Linux + SSH)

```bash
# Local Linux with DISPLAY
apocalypse                       # menu works
apocalypse --list                # JSON output works
apocalypse log <known-sid>       # pager opens; j/k/g/G/PgDn/quit
apocalypse log <known-sid> --raw | less -R
apocalypse workspace             # 3-level nav

# SSH to localhost (no DISPLAY)
ssh localhost
apocalypse                       # menu opens; resume prints command
apocalypse log <known-sid>       # pager still works in tmux/screen
apocalypse workspace             # tree nav works
```

## 9. Migration steps

Each commit is independently revertible.

1. **commit 1** — add `apocalypse/` package skeleton (`__init__.py`, `__main__.py`, `tui.py` stubs). Top-level `apocalypse.py` becomes `from apocalypse.__main__ import main; main()`. The existing menu code is still in the top-level `apocalypse.py` until commit 2.
2. **commit 2** — move menu code (Menu class, recent_sessions_menu, project_select_flow, session_select_flow, show_detail, launch_session, etc.) into `apocalypse/launcher.py`. `__main__.py` imports it for the no-subcommand path. Top-level `apocalypse.py` stays as the wrapper. All existing flags (`--refresh`, `--update`, `--list`, `--codex`) still work.
3. **commit 3** — add `apocalypse/log_view.py` + `apocalypse log` subcommand route + unit tests.
4. **commit 4** — add `apocalypse/workspace_view.py` + `apocalypse workspace` route + unit tests.
5. **commit 5** — `is_headless()` + headless resume fallback.
6. **commit 6** — docs: SKILL.md, CLAUDE.md, this spec is updated as needed.

Smoke test after each commit:
```bash
apocalypse --list
apocalypse --refresh
apocalypse log <real-sid> --raw | head -50
apocalypse workspace
```

## 10. Documentation updates

### SKILL.md — new "CLI Subcommands" section

Add after the existing "## Standalone Workspace Update" section. Document:
- The subcommand table.
- `apocalypse log` keymap and `--raw` / `--tail` flags.
- `apocalypse workspace` keymap and three-level navigation.
- Headless mode (SSH) and how resume behaviour changes.

### CLAUDE.md — Architecture section update

- Replace the single-file description with the package layout.
- Add a "Headless mode" paragraph describing `is_headless()` and resume fallback.
- Add a "Subcommands" table.
- The "Workspace Visualization" and "History-export gotchas" sections are unchanged.

### Files NOT updated

- `install.sh` — alias already points to `apocalypse.py` which is still the wrapper.
- `start.sh`, `hooks/on-tool.sh`, `hooks/on-stop.sh` — unchanged.
- `server.py`, `dashboard.html`, `workspace.html` — unchanged.

## 11. Rollback

Each commit in section 9 is `git revert`-able. The new package is additive (new directory + thin wrapper replacement). Reverting the entire feature branch returns the repo to a single 1172-line `apocalypse.py` with no behavioural change.

## 12. Open questions for the implementation plan

These are decisions to revisit when writing-plans picks up:

- Should `apocalypse workspace` also accept `--raw` (no nav, dump a tree to stdout)? Probably yes for grep-friendliness; deferred to a follow-up.
- Should the bar chart log-scale constant be configurable? Probably not — `int(log2(1+n) * 2)` matches the web's nebula size formula and is good enough.
- Should `--tail` use polling (already what server.py does) or inotify (Linux only, more efficient)? Polling at 500ms is the conservative default; inotify as a future enhancement.
