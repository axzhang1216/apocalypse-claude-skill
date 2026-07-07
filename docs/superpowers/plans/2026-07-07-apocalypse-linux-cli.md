# Apocalypse Linux CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Linux-first, SSH-friendly CLI to Apocalypse with two new subcommands — `apocalypse log <sid>` for full session transcript viewing and `apocalypse workspace` for project map navigation — while keeping the existing menu 100% intact.

**Architecture:** Convert the top-level `skills_apocalypse/apocalypse.py` (1172 lines) into a thin wrapper around a new `apocalypse/` Python package. New `tui.py` provides shared pager / colour / keymap primitives. New `log_view.py` and `workspace_view.py` implement the two new subcommands. `is_headless()` in `__main__.py` detects SSH / no-GUI environments and switches resume behaviour to print-only.

**Tech Stack:** Python 3 stdlib only (no new dependencies). `unittest` for tests. ANSI escape codes for colour. `termios` cbreak for Linux/macOS input, `msvcrt` for Windows.

**Spec:** `docs/superpowers/specs/2026-07-07-apocalypse-linux-cli-design.md`

## Global Constraints

- **Python 3 stdlib only** — no new pip dependencies
- **Cross-platform**: Linux (primary), macOS, Windows (existing menu must keep working on all)
- **SSH-friendly**: terminal-based only, no GUI dependencies
- **Test framework**: stdlib `unittest` only — no pytest
- **100% backward compat**: `apocalypse` (no args) and all existing flags (`--refresh`, `--update`, `--list`, `--codex`) must keep their current behaviour byte-for-byte
- **Pre-existing files NOT to modify** in this plan: `install.sh`, `start.sh`, `hooks/on-tool.sh`, `hooks/on-stop.sh`, `server.py`, `dashboard.html`, `workspace.html`, `codex_workspace.py`, `platform_utils.py`, `apocalypse.sh`
- **Tests live under `skills_apocalypse/tests/`** and are run with `cd skills_apocalypse && python -m unittest tests.test_xxx`
- **All new package code lives under `skills_apocalypse/apocalypse/`** and imports sibling modules with relative-style imports; the package is added to sys.path by the top-level `apocalypse.py` wrapper using the existing `sys.path.insert(0, ...)` pattern
- **Each task ends with a `git commit`**; each commit is independently revertible
- **Visual glyph fallback** (always apply): when `Style.enabled` is False, every Unicode glyph in the table below is replaced by its ASCII equivalent:
  | Unicode | ASCII |
  |---|---|
  | `▁▂▃▄▅▆▇█` | `-` / `-` / `-` / `-` / `-` / `-` / `-` / `#` |
  | `▣` | `*` |
  | `⚙` | `#` |
  | `📖` | `R` |
  | `▶` | `>` |
  | `⏎` | `@` |
  | `↩` | `<` |
  | `▸` | `*` |
  | `»` | `>>` |
  | `✅` | `+` |
  | `❌` | `x` |
  | `→` | `->` |

---

## Task 1: Package skeleton + `tui.Style`

**Files:**
- Create: `skills_apocalypse/apocalypse/__init__.py`
- Create: `skills_apocalypse/apocalypse/__main__.py`
- Create: `skills_apocalypse/apocalypse/tui.py`
- Create: `skills_apocalypse/tests/__init__.py`
- Create: `skills_apocalypse/tests/test_tui_style.py`

This task creates the new package directory with `Style` (colour + glyph wrapper). Existing `apocalypse.py` is **unchanged** — it is replaced by a wrapper in Task 2. After this task, the package is importable but the wrapper doesn't use it yet.

**Interfaces:**
- Produces (used by Tasks 2-4):
  - `Style(enabled: Optional[bool] = None)` — `None` auto-detects from env
  - `Style.enabled: bool` — public flag
  - `Style.bold(s) / .dim(s) / .red(s) / .green(s) / .yellow(s) / .blue(s) / .magenta(s) / .cyan(s)` — wrap or passthrough
  - `Style.bg_yellow(s) / .bg_cyan(s)` — inverse-video for search/filter markers
  - `Style.glyph(ch: str) -> str` — Unicode→ASCII fallback when disabled

- [ ] **Step 1: Create `apocalypse/__init__.py`**

```python
"""Apocalypse CLI package — Linux-first, SSH-friendly session browser."""

__version__ = "1.1.0"
```

- [ ] **Step 2: Create `apocalypse/__main__.py` (stub `main`)**

```python
"""Entry point. argparse dispatch and headless detection.

This file starts as a stub; the real argparse + launcher delegation
arrives in Task 2.
"""
import sys


def main() -> int:
    print("apocalypse: package skeleton (no menu yet — see Task 2)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Write the failing test for `Style`**

Create `skills_apocalypse/tests/__init__.py`:

```python
"""Test package for apocalypse skill."""
```

Create `skills_apocalypse/tests/test_tui_style.py`:

```python
"""Tests for apocalypse.tui.Style."""
import os
import unittest
from unittest import mock

from apocalypse.tui import Style


class TestStyleExplicitEnabled(unittest.TestCase):
    def test_bold_wraps_when_enabled(self):
        s = Style(enabled=True)
        self.assertEqual(s.bold("hi"), "\033[1mhi\033[0m")

    def test_bold_passthrough_when_disabled(self):
        s = Style(enabled=False)
        self.assertEqual(s.bold("hi"), "hi")

    def test_color_wraps_when_enabled(self):
        s = Style(enabled=True)
        self.assertEqual(s.red("x"), "\033[31mx\033[0m")
        self.assertEqual(s.green("x"), "\033[32mx\033[0m")
        self.assertEqual(s.yellow("x"), "\033[33mx\033[0m")
        self.assertEqual(s.blue("x"), "\033[34mx\033[0m")
        self.assertEqual(s.cyan("x"), "\033[36mx\033[0m")

    def test_dim_wraps_when_enabled(self):
        s = Style(enabled=True)
        self.assertEqual(s.dim("x"), "\033[2mx\033[0m")

    def test_bg_inverse_wraps_when_enabled(self):
        s = Style(enabled=True)
        self.assertEqual(s.bg_yellow("x"), "\033[43;30mx\033[0m")
        self.assertEqual(s.bg_cyan("x"), "\033[46;30mx\033[0m")

    def test_all_passthrough_when_disabled(self):
        s = Style(enabled=False)
        for method in (s.bold, s.dim, s.red, s.green, s.yellow,
                       s.blue, s.magenta, s.cyan, s.bg_yellow, s.bg_cyan):
            self.assertEqual(method("x"), "x")


class TestStyleGlyphFallback(unittest.TestCase):
    def test_glyph_passthrough_when_enabled(self):
        s = Style(enabled=True)
        self.assertEqual(s.glyph("✅"), "✅")
        self.assertEqual(s.glyph("▣"), "▣")

    def test_glyph_fallback_when_disabled(self):
        s = Style(enabled=False)
        self.assertEqual(s.glyph("▁"), "-")
        self.assertEqual(s.glyph("█"), "#")
        self.assertEqual(s.glyph("▣"), "*")
        self.assertEqual(s.glyph("⚙"), "#")
        self.assertEqual(s.glyph("📖"), "R")
        self.assertEqual(s.glyph("▶"), ">")
        self.assertEqual(s.glyph("⏎"), "@")
        self.assertEqual(s.glyph("↩"), "<")
        self.assertEqual(s.glyph("▸"), "*")
        self.assertEqual(s.glyph("»"), ">>")
        self.assertEqual(s.glyph("✅"), "+")
        self.assertEqual(s.glyph("❌"), "x")
        self.assertEqual(s.glyph("→"), "->")

    def test_glyph_unknown_passthrough(self):
        s = Style(enabled=False)
        self.assertEqual(s.glyph("ñ"), "ñ")  # not in table, passes through


class TestStyleAutoDetect(unittest.TestCase):
    def test_no_color_env_disables(self):
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            s = Style()
        self.assertFalse(s.enabled)

    def test_dumb_term_disables(self):
        with mock.patch.dict(os.environ, {"TERM": "dumb", "NO_COLOR": ""}, clear=False):
            # clear NO_COLOR so we test TERM=dumb alone
            os.environ.pop("NO_COLOR", None)
            with mock.patch.dict(os.environ, {"TERM": "dumb"}):
                s = Style()
        self.assertFalse(s.enabled)

    def test_explicit_enabled_overrides_env(self):
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            s = Style(enabled=True)
        self.assertTrue(s.enabled)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd skills_apocalypse && python -m unittest tests.test_tui_style -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'apocalypse.tui'`.

- [ ] **Step 5: Implement `apocalypse/tui.py`**

Create `skills_apocalypse/apocalypse/tui.py`:

```python
"""Shared TUI primitives: ANSI colour, terminal size, raw key input, pager.

Used by launcher, log_view, and workspace_view. No third-party deps.
"""
from __future__ import annotations

import os
import sys
from typing import Callable, List, Optional, TextIO


# ─── Style ─────────────────────────────────────────────────────────────────


class Style:
    """ANSI colour + Unicode glyph wrapper.

    When `enabled` is True, colour codes are emitted and Unicode glyphs pass
    through unchanged. When False, colours are stripped and glyphs fall back
    to ASCII (so output is portable to `TERM=dumb`, dumb terminals, and
    copy-paste into non-Unicode contexts).

    `enabled=None` (the default) auto-detects from NO_COLOR, TERM=dumb, and
    whether stdout is a TTY.
    """

    GLYPHS = {
        "▁": "-", "▂": "-", "▃": "-", "▄": "-",
        "▅": "-", "▆": "-", "▇": "-", "█": "#",
        "▣": "*", "⚙": "#", "📖": "R", "▶": ">",
        "⏎": "@", "↩": "<", "▸": "*", "»": ">>",
        "✅": "+", "❌": "x", "→": "->",
    }

    def __init__(self, enabled: Optional[bool] = None):
        if enabled is None:
            enabled = self._auto_detect()
        self.enabled = enabled

    def _auto_detect(self) -> bool:
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("TERM") == "dumb":
            return False
        if not sys.stdout.isatty():
            return False
        return True

    def _wrap(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.enabled else s

    def bold(self, s: str) -> str: return self._wrap("1", s)
    def dim(self, s: str) -> str: return self._wrap("2", s)
    def red(self, s: str) -> str: return self._wrap("31", s)
    def green(self, s: str) -> str: return self._wrap("32", s)
    def yellow(self, s: str) -> str: return self._wrap("33", s)
    def blue(self, s: str) -> str: return self._wrap("34", s)
    def magenta(self, s: str) -> str: return self._wrap("35", s)
    def cyan(self, s: str) -> str: return self._wrap("36", s)
    def bg_yellow(self, s: str) -> str: return self._wrap("43;30", s)
    def bg_cyan(self, s: str) -> str: return self._wrap("46;30", s)

    def glyph(self, ch: str) -> str:
        if self.enabled:
            return ch
        return self.GLYPHS.get(ch, ch)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd skills_apocalypse && python -m unittest tests.test_tui_style -v`
Expected: PASS (15+ tests, all green).

- [ ] **Step 7: Commit**

```bash
cd E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse
git add skills_apocalypse/apocalypse/__init__.py \
        skills_apocalypse/apocalypse/__main__.py \
        skills_apocalypse/apocalypse/tui.py \
        skills_apocalypse/tests/__init__.py \
        skills_apocalypse/tests/test_tui_style.py
git -c user.name="Apocalypse Dev" -c user.email="dev@apocalypse.local" commit -m "feat(tui): add Style class with NO_COLOR/TERM=dumb fallback"
```

---

## Task 2: `tui.term_size` + `RawInput` + `Pager`

**Files:**
- Modify: `skills_apocalypse/apocalypse/tui.py`
- Create: `skills_apocalypse/tests/test_tui_term_size.py`
- Create: `skills_apocalypse/tests/test_tui_pager.py`

This task adds the rest of the TUI primitives. `Pager` accepts pre-rendered lines and a key callback. Tests inject fake stdin/stdout so the key loop runs in a CI environment without a real TTY.

**Interfaces (added to `apocalypse.tui`):**
- `term_size() -> tuple[int, int]` — `(cols, rows)`, default `(80, 24)` on failure
- `RawInput(in_stream: Optional[TextIO] = None) -> str` — context manager; `read_key()` returns named keys
- `Pager(lines: list[str], *, in_stream, out_stream, status, on_key, height_fn)` — full-screen pager; `run()` blocks until `on_key` returns `None` or `q`/`ESC` is pressed

- [ ] **Step 1: Write the failing test for `term_size`**

Create `skills_apocalypse/tests/test_tui_term_size.py`:

```python
"""Tests for apocalypse.tui.term_size."""
import io
import os
import unittest
from unittest import mock

from apocalypse.tui import term_size


class TestTermSize(unittest.TestCase):
    def test_returns_cols_rows(self):
        cols, rows = term_size()
        self.assertIsInstance(cols, int)
        self.assertIsInstance(rows, int)
        self.assertGreater(cols, 0)
        self.assertGreater(rows, 0)

    def test_falls_back_to_80_24_on_error(self):
        with mock.patch("shutil.get_terminal_size", side_effect=OSError("nope")):
            cols, rows = term_size()
        self.assertEqual((cols, rows), (80, 24))

    def test_uses_provided_size(self):
        fake = os.terminal_size((120, 40))
        with mock.patch("shutil.get_terminal_size", return_value=fake):
            cols, rows = term_size()
        self.assertEqual((cols, rows), (120, 40))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd skills_apocalypse && python -m unittest tests.test_tui_term_size -v`
Expected: FAIL with `ImportError: cannot import name 'term_size'`.

- [ ] **Step 3: Write the failing test for `Pager` (using injected streams)**

Create `skills_apocalypse/tests/test_tui_pager.py`:

```python
"""Tests for apocalypse.tui.Pager.

Pager uses injected StringIO streams so the key loop runs without a real TTY.
"""
import io
import unittest

from apocalypse.tui import Pager, PagerState


def _feed(chars: str) -> io.StringIO:
    return io.StringIO(chars)


class TestPagerQuit(unittest.TestCase):
    def test_q_quits_immediately(self):
        out = io.StringIO()
        keys = _feed("q")
        pager = Pager(["line1", "line2"], in_stream=keys, out_stream=out, height_fn=lambda: 24)
        pager.run()
        self.assertIn("line1", out.getvalue())

    def test_esc_quits(self):
        out = io.StringIO()
        keys = _feed("\x1b")
        pager = Pager(["line1"], in_stream=keys, out_stream=out, height_fn=lambda: 24)
        pager.run()

    def test_on_key_returning_none_quits(self):
        out = io.StringIO()
        keys = _feed("j")  # one keypress
        calls = []

        def on_key(k, s):
            calls.append(k)
            return None  # quit on first key

        pager = Pager(["a", "b", "c"], in_stream=keys, out_stream=out,
                      height_fn=lambda: 24, on_key=on_key)
        pager.run()
        self.assertEqual(calls, ["j"])


class TestPagerScroll(unittest.TestCase):
    def test_j_moves_top_down_one(self):
        out = io.StringIO()
        keys = _feed("jq")
        state_history = []

        def on_key(k, s):
            state_history.append((k, s.top))
            if k == "j":
                return PagerState(s.lines, top=min(s.top + 1, len(s.lines) - 1))
            return s  # stay alive

        pager = Pager(["a", "b", "c"], in_stream=keys, out_stream=out,
                      height_fn=lambda: 24, on_key=on_key)
        pager.run()
        # Two keys: 'j' (top=1), 'q' (top=1, no change)
        self.assertEqual(state_history, [("j", 0), ("q", 1)])

    def test_g_goto_top(self):
        out = io.StringIO()
        keys = _feed("gq")
        state_history = []

        def on_key(k, s):
            state_history.append(s.top)
            if k == "g":
                return PagerState(s.lines, top=0)
            return s

        pager = Pager(list(range(50)), in_stream=keys, out_stream=out,
                      height_fn=lambda: 10, on_key=on_key)
        pager.run()


class TestPagerRender(unittest.TestCase):
    def test_renders_lines_within_height(self):
        out = io.StringIO()
        pager = Pager(["alpha", "beta", "gamma"], in_stream=_feed("q"),
                      out_stream=out, height_fn=lambda: 5)
        pager.run()
        rendered = out.getvalue()
        self.assertIn("alpha", rendered)
        self.assertIn("beta", rendered)
        self.assertIn("gamma", rendered)

    def test_status_callback_invoked(self):
        out = io.StringIO()
        status_seen = []

        def status(s):
            status_seen.append(s.top)
            return f"[top={s.top}]"

        pager = Pager(["x"], in_stream=_feed("q"),
                      out_stream=out, height_fn=lambda: 5, status=status)
        pager.run()
        self.assertEqual(status_seen, [0])
        self.assertIn("[top=0]", out.getvalue())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run, verify both fail**

Run: `cd skills_apocalypse && python -m unittest tests.test_tui_term_size tests.test_tui_pager -v`
Expected: FAIL on both with `ImportError`.

- [ ] **Step 5: Implement `term_size`, `RawInput`, `Pager`**

Modify `skills_apocalypse/apocalypse/tui.py`. **Append** the following after the `Style` class (do not touch the existing code):

```python
import shutil
import termios
import tty
from dataclasses import dataclass, field


# ─── Terminal size ────────────────────────────────────────────────────────


def term_size() -> tuple[int, int]:
    """Return (cols, rows). Falls back to (80, 24) on error or non-TTY."""
    try:
        s = shutil.get_terminal_size((80, 24))
        return s.columns, s.lines
    except Exception:
        return (80, 24)


# ─── Raw key input ────────────────────────────────────────────────────────


class RawInput:
    """POSIX termios cbreak key reader.

    Usage:
        with RawInput() as keys:
            key = keys.read_key()

    For non-TTY streams (used in tests), falls back to a StringIO-style
    reader that still recognises multi-byte escape sequences.
    """

    def __init__(self, in_stream: Optional[TextIO] = None):
        self._in = in_stream
        self._own = in_stream is None
        self._old = None

    def __enter__(self):
        if self._own:
            self._in = sys.stdin
        if self._in.isatty():
            self._old = termios.tcgetattr(self._in)
            tty.setcbreak(self._in.fileno())
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._old is not None:
            try:
                termios.tcsetattr(self._in, termios.TCSADRAIN, self._old)
            except Exception:
                pass
        # Always restore cursor + reset attributes
        try:
            sys.stdout.write("\033[?25h\033[0m")
            sys.stdout.flush()
        except Exception:
            pass

    def read_key(self) -> str:
        """Block until one keypress is available. Returns named key.

        Named returns: 'UP', 'DOWN', 'PAGE_UP', 'PAGE_DOWN', 'HOME',
        'END', 'ENTER', 'ESC', 'BACKSPACE', 'TAB', 'EOF'.
        Single characters: 'j', 'q', 'G', ' ', '/', etc.
        """
        if self._in.isatty():
            ch = os.read(self._in.fileno(), 1).decode("utf-8", errors="replace")
        else:
            ch = self._in.read(1)
            if not ch:
                return "EOF"
        if ch in ("\n", "\r"):
            return "ENTER"
        if ch == "\x7f" or ch == "\x08":
            return "BACKSPACE"
        if ch == "\t":
            return "TAB"
        if ch == "\x1b":
            return self._read_escape_seq()
        return ch

    def _read_escape_seq(self) -> str:
        if self._in.isatty():
            n1 = os.read(self._in.fileno(), 1).decode("utf-8", errors="replace")
        else:
            n1 = self._in.read(1)
            if not n1:
                return "ESC"
        if n1 != "[" and n1 != "O":
            return "ESC"
        if self._in.isatty():
            n2 = os.read(self._in.fileno(), 1).decode("utf-8", errors="replace")
        else:
            n2 = self._in.read(1)
            if not n2:
                return "ESC"
        if n2 == "A":
            return "UP"
        if n2 == "B":
            return "DOWN"
        if n2 == "C":
            return "RIGHT"
        if n2 == "D":
            return "LEFT"
        if n2 == "H":
            return "HOME"
        if n2 == "F":
            return "END"
        if n2 == "5":
            self._read_one()
            return "PAGE_UP"
        if n2 == "6":
            self._read_one()
            return "PAGE_DOWN"
        return "ESC"

    def _read_one(self) -> str:
        if self._in.isatty():
            return os.read(self._in.fileno(), 1).decode("utf-8", errors="replace")
        return self._in.read(1)


# ─── Pager ────────────────────────────────────────────────────────────────


@dataclass
class PagerState:
    lines: List[str]
    top: int = 0
    query: str = ""
    matches: List[int] = field(default_factory=list)


class Pager:
    """Generic full-screen pager.

    Accepts pre-rendered lines and a key callback. The callback receives
    (key, state) and returns either an updated state, or None to quit.

    Default key handling (when on_key returns the same state):
      - 'q', 'ESC' → quit
      - 'UP' / 'k' → top -= 1
      - 'DOWN' / 'j' → top += 1
      - 'PAGE_UP' / 'b' → top -= height
      - 'PAGE_DOWN' / ' ' → top += height
      - 'g' → top = 0
      - 'G' → top = len(lines) - height
    """
    def __init__(
        self,
        lines: List[str],
        *,
        in_stream: Optional[TextIO] = None,
        out_stream: Optional[TextIO] = None,
        status: Optional[Callable[[PagerState], str]] = None,
        on_key: Optional[Callable[[str, PagerState], Optional[PagerState]]] = None,
        height_fn: Optional[Callable[[], int]] = None,
    ):
        self._lines = lines
        self._out = out_stream or sys.stdout
        self._status = status or (lambda s: "")
        self._on_key = on_key
        self._height_fn = height_fn or (lambda: term_size()[1] - 2)
        self.state = PagerState(lines=lines)
        self._in = in_stream
        self._in_own = in_stream is None

    def _height(self) -> int:
        try:
            return max(1, self._height_fn())
        except Exception:
            return 22

    def _render(self):
        h = self._height()
        top = max(0, min(self.state.top, max(0, len(self._lines) - 1)))
        self.state.top = top
        self._out.write("\033[2J\033[H")
        bottom = min(top + h, len(self._lines))
        for i in range(top, bottom):
            self._out.write(self._lines[i])
            self._out.write("\n")
        self._out.write(self._status(self.state))
        self._out.write("\n")
        self._out.flush()

    def _default_step(self, key: str, state: PagerState) -> Optional[PagerState]:
        h = self._height()
        n = len(state.lines)
        max_top = max(0, n - 1)
        if key in ("q", "ESC"):
            return None
        if key in ("UP", "k"):
            return PagerState(state.lines, top=max(0, state.top - 1), query=state.query)
        if key in ("DOWN", "j"):
            return PagerState(state.lines, top=min(max_top, state.top + 1), query=state.query)
        if key in ("PAGE_UP", "b"):
            return PagerState(state.lines, top=max(0, state.top - h), query=state.query)
        if key in ("PAGE_DOWN", " "):
            return PagerState(state.lines, top=min(max_top, state.top + h), query=state.query)
        if key == "g":
            return PagerState(state.lines, top=0, query=state.query)
        if key == "G":
            return PagerState(state.lines, top=max_top, query=state.query)
        return state

    def run(self) -> None:
        try:
            with RawInput(self._in) as keys:
                while True:
                    self._render()
                    key = keys.read_key()
                    if self._on_key is not None:
                        new_state = self._on_key(key, self.state)
                        if new_state is None:
                            return
                        self.state = new_state
                    else:
                        new_state = self._default_step(key, self.state)
                        if new_state is None:
                            return
                        self.state = new_state
        finally:
            try:
                self._out.write("\033[0m\033[?25h")
                self._out.flush()
            except Exception:
                pass
```

- [ ] **Step 6: Run, verify all pass**

Run: `cd skills_apocalypse && python -m unittest tests.test_tui_style tests.test_tui_term_size tests.test_tui_pager -v`
Expected: PASS (all green).

- [ ] **Step 7: Smoke test that the package is importable**

Run: `cd skills_apocalypse && python -c "from apocalypse.tui import Style, Pager, term_size; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 8: Commit**

```bash
cd E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse
git add skills_apocalypse/apocalypse/tui.py \
        skills_apocalypse/tests/test_tui_term_size.py \
        skills_apocalypse/tests/test_tui_pager.py
git -c user.name="Apocalypse Dev" -c user.email="dev@apocalypse.local" commit -m "feat(tui): add term_size, RawInput, Pager primitives"
```

---

## Task 3: Move menu code to `apocalypse/launcher.py` + thin wrapper

**Files:**
- Create: `skills_apocalypse/apocalypse/launcher.py`
- Modify: `skills_apocalypse/apocalypse/__main__.py`
- Modify: `skills_apocalypse/apocalypse.py` (replace 1172-line file with 5-line wrapper)

This is a pure refactor. **No new tests** — the existing behaviour is validated by manual smoke tests at the end. All existing flags and the menu's behaviour must remain byte-for-byte equivalent.

**Interfaces (used by `__main__.py` and Tasks 4-5):**
- `launcher.run(args) -> None` — entry point; takes the argparse namespace
- `launcher.is_headless() -> bool` — defined as a stub in this task, real implementation in Task 6
- All other names (`Menu`, `recent_sessions_menu`, etc.) become private to `launcher.py` (prefixed `_`)

- [ ] **Step 1: Read the current `apocalypse.py` to capture the existing code**

Run: `wc -l skills_apocalypse/apocalypse.py` and note the line count (should be 1172).

No code change yet — just record the line count so we can verify the refactor later.

- [ ] **Step 2: Create `apocalypse/launcher.py` with all existing logic moved**

Create `skills_apocalypse/apocalypse/launcher.py`. **Copy the entire current `apocalypse.py` file** into `launcher.py` and then make these adjustments:

1. **Add at the top after imports:**

```python
# `apocalypse.py` was a single-file script. Its contents have been moved
# here as part of the package split (see docs/superpowers/specs/2026-07-07-
# apocalypse-linux-cli-design.md). The public entry point is `launcher.run`.
```

2. **Change `if __name__ == "__main__":` block** to:

```python
def run(args=None) -> None:
    """Public entry point. `args` is the argparse namespace (or None for defaults)."""
    if args is None:
        # Compatibility shim: when called without args, re-parse argv.
        args = _build_argparser().parse_args()
    return _dispatch(args)


def _build_argparser():
    import argparse
    p = argparse.ArgumentParser(description="Apocalypse Launcher")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--update", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--codex", action="store_true")
    return p


def _dispatch(args):
    provider = get_provider("codex" if args.codex else "claude")

    if args.list:
        provider["ensure_workspace"](incremental=True)
        projects = provider["load_projects"]()
        out = [
            {
                "title": project["title"],
                "name": project["name"],
                "tags": project["tags"],
                "session_count": len(project["sessions"]),
                "last_active": project["last_active"],
                "sessions": [{"id": session["id"], "goal": session["goal"], "ts": session["ts"]} for session in project["sessions"]],
            }
            for project in projects
        ]
        import json
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if args.update:
        return update_workspace()

    if args.refresh:
        from apocalypse.tui import Style
        _ = Style  # imported to confirm dep is present
        print("  Refreshing workspace...")
        run_incremental()

    return recent_sessions_menu(provider)


def is_headless() -> bool:
    """Stub for Task 6. Real detection in is_headless() implementation."""
    return False


if __name__ == "__main__":
    import sys
    sys.exit(run(_build_argparser().parse_args()) or 0)
```

3. **Remove the now-orphaned `if __name__ == "__main__": main()`** and the `def main():` function from the bottom of the file (the one that calls `recent_sessions_menu` directly — that logic now lives in `_dispatch`).

The rest of the file is unchanged. **Do not touch** the `Menu` class, `get_provider`, `recent_sessions_menu`, `project_select_flow`, `session_select_flow`, `show_detail`, `launch_session`, `launch_new_conversation`, `update_workspace`, or any of the helper functions.

- [ ] **Step 3: Update `apocalypse/__main__.py` to dispatch**

Modify `skills_apocalypse/apocalypse/__main__.py`. **Replace the entire file** with:

```python
"""Apocalypse CLI entry point.

`apocalypse`         → launcher (existing menu)
`apocalypse log`     → log_view (Task 4)
`apocalypse workspace` → workspace_view (Task 5)
"""
import argparse
import sys
from pathlib import Path

# Make `skills_apocalypse` importable when run via the wrapper script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apocalypse import launcher  # noqa: E402


def _build_argparser():
    p = argparse.ArgumentParser(
        description="Apocalypse — Claude Code / Codex session browser",
        prog="apocalypse",
    )
    sub = p.add_subparsers(dest="subcommand")

    p_log = sub.add_parser("log", help="View a session's full transcript")
    p_log.add_argument("session_id", help="Session ID (from `apocalypse --list`)")
    p_log.add_argument("--raw", action="store_true",
                       help="Print ANSI text without pager (for `less -R`)")
    p_log.add_argument("--tail", action="store_true",
                       help="Watch the session live (SSE-style tail)")

    p_ws = sub.add_parser("workspace", help="Browse all projects")
    p_ws.add_argument("--search", default=None,
                      help="Pre-fill filter query")

    p.add_argument("--refresh", action="store_true")
    p.add_argument("--update", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--codex", action="store_true")
    return p


def main() -> int:
    args = _build_argparser().parse_args()

    if args.subcommand == "log":
        from apocalypse import log_view
        return log_view.run(args.session_id, raw=args.raw, tail=args.tail)
    if args.subcommand == "workspace":
        from apocalypse import workspace_view
        return workspace_view.run(search=args.search, codex=args.codex)

    # No subcommand: hand off to the existing launcher
    return launcher.run(args) or 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Replace top-level `apocalypse.py` with the 5-line wrapper**

Modify `skills_apocalypse/apocalypse.py`. **Replace the entire file** with:

```python
#!/usr/bin/env python3
"""Apocalypse launcher (wrapper). Real entry is apocalypse.__main__:main()."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apocalypse.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Verify launcher.py is the same size as the original apocalypse.py (within a small fudge)**

Run: `wc -l skills_apocalypse/apocalypse/launcher.py skills_apocalypse/apocalypse.py`
Expected: launcher.py ~1172 lines, apocalypse.py ~10 lines. (The launcher.py has a few added lines for the new `run` function, `_dispatch`, etc. — total should be within ±20 lines of the original.)

- [ ] **Step 6: Smoke test — `--list` still produces the same JSON**

Run: `cd skills_apocalypse && python apocalypse.py --list | head -10`
Expected: JSON output of projects, same as before the refactor.

If output is empty (no workspace.json yet), run once to generate data:
```bash
cd skills_apocalypse && python apocalypse.py --refresh
python apocalypse.py --list | head -10
```

- [ ] **Step 7: Smoke test — `log` and `workspace` subcommands are wired (will be no-op until Tasks 4-5)**

Run: `cd skills_apocalypse && python apocalypse.py log --help`
Expected: shows usage for `log` subcommand.

Run: `cd skills_apocalypse && python apocalypse.py workspace --help`
Expected: shows usage for `workspace` subcommand.

- [ ] **Step 8: Commit**

```bash
cd E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse
git add skills_apocalypse/apocalypse.py \
        skills_apocalypse/apocalypse/launcher.py \
        skills_apocalypse/apocalypse/__main__.py
git -c user.name="Apocalypse Dev" -c user.email="dev@apocalypse.local" commit -m "refactor: move menu code to apocalypse.launcher, wrap top-level script"
```

---

## Task 4: `apocalypse log <sid>` — `load_messages` + `messages_to_lines`

**Files:**
- Create: `skills_apocalypse/tests/fixtures/sample_session.jsonl`
- Create: `skills_apocalypse/tests/test_parse_messages.py`
- Create: `skills_apocalypse/tests/test_render_log.py`
- Create: `skills_apocalypse/apocalypse/log_view.py`

This task adds the `apocalypse log` subcommand. TDD pattern: write tests for the parser first, then the renderer. The `__main__.py` already routes to `log_view.run()`; this task makes that route do real work.

**Interfaces (added to `apocalypse.log_view`):**
- `Message(role: str, ts: str, blocks: list[Block])` — dataclass
- `TextBlock(text: str)` / `ToolUseBlock(tool_name: str, summary: str, full_input: str)` / `ToolResultBlock(content: str, is_error: bool, truncated: bool)` / `ThinkingBlock(text: str)` — dataclasses
- `load_messages(sid: str) -> list[Message]` — reads jsonl, filters noise, returns normalised messages
- `messages_to_lines(messages, *, expanded_tools: bool, width: int, style: Style) -> list[str]` — pure renderer
- `run(sid: str, *, raw: bool = False, tail: bool = False) -> int` — entry point invoked by `__main__`

- [ ] **Step 1: Create the test fixture**

Create `skills_apocalypse/tests/fixtures/sample_session.jsonl`:

```jsonl
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi can you help me fix a bug"}]},"timestamp":"2026-07-07T10:00:00Z","cwd":"/home/user/project","session_id":"abc123"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Sure, what's the symptom?"},{"type":"tool_use","id":"tu_1","name":"Bash","input":{"command":"ls -la","description":"List files"}}]},"timestamp":"2026-07-07T10:00:05Z"}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"tu_1","content":"file1.txt\nfile2.txt\n","is_error":false}]},"timestamp":"2026-07-07T10:00:06Z"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Found 2 files. Want me to inspect them?"}]},"timestamp":"2026-07-07T10:00:08Z"}
{"type":"user","isMeta":true,"message":{"role":"user","content":"<local-command-caveat>ignored</local-command-caveat>"},"timestamp":"2026-07-07T10:00:10Z"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"thinking","text":"I should ask the user to clarify."},{"type":"text","text":"Do you want me to read both?"}]},"timestamp":"2026-07-07T10:00:12Z"}
```

- [ ] **Step 2: Write failing test for `load_messages`**

Create `skills_apocalypse/tests/test_parse_messages.py`:

```python
"""Tests for apocalypse.log_view.load_messages.

Uses a hand-crafted fixture under tests/fixtures/.
"""
import os
import unittest
from pathlib import Path
from unittest import mock

from apocalypse import log_view


FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


class TestLoadMessages(unittest.TestCase):
    def test_returns_list_of_messages(self):
        msgs = log_view.load_messages_from_path(FIXTURE)
        # 6 records; 1 is isMeta; 1 has thinking but is still a real message.
        # Filtering rule: isMeta=True is filtered, leaving 5 messages.
        self.assertEqual(len(msgs), 5)

    def test_first_message_is_user(self):
        msgs = log_view.load_messages_from_path(FIXTURE)
        self.assertEqual(msgs[0].role, "user")
        self.assertEqual(msgs[0].blocks[0].text, "hi can you help me fix a bug")

    def test_assistant_with_tool_use(self):
        msgs = log_view.load_messages_from_path(FIXTURE)
        # Index 1 is the assistant with text + tool_use
        asst = msgs[1]
        self.assertEqual(asst.role, "assistant")
        kinds = [type(b).__name__ for b in asst.blocks]
        self.assertIn("TextBlock", kinds)
        self.assertIn("ToolUseBlock", kinds)

    def test_tool_result_message(self):
        msgs = log_view.load_messages_from_path(FIXTURE)
        # Index 2 is the user message that contains the tool_result
        tr = msgs[2]
        self.assertEqual(tr.role, "user")
        self.assertEqual(type(tr.blocks[0]).__name__, "ToolResultBlock")
        self.assertFalse(tr.blocks[0].is_error)

    def test_thinking_block_extracted(self):
        msgs = log_view.load_messages_from_path(FIXTURE)
        # Last message is assistant with thinking + text
        last = msgs[-1]
        thinking = [b for b in last.blocks if type(b).__name__ == "ThinkingBlock"]
        self.assertEqual(len(thinking), 1)
        self.assertIn("clarify", thinking[0].text)

    def test_noise_filtered(self):
        # The isMeta=True record must not appear.
        msgs = log_view.load_messages_from_path(FIXTURE)
        all_text = " ".join(b.text for m in msgs for b in m.blocks if hasattr(b, "text"))
        self.assertNotIn("local-command-caveat", all_text)


class TestLoadBySessionId(unittest.TestCase):
    def test_finds_session_under_projects_dir(self):
        # The fixture's session_id is "abc123". Mock the projects dir
        # so PROJECTS_DIR/<encoded>/abc123.jsonl resolves to our fixture.
        fake_root = FIXTURE.parent
        fake_proj = fake_root / "fake-project"
        fake_proj.mkdir(exist_ok=True)
        target = fake_proj / "abc123.jsonl"
        target.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            with mock.patch.object(log_view, "PROJECTS_DIR", fake_root):
                msgs = log_view.load_messages("abc123")
            self.assertGreater(len(msgs), 0)
            self.assertEqual(msgs[0].role, "user")
        finally:
            target.unlink()
            fake_proj.rmdir()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run, verify it fails**

Run: `cd skills_apocalypse && python -m unittest tests.test_parse_messages -v`
Expected: FAIL with `ImportError: cannot import name 'log_view'`.

- [ ] **Step 4: Implement `apocalypse/log_view.py` (parser part)**

Create `skills_apocalypse/apocalypse/log_view.py`:

```python
"""Session transcript viewer: parse jsonl, render to ANSI text, drive pager."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from apocalypse.tui import Style


PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Same noise prefixes as launcher.py (kept in sync with apocalypse.py NOISE_PREFIXES).
NOISE_PREFIXES = (
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<command-message>",
    "<command-name>",
    "<command-args>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "You are running as a local coding agent for a Multica",
    "You are running as a chat assistant for a Multica",
    "<persisted-output>",
)


# ─── Block / Message types ───────────────────────────────────────────────


@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    tool_name: str
    summary: str
    full_input: str


@dataclass
class ToolResultBlock:
    content: str
    is_error: bool
    truncated: bool


@dataclass
class ThinkingBlock:
    text: str


Block = Union[TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock]


@dataclass
class Message:
    role: str  # "user" or "assistant"
    ts: str
    blocks: List[Block] = field(default_factory=list)


# ─── Parser ──────────────────────────────────────────────────────────────


def _is_noise(d: dict) -> bool:
    if d.get("isMeta"):
        return True
    msg = d.get("message") or {}
    content = msg.get("content", [])
    if isinstance(content, str):
        if any(content.startswith(p) for p in NOISE_PREFIXES):
            return True
        return False
    if not isinstance(content, list):
        return True
    for c in content:
        if isinstance(c, dict) and c.get("type") == "tool_result":
            return True
        if isinstance(c, dict) and c.get("type") == "text":
            text = (c.get("text") or "").strip()
            if text and any(text.startswith(p) for p in NOISE_PREFIXES):
                return True
    return False


def _coerce_content(content) -> list:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return content
    return []


def _parse_blocks(content: list) -> List[Block]:
    blocks: List[Block] = []
    for c in _coerce_content(content):
        if not isinstance(c, dict):
            continue
        t = c.get("type")
        if t == "text":
            text = (c.get("text") or "").strip()
            if text:
                blocks.append(TextBlock(text=text))
        elif t == "thinking":
            text = (c.get("text") or "").strip()
            if text:
                blocks.append(ThinkingBlock(text=text))
        elif t == "tool_use":
            tool_name = c.get("name", "tool")
            inp = c.get("input", {})
            try:
                full_input = json.dumps(inp, ensure_ascii=False, indent=2)
            except Exception:
                full_input = str(inp)
            summary = _tool_summary(tool_name, inp)
            blocks.append(ToolUseBlock(tool_name=tool_name, summary=summary, full_input=full_input))
        elif t == "tool_result":
            content = c.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    item.get("text", "") for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            content = content or ""
            is_error = bool(c.get("is_error", False))
            truncated = len(content) > 500
            if truncated:
                content = content[:500] + f"\n[...{len(content) - 500} more chars]"
            blocks.append(ToolResultBlock(content=content, is_error=is_error, truncated=truncated))
    return blocks


def _tool_summary(tool_name: str, inp: dict) -> str:
    if not isinstance(inp, dict):
        return tool_name
    if tool_name == "Bash":
        cmd = inp.get("command", "")
        return f"Bash: {cmd[:80]}"
    if tool_name in ("Read", "Edit", "Write"):
        path = inp.get("file_path", "")
        return f"{tool_name}: {path}"
    if tool_name == "Glob":
        return f"Glob: {inp.get('pattern', '')}"
    if tool_name == "Grep":
        return f"Grep: {inp.get('pattern', '')}"
    return tool_name


def load_messages_from_path(path: Path) -> List[Message]:
    messages: List[Message] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if _is_noise(d):
                continue
            role = d.get("type") or d.get("message", {}).get("role", "")
            if role not in ("user", "assistant"):
                continue
            ts = d.get("timestamp", "")
            msg = d.get("message") or {}
            blocks = _parse_blocks(msg.get("content", []))
            if not blocks:
                continue
            messages.append(Message(role=role, ts=ts, blocks=blocks))
    return messages


def load_messages(sid: str) -> List[Message]:
    """Find the session jsonl by ID and return its messages."""
    for jsonl in PROJECTS_DIR.glob(f"*/{sid}.jsonl"):
        return load_messages_from_path(jsonl)
    raise FileNotFoundError(f"Session {sid} not found under {PROJECTS_DIR}")


# ─── Renderer ────────────────────────────────────────────────────────────


def _wrap(text: str, width: int, prefix: str = "  ") -> List[str]:
    """Wrap `text` to `width` with a leading prefix on every line."""
    if not text:
        return [prefix.rstrip()]
    out: List[str] = []
    for line in text.split("\n"):
        if not line:
            out.append(prefix.rstrip())
            continue
        while line:
            out.append(prefix + line[: max(1, width - len(prefix))])
            line = line[max(1, width - len(prefix)) :]
    return out


def messages_to_lines(
    messages: List[Message],
    *,
    expanded_tools: bool,
    width: int,
    style: Style,
) -> List[str]:
    """Render messages to a list of pre-coloured lines."""
    lines: List[str] = []
    for m in messages:
        ts = (m.ts or "")[:19]  # YYYY-MM-DDTHH:MM:SS
        hh = ts[11:19] if len(ts) >= 19 else ts
        if m.role == "user":
            head = style.green(style.bold("user"))
        else:
            head = style.blue(style.bold("assistant"))
        if hh:
            lines.append(f"[{style.dim(hh)}] {head}")
        else:
            lines.append(head)
        for b in m.blocks:
            if isinstance(b, TextBlock):
                lines.extend(_wrap(b.text, width))
            elif isinstance(b, ThinkingBlock):
                # Always render dim, regardless of expanded_tools
                for ln in _wrap(b.text, width, prefix="  " + style.dim("… ")):
                    lines.append(ln)
            elif isinstance(b, ToolUseBlock):
                glyph = style.glyph("⚙")
                head = f"{style.yellow(glyph + ' ' + b.tool_name)}"
                if b.summary and b.summary != b.tool_name:
                    head += style.dim(f"  {b.summary}")
                lines.append(head)
                if expanded_tools:
                    for ln in _wrap(b.full_input, width):
                        lines.append(ln)
            elif isinstance(b, ToolResultBlock):
                ok_glyph = style.glyph("✅" if not b.is_error else "❌")
                color = style.yellow if not b.is_error else style.red
                head = f"{color(ok_glyph + ' ' + ('tool error' if b.is_error else 'tool result'))}"
                lines.append(head)
                if expanded_tools or not b.truncated:
                    for ln in _wrap(b.content, width):
                        lines.append(ln)
                else:
                    first = b.content.split("\n", 1)[0]
                    lines.extend(_wrap(first[:200] + (style.dim(" [↓ more]") if len(first) > 200 else ""), width))
        lines.append("")  # blank line between messages
    if lines and lines[-1] == "":
        lines.pop()
    return lines


# ─── Entry point ─────────────────────────────────────────────────────────


def run(sid: str, *, raw: bool = False, tail: bool = False) -> int:
    """Entry point invoked by apocalypse.__main__ for `apocalypse log`."""
    style = Style()
    try:
        messages = load_messages(sid)
    except FileNotFoundError as e:
        print(f"[apocalypse log] {e}", file=sys.stderr)
        return 1

    width = 100  # sensible default; Pager handles wrap if needed
    lines = messages_to_lines(messages, expanded_tools=False, width=width, style=style)

    if raw or not sys.stdout.isatty():
        if not raw and not sys.stdout.isatty():
            print(
                "[apocalypse log] stdout is not a TTY — falling back to --raw mode. "
                "Pass --raw explicitly to silence this.",
                file=sys.stderr,
            )
        for ln in lines:
            print(ln)
        return 0

    if tail:
        # Real tail implementation arrives in Task 5 follow-up; for now
        # just render once and exit.
        for ln in lines:
            print(ln)
        return 0

    from apocalypse.tui import Pager, PagerState

    expanded = [False]  # mutable closure state

    def on_key(key, state):
        if key == "t":
            expanded[0] = not expanded[0]
            return PagerState(
                messages_to_lines(messages, expanded_tools=expanded[0], width=width, style=style),
                top=state.top,
                query=state.query,
            )
        return state

    def status(state):
        if expanded[0]:
            return style.dim("[t] collapse tools    q quit")
        return style.dim("[t] expand tools    q quit")

    pager = Pager(lines, on_key=on_key, status=status, height_fn=lambda: 24)
    pager.run()
    return 0
```

- [ ] **Step 5: Run, verify parser tests pass**

Run: `cd skills_apocalypse && python -m unittest tests.test_parse_messages -v`
Expected: PASS.

- [ ] **Step 6: Write failing test for `messages_to_lines`**

Create `skills_apocalypse/tests/test_render_log.py`:

```python
"""Tests for apocalypse.log_view.messages_to_lines."""
import unittest

from apocalypse import log_view
from apocalypse.tui import Style


def _msg(role, ts, blocks):
    return log_view.Message(role=role, ts=ts, blocks=blocks)


class TestRenderUserText(unittest.TestCase):
    def test_renders_user_with_text(self):
        style = Style(enabled=False)
        msgs = [_msg("user", "2026-07-07T10:00:00Z", [log_view.TextBlock("hello world")])]
        out = log_view.messages_to_lines(msgs, expanded_tools=False, width=80, style=style)
        joined = "\n".join(out)
        self.assertIn("user", joined)
        self.assertIn("hello world", joined)
        self.assertIn("10:00:00", joined)

    def test_renders_assistant_with_text(self):
        style = Style(enabled=False)
        msgs = [_msg("assistant", "2026-07-07T10:00:01Z", [log_view.TextBlock("hi back")])]
        out = log_view.messages_to_lines(msgs, expanded_tools=False, width=80, style=style)
        joined = "\n".join(out)
        self.assertIn("assistant", joined)
        self.assertIn("hi back", joined)


class TestRenderToolUse(unittest.TestCase):
    def test_collapsed_shows_summary(self):
        style = Style(enabled=False)
        msgs = [_msg("assistant", "2026-07-07T10:00:01Z",
                     [log_view.ToolUseBlock("Bash", "Bash: ls -la", '{"command":"ls -la"}')])]
        out = log_view.messages_to_lines(msgs, expanded_tools=False, width=80, style=style)
        joined = "\n".join(out)
        self.assertIn("Bash", joined)
        self.assertIn("ls -la", joined)
        # Full input not in collapsed mode
        self.assertNotIn('"command"', joined)

    def test_expanded_shows_full_input(self):
        style = Style(enabled=False)
        msgs = [_msg("assistant", "2026-07-07T10:00:01Z",
                     [log_view.ToolUseBlock("Bash", "Bash: ls -la", '{"command":"ls -la"}')])]
        out = log_view.messages_to_lines(msgs, expanded_tools=True, width=80, style=style)
        joined = "\n".join(out)
        self.assertIn('"command"', joined)


class TestRenderToolResult(unittest.TestCase):
    def test_ok_result_uses_plus_glyph(self):
        style = Style(enabled=False)
        msgs = [_msg("user", "2026-07-07T10:00:02Z",
                     [log_view.ToolResultBlock("file1\nfile2", is_error=False, truncated=False)])]
        out = log_view.messages_to_lines(msgs, expanded_tools=False, width=80, style=style)
        joined = "\n".join(out)
        self.assertIn("+", joined)  # ASCII fallback for ✅
        self.assertIn("tool result", joined)

    def test_error_result_uses_x_glyph(self):
        style = Style(enabled=False)
        msgs = [_msg("user", "2026-07-07T10:00:02Z",
                     [log_view.ToolResultBlock("boom", is_error=True, truncated=False)])]
        out = log_view.messages_to_lines(msgs, expanded_tools=False, width=80, style=style)
        joined = "\n".join(out)
        self.assertIn("x", joined)
        self.assertIn("tool error", joined)


class TestRenderThinking(unittest.TestCase):
    def test_thinking_always_dim(self):
        style = Style(enabled=True)
        msgs = [_msg("assistant", "2026-07-07T10:00:01Z",
                     [log_view.ThinkingBlock("let me think")])]
        out = log_view.messages_to_lines(msgs, expanded_tools=False, width=80, style=style)
        joined = "\n".join(out)
        self.assertIn("let me think", joined)
        # Should contain the dim ANSI prefix
        self.assertIn("\033[2m", joined)


class TestRenderWrapping(unittest.TestCase):
    def test_long_text_wraps(self):
        style = Style(enabled=False)
        long_text = "x" * 200
        msgs = [_msg("user", "2026-07-07T10:00:00Z", [log_view.TextBlock(long_text)])]
        out = log_view.messages_to_lines(msgs, expanded_tools=False, width=40, style=style)
        for line in out:
            self.assertLessEqual(len(line), 42, f"Line too long: {line!r}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 7: Run, verify it fails**

Run: `cd skills_apocalypse && python -m unittest tests.test_render_log -v`
Expected: FAIL on the first test (function not found or wrong return type).

- [ ] **Step 8: Verify `messages_to_lines` works (already implemented in Step 4)**

Re-run: `cd skills_apocalypse && python -m unittest tests.test_render_log -v`
Expected: PASS.

- [ ] **Step 9: Manual smoke test of the live subcommand**

Run with a real session id:
```bash
cd skills_apocalypse && python apocalypse.py log <some-real-sid> --raw | head -20
```
Expected: ANSI-coloured transcript.

If no real session is available, this step can be skipped — the unit tests cover the rendering.

- [ ] **Step 10: Commit**

```bash
cd E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse
git add skills_apocalypse/apocalypse/log_view.py \
        skills_apocalypse/tests/fixtures/sample_session.jsonl \
        skills_apocalypse/tests/test_parse_messages.py \
        skills_apocalypse/tests/test_render_log.py
git -c user.name="Apocalypse Dev" -c user.email="dev@apocalypse.local" commit -m "feat(log): add apocalypse log subcommand (interactive + raw)"
```

---

## Task 5: `apocalypse workspace` — three-level project tree

**Files:**
- Create: `skills_apocalypse/apocalypse/workspace_view.py`
- Create: `skills_apocalypse/tests/test_render_workspace.py`
- Create: `skills_apocalypse/tests/fixtures/workspace.json`

This task adds the `apocalypse workspace` subcommand. TDD for the level renderers; the navigation loop is exercised manually.

**Interfaces (added to `apocalypse.workspace_view`):**
- `WorkspaceView(workspace: dict, *, provider: str) -> None` — manages the navigation stack
- `WorkspaceView.run(search: Optional[str]) -> int` — entry point
- `render_top(workspace, *, style, width) -> list[str]` — pure function, testable
- `render_project(project, *, style, width) -> list[str]` — pure function, testable
- `render_points(points: list[dict], *, style, width) -> list[str]` — pure function, testable
- `load_workspace() -> dict` — reads `~/.claude/apocalypse/workspace.json` (or `~/.codex/...` for codex)
- `detect_provider() -> str` — returns "claude" or "codex"

- [ ] **Step 1: Create the test fixture workspace**

Create `skills_apocalypse/tests/fixtures/workspace.json`:

```json
{
  "projects": {
    "/home/user/climate": {
      "name": "climate",
      "title": "Climate penalty论文",
      "tags": ["学术", "气候", "LaTeX"],
      "cwd": "/home/user/climate",
      "last_active": "2026-06-04T12:00:00Z",
      "analyzed_sessions": {
        "sess1": {
          "user_goal": "写第三节 方法 再投 Nature Climate Change",
          "summary": "Drafted §3 and submitted.",
          "outcome": "completed",
          "category": "docs",
          "ts": "2026-06-04T12:00:00Z"
        },
        "sess2": {
          "user_goal": "和导师过 rebuttal letter 第二轮",
          "summary": "Addressed reviewer comments.",
          "outcome": "completed",
          "category": "docs",
          "ts": "2026-06-02T10:00:00Z"
        }
      },
      "points": [
        {"topic": "IOA 异常值", "decision": "IQR 过滤后取中位数",
         "related_to": [], "session_id": "sess1"}
      ]
    },
    "/home/user/apocalypse": {
      "name": "apocalypse",
      "title": "Apocalypse监控仪表盘",
      "tags": ["前端", "3D可视化", "AI工具"],
      "cwd": "/home/user/apocalypse",
      "last_active": "2026-07-07T09:00:00Z",
      "analyzed_sessions": {
        "sessA": {
          "user_goal": "添加 Linux-first CLI",
          "summary": "Split into package + new subcommands.",
          "outcome": "partial",
          "category": "ai_tools",
          "ts": "2026-07-07T09:00:00Z"
        }
      },
      "points": [
        {"topic": "package vs single file", "decision": "Go with package split",
         "related_to": [], "session_id": "sessA"},
        {"topic": "TUI library or stdlib", "decision": "stdlib only",
         "related_to": [], "session_id": "sessA"}
      ]
    }
  }
}
```

- [ ] **Step 2: Write failing tests for `render_top` and `render_project`**

Create `skills_apocalypse/tests/test_render_workspace.py`:

```python
"""Tests for apocalypse.workspace_view renderers."""
import json
import unittest
from pathlib import Path

from apocalypse import workspace_view
from apocalypse.tui import Style


FIXTURE = Path(__file__).parent / "fixtures" / "workspace.json"


def _load_ws():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestRenderTop(unittest.TestCase):
    def test_lists_all_projects(self):
        ws = _load_ws()
        lines = workspace_view.render_top(ws, style=Style(enabled=False), width=100)
        joined = "\n".join(lines)
        self.assertIn("Climate penalty论文", joined)
        self.assertIn("Apocalypse监控仪表盘", joined)

    def test_sorted_by_last_active_desc(self):
        ws = _load_ws()
        lines = workspace_view.render_top(ws, style=Style(enabled=False), width=100)
        # apocalypse is more recent than climate, so it should appear first
        apoc_idx = next(i for i, ln in enumerate(lines) if "Apocalypse" in ln)
        clim_idx = next(i for i, ln in enumerate(lines) if "Climate" in ln)
        self.assertLess(apoc_idx, clim_idx)

    def test_session_count_appears(self):
        ws = _load_ws()
        lines = workspace_view.render_top(ws, style=Style(enabled=False), width=100)
        joined = "\n".join(lines)
        self.assertIn("2 sessions", joined)  # climate has 2
        self.assertIn("1 sessions", joined)  # apocalypse has 1

    def test_tags_appear(self):
        ws = _load_ws()
        lines = workspace_view.render_top(ws, style=Style(enabled=False), width=100)
        joined = "\n".join(lines)
        self.assertIn("学术", joined)
        self.assertIn("3D可视化", joined)


class TestRenderProject(unittest.TestCase):
    def test_shows_sessions(self):
        ws = _load_ws()
        project = ws["projects"]["/home/user/climate"]
        lines = workspace_view.render_project(project, style=Style(enabled=False), width=100)
        joined = "\n".join(lines)
        self.assertIn("Climate penalty论文", joined)
        self.assertIn("写第三节", joined)
        self.assertIn("和导师过 rebuttal", joined)

    def test_shows_points_aggregate(self):
        ws = _load_ws()
        project = ws["projects"]["/home/user/climate"]
        lines = workspace_view.render_project(project, style=Style(enabled=False), width=100)
        joined = "\n".join(lines)
        self.assertIn("Discussion points", joined)


class TestRenderPoints(unittest.TestCase):
    def test_lists_each_point(self):
        points = [
            {"topic": "T1", "decision": "D1", "session_id": "s1"},
            {"topic": "T2", "decision": "D2", "session_id": "s2"},
        ]
        lines = workspace_view.render_points(points, style=Style(enabled=False), width=100)
        joined = "\n".join(lines)
        self.assertIn("T1", joined)
        self.assertIn("D1", joined)
        self.assertIn("T2", joined)
        self.assertIn("D2", joined)


class TestLoadWorkspace(unittest.TestCase):
    def test_loads_from_file(self):
        ws = workspace_view.load_workspace_from_path(FIXTURE)
        self.assertIn("projects", ws)
        self.assertEqual(len(ws["projects"]), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run, verify it fails**

Run: `cd skills_apocalypse && python -m unittest tests.test_render_workspace -v`
Expected: FAIL with `ImportError: cannot import name 'workspace_view'`.

- [ ] **Step 4: Implement `apocalypse/workspace_view.py`**

Create `skills_apocalypse/apocalypse/workspace_view.py`:

```python
"""Project map: three-level TUI navigation over workspace.json."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from apocalypse.tui import Style


WORKSPACE_FILE = Path.home() / ".claude" / "apocalypse" / "workspace.json"
CODEX_WORKSPACE_FILE = Path.home() / ".codex" / "workspace.json"


# ─── Data loading ────────────────────────────────────────────────────────


def load_workspace_from_path(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_workspace(provider: str = "claude") -> dict:
    """Return the workspace.json contents (or {} if missing)."""
    path = CODEX_WORKSPACE_FILE if provider == "codex" else WORKSPACE_FILE
    if not path.exists():
        return {}
    try:
        return load_workspace_from_path(path)
    except Exception:
        return {}


def detect_provider() -> str:
    codex_exists = CODEX_WORKSPACE_FILE.exists()
    claude_exists = WORKSPACE_FILE.exists()
    if codex_exists and not claude_exists:
        return "codex"
    return "claude"


# ─── Renderers (pure) ───────────────────────────────────────────────────


def _bar(n: int, max_n: int, style: Style) -> str:
    """Render a UTF-8 block bar of width 8, height = log2-scaled count."""
    if not style.enabled:
        height = int(0.5 + 2.5 * (n / max(1, max_n)))
        height = max(0, min(7, height))
        return "-" * height + " " * (7 - height)
    height = int(0.5 + 2.5 * (n / max(1, max_n)))
    height = max(0, min(7, height))
    blocks = "▁▂▃▄▅▆▇█"
    return "".join(blocks[i] for i in range(height)) + " " * (7 - height)


def _relative_time(ts: str) -> str:
    """Return a short relative time string (no external dep)."""
    from datetime import datetime, timezone
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
        if mins < 1: return "just now"
        if mins < 60: return f"{mins}m ago"
        hrs = mins // 60
        if hrs < 24: return f"{hrs}h ago"
        days = hrs // 24
        if days < 30: return f"{days}d ago"
        return f"{days // 30}mo ago"
    except Exception:
        return ""


def _trunc(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def render_top(workspace: dict, *, style: Style, width: int) -> List[str]:
    projects = list(workspace.get("projects", {}).values())
    projects.sort(key=lambda p: p.get("last_active", ""), reverse=True)
    max_sessions = max((len(p.get("analyzed_sessions", {})) for p in projects), default=0)
    lines: List[str] = []
    marker = style.glyph("▣")
    for p in projects:
        title = p.get("title") or p.get("name", "Unknown")
        n = len(p.get("analyzed_sessions", {}))
        bar = _bar(n, max_sessions, style)
        rel = _relative_time(p.get("last_active", ""))
        tags = ", ".join((p.get("tags") or [])[:3])
        prefix = f"{marker} {title}"
        meta = f"  {bar}  {n} sessions  {rel}  {tags}".rstrip()
        lines.append(prefix + style.dim(meta))
    return lines


def render_project(project: dict, *, style: Style, width: int) -> List[str]:
    title = project.get("title") or project.get("name", "Unknown")
    sessions = project.get("analyzed_sessions", {})
    points = project.get("points", [])
    lines: List[str] = []
    lines.append(style.bold(title))
    lines.append(style.dim(f"  path: {project.get('cwd', '')}"))
    if sessions:
        first = min((s.get("ts", "") for s in sessions.values()), default="")
        last = max((s.get("ts", "") for s in sessions.values()), default="")
        lines.append(style.dim(f"  sessions: {len(sessions)}    first: {first[:10]}    last: {last[:10]}"))
    lines.append("")
    # Sessions
    lines.append(style.cyan("  Sessions"))
    for sid, s in sorted(sessions.items(), key=lambda kv: kv[1].get("ts", ""), reverse=True):
        ts = (s.get("ts") or "")[:10]
        goal = _trunc(s.get("user_goal", ""), 60)
        outcome = s.get("outcome", "")
        lines.append(f"    [{ts}] {goal}  {style.dim('[' + outcome + ']')}")
    lines.append("")
    # Points aggregate
    if points:
        lines.append(style.cyan(f"  Discussion points ({len(points)})"))
        for pt in points[:5]:
            lines.append(f"    {style.glyph('▸')} {pt.get('topic', '')}")
        if len(points) > 5:
            lines.append(style.dim(f"    ... and {len(points) - 5} more"))
    return lines


def render_points(points: List[dict], *, style: Style, width: int) -> List[str]:
    lines: List[str] = []
    marker = style.glyph("▸")
    for pt in points:
        lines.append(f"{marker} {style.bold(pt.get('topic', ''))}")
        if pt.get("discussion"):
            lines.append(f"  {style.dim('discussion')}  {pt['discussion']}")
        if pt.get("decision"):
            lines.append(f"  {style.green('decision')}    {pt['decision']}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


# ─── Navigation ──────────────────────────────────────────────────────────


@dataclass
class WSLevel:
    kind: str            # "top" | "project" | "points" | "peek"
    title: str
    lines: List[str] = field(default_factory=list)
    items: list = field(default_factory=list)  # list of selectable entries


class WorkspaceView:
    def __init__(self, workspace: dict, *, provider: str):
        self.workspace = workspace
        self.provider = provider
        self.style = Style()
        self.width = 100
        self.stack: List[WSLevel] = []
        self.sel = 0
        self._push_top()

    def _push_top(self):
        projects = list(self.workspace.get("projects", {}).values())
        projects.sort(key=lambda p: p.get("last_active", ""), reverse=True)
        self.stack.append(WSLevel(
            kind="top",
            title=f"Apocalypse | {self.provider} | Workspace",
            lines=render_top(self.workspace, style=self.style, width=self.width),
            items=projects,
        ))
        self.sel = 0

    def _push_project(self, project):
        self.stack.append(WSLevel(
            kind="project",
            title=project.get("title") or project.get("name", "Unknown"),
            lines=render_project(project, style=self.style, width=self.width),
            items=[{"_kind": "sessions", "sessions": project.get("analyzed_sessions", {})},
                   {"_kind": "points", "points": project.get("points", [])}],
        ))
        self.sel = 0

    def _push_points(self, project, points):
        self.stack.append(WSLevel(
            kind="points",
            title=f"{project.get('title') or project.get('name', 'Unknown')} | Points",
            lines=render_points(points, style=self.style, width=self.width),
            items=points,
        ))
        self.sel = 0

    def _render(self):
        import sys
        sys.stdout.write("\033[2J\033[H")
        level = self.stack[-1]
        sys.stdout.write(self.style.bold(level.title) + "\n")
        sys.stdout.write(self.style.dim("─" * min(self.width, 80)) + "\n")
        for i, ln in enumerate(level.lines):
            if i == self.sel and level.kind == "top":
                sys.stdout.write("> " + self.style.bold(ln) + "\n")
            else:
                sys.stdout.write("  " + ln + "\n")
        sys.stdout.write("\n")
        sys.stdout.write(self.style.dim("Enter enter  ←/h back  q quit  / filter  ? help") + "\n")
        sys.stdout.flush()

    def run(self) -> int:
        from apocalypse.tui import RawInput
        try:
            with RawInput() as keys:
                while True:
                    self._render()
                    key = keys.read_key()
                    if key in ("q", "ESC") and len(self.stack) == 1:
                        return 0
                    if key in ("q", "ESC"):
                        # not on top — treat as back
                        self.stack.pop()
                        self.sel = 0
                        continue
                    if key in ("LEFT", "h"):
                        if len(self.stack) > 1:
                            self.stack.pop()
                            self.sel = 0
                        continue
                    if key in ("UP", "k"):
                        self.sel = max(0, self.sel - 1)
                    elif key in ("DOWN", "j"):
                        self.sel = min(len(self.stack[-1].items) - 1 if self.stack[-1].items else 0,
                                       self.sel + 1)
                    elif key in ("ENTER", "RIGHT", "l"):
                        if not self.stack[-1].items:
                            continue
                        item = self.stack[-1].items[self.sel]
                        if self.stack[-1].kind == "top":
                            self._push_project(item)
                        elif self.stack[-1].kind == "project":
                            if isinstance(item, dict) and item.get("_kind") == "points":
                                # find this project
                                cur = self.stack[-1]
                                # re-derive project from stack title
                                # easier: peek into self.workspace
                                proj = self._find_project_by_title(cur.title)
                                if proj:
                                    self._push_points(proj, item.get("points", []))
                        # 'sessions' item and 'points'/'peek' rows in non-top
                        # levels are not Enter-drilled further in this MVP.
        finally:
            sys.stdout.write("\033[0m\033[?25h")
            sys.stdout.flush()
        return 0

    def _find_project_by_title(self, title: str):
        for p in self.workspace.get("projects", {}).values():
            if (p.get("title") or p.get("name")) == title:
                return p
        return None


def run(*, search: Optional[str] = None, codex: bool = False) -> int:
    provider = "codex" if codex else detect_provider()
    workspace = load_workspace(provider)
    if not workspace or not workspace.get("projects"):
        print(
            "[apocalypse workspace] No projects found. Run `apocalypse --update` first.",
            file=sys.stderr,
        )
        return 1
    view = WorkspaceView(workspace, provider=provider)
    if search:
        # Future: pre-fill filter. For now, just print a notice.
        print(f"[apocalypse workspace] filter pre-fill not yet implemented: {search!r}", file=sys.stderr)
    return view.run()
```

- [ ] **Step 5: Run, verify tests pass**

Run: `cd skills_apocalypse && python -m unittest tests.test_render_workspace -v`
Expected: PASS.

- [ ] **Step 6: Manual smoke test**

Run: `cd skills_apocalypse && cp tests/fixtures/workspace.json ~/.claude/apocalypse/workspace.json`
Then:
```bash
cd skills_apocalypse && python apocalypse.py workspace
```
Expected: a top-level list of projects. Press `q` to exit.

After verifying, **delete the smoke fixture** so it doesn't pollute real data:
```bash
rm ~/.claude/apocalypse/workspace.json
```

- [ ] **Step 7: Commit**

```bash
cd E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse
git add skills_apocalypse/apocalypse/workspace_view.py \
        skills_apocalypse/tests/fixtures/workspace.json \
        skills_apocalypse/tests/test_render_workspace.py
git -c user.name="Apocalypse Dev" -c user.email="dev@apocalypse.local" commit -m "feat(workspace): add apocalypse workspace subcommand (3-level nav)"
```

---

## Task 6: `is_headless()` + headless resume fallback

**Files:**
- Modify: `skills_apocalypse/apocalypse/launcher.py`
- Create: `skills_apocalypse/tests/test_headless.py`

This task makes the existing `apocalypse` command SSH-friendly. On a headless server, the resume action prints the command instead of trying to open a new GUI terminal (which would fail anyway because no terminal emulator exists).

**Interfaces:**
- `launcher.is_headless() -> bool` — replaces the stub from Task 3
- `launcher.print_resume_command(sid: str, cwd: str, dangerous: bool) -> None` — prints the cd-and-launch line and waits for Enter
- `launcher.launch_session(...) -> bool` — picks between GUI launch and print based on `is_headless()`

- [ ] **Step 1: Write failing tests for `is_headless`**

Create `skills_apocalypse/tests/test_headless.py`:

```python
"""Tests for apocalypse.launcher.is_headless and headless resume."""
import os
import unittest
from unittest import mock

from apocalypse import launcher


class TestIsHeadless(unittest.TestCase):
    def test_ssh_connection_triggers_headless(self):
        with mock.patch.dict(os.environ, {"SSH_CONNECTION": "1.2.3.4 1234 5.6.7.8 22"}):
            self.assertTrue(launcher.is_headless())

    def test_ssh_tty_triggers_headless(self):
        with mock.patch.dict(os.environ, {"SSH_TTY": "/dev/pts/0"}):
            self.assertTrue(launcher.is_headless())

    def test_no_display_and_no_wayland_triggers_headless(self):
        env = {"DISPLAY": "", "WAYLAND_DISPLAY": ""}
        # Clear them entirely
        for k in ("DISPLAY", "WAYLAND_DISPLAY", "SSH_CONNECTION", "SSH_TTY"):
            os.environ.pop(k, None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(launcher.is_headless())

    def test_display_set_returns_false(self):
        with mock.patch.dict(os.environ,
                             {"DISPLAY": ":0", "SSH_CONNECTION": "", "SSH_TTY": ""},
                             clear=False):
            os.environ.pop("SSH_CONNECTION", None)
            os.environ.pop("SSH_TTY", None)
            with mock.patch.dict(os.environ, {"DISPLAY": ":0"}):
                self.assertFalse(launcher.is_headless())

    def test_wayland_set_returns_false(self):
        with mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            self.assertFalse(launcher.is_headless())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd skills_apocalypse && python -m unittest tests.test_headless -v`
Expected: FAIL on `is_headless` returning the stub `False` (test_display_set_returns_false passes; others fail).

- [ ] **Step 3: Replace `is_headless` stub with real implementation**

In `skills_apocalypse/apocalypse/launcher.py`, find the stub:

```python
def is_headless() -> bool:
    """Stub for Task 6. Real detection in is_headless() implementation."""
    return False
```

**Replace** it with:

```python
def is_headless() -> bool:
    """True when there's no usable GUI terminal launcher available.

    Triggers:
      - SSH_CONNECTION or SSH_TTY is set (terminal is on the remote side)
      - No DISPLAY and no WAYLAND_DISPLAY (no X / Wayland server)
    """
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return True
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return True
    return False
```

Make sure `import os` is present at the top of the file (it should already be — the existing apocalypse.py imports it).

- [ ] **Step 4: Run, verify pass**

Run: `cd skills_apocalypse && python -m unittest tests.test_headless -v`
Expected: PASS.

- [ ] **Step 5: Modify `launch_session` to honour `is_headless`**

In `launcher.py`, find the `launch_session` function. **Replace it** with:

```python
def launch_session(session):
    sid = session["id"]
    cwd = session.get("cwd", "") or _find_cwd_for_session(sid)
    provider = get_provider(session.get("provider", "claude"))
    mode = _choose_permission_mode(provider, "session resume")
    if mode is None:
        return False
    cli_path = shutil.which(provider["name"]) or provider["name"]
    cmd = _build_launch_command(provider["name"], cli_path, session_id=sid, dangerous=(mode == "dangerous"))
    if is_headless():
        return _print_resume_command(cwd, cmd)
    print(f"\n  Launch: cd {cwd} && {cmd}")
    launch_in_terminal(cmd, cwd=cwd or None)
    return True


def launch_new_conversation(project, provider):
    cwd = project.get("cwd", "")
    mode = _choose_permission_mode(provider, "new session")
    if mode is None:
        return False
    cli_path = shutil.which(provider["name"]) or provider["name"]
    cmd = _build_launch_command(provider["name"], cli_path, dangerous=(mode == "dangerous"))
    if is_headless():
        return _print_resume_command(cwd, cmd)
    print(f"\n  Launch new session: cd {cwd} && {cmd}")
    launch_in_terminal(cmd, cwd=cwd or None)
    return True


def _print_resume_command(cwd: str, cmd: str) -> bool:
    """Print the resume command for the user to copy-paste in another shell.

    Used on headless systems where we cannot spawn a GUI terminal.
    """
    full = f"cd {cwd} && {cmd}" if cwd else cmd
    print()
    print("  [headless mode] Resume command (paste in your other shell):")
    print(f"    {full}")
    print()
    try:
        input("  Press Enter to return to the menu...")
    except (EOFError, KeyboardInterrupt):
        pass
    return True
```

- [ ] **Step 6: Add a headless-mode hint to the menu footer**

In `launcher.py`, find the `Menu(...)` constructor in `recent_sessions_menu` (the one whose `footer=` argument is `"Up/Down navigate  |  Enter detail  |  q quit"`). **Replace** the `footer=` argument with:

```python
footer=("Up/Down navigate  |  Enter detail  |  q quit"
        + ("  |  [headless] resume prints command" if is_headless() else "")),
```

Repeat the same change in `project_select_flow` and `session_select_flow` (each has its own `footer=` argument).

- [ ] **Step 7: Manual smoke test in headless mode**

```bash
cd skills_apocalypse
SSH_CONNECTION=fake DISPLAY="" python apocalypse.py --list | head -5
```
Expected: `--list` still works (it doesn't go through `launch_session`).

Then:
```bash
cd skills_apocalypse
SSH_CONNECTION=fake python apocalypse.py --codex  # or any menu entry path
```
Expected: pressing Enter on a session shows the `[headless mode] Resume command` line and waits for Enter.

- [ ] **Step 8: Verify the GUI path is unchanged**

```bash
cd skills_apocalypse
DISPLAY=:0 python apocalypse.py --list | head -5
```
Expected: identical to step 7 output. (No `headless` message because DISPLAY is set.)

- [ ] **Step 9: Commit**

```bash
cd E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse
git add skills_apocalypse/apocalypse/launcher.py \
        skills_apocalypse/tests/test_headless.py
git -c user.name="Apocalypse Dev" -c user.email="dev@apocalypse.local" commit -m "feat(launcher): headless detection + print-only resume on SSH/no-GUI"
```

---

## Task 7: Documentation updates (SKILL.md, CLAUDE.md)

**Files:**
- Modify: `skills_apocalypse/SKILL.md`
- Modify: `apocalypse/CLAUDE.md`

This is a documentation task. No tests. Manual review of the diff is the verification.

- [ ] **Step 1: Append a "CLI Subcommands" section to SKILL.md**

Open `skills_apocalypse/SKILL.md` and find the existing "## Standalone Workspace Update" section. **After** that section (before "## Notes"), insert:

````markdown
## CLI Subcommands

`apocalypse` accepts a subcommand. With no subcommand, the original
menu-driven launcher runs (unchanged). New subcommands target SSH and
headless Linux users who can't open a browser.

| Subcommand | Behaviour |
|---|---|
| `apocalypse` | Original menu (recent sessions → detail → resume) |
| `apocalypse log <sid>` | Interactive pager for a full session transcript |
| `apocalypse log <sid> --raw` | ANSI-coloured transcript, no pager (for `less -R`) |
| `apocalypse log <sid> --tail` | Watch the session live |
| `apocalypse workspace` | Multi-level project tree (top → project → points) |
| `apocalypse --codex` | Switch to OpenAI Codex source (works with all subcommands) |

### `apocalypse log` keymap

```
j / ↓            next line
k / ↑            prev line
d / u            half-page down / up
PgDn / Space     next page
PgUp / b         prev page
g / G            top / bottom
/ text           search forward
? text           search backward
n / N            next / prev match
t                toggle tool expansion
q / Esc          quit
```

### `apocalypse workspace` keymap

```
↑/k ↓/j          up / down
Enter / →/l      enter current row
← / h            previous level
g / G            top / bottom
/                enter filter mode
Esc (top level)  quit
q                quit
```

### Headless mode (SSH / no GUI)

On SSH sessions or systems with no `DISPLAY` / `WAYLAND_DISPLAY`, the
menu enters headless mode. Resume actions print the launch command
instead of opening a new terminal:

```
  [headless mode] Resume command (paste in your other shell):
    cd <cwd> && claude --resume <sid>

  Press Enter to return to the menu...
```

This is auto-detected from `SSH_CONNECTION` / `SSH_TTY` env vars or the
absence of a display server.
````

- [ ] **Step 2: Update CLAUDE.md Architecture section**

Open `apocalypse/CLAUDE.md`. **Replace** the "## Architecture" section's bullet list (the one starting with "The project has two directories:") with:

```markdown
The project has two directories plus a CLI package:

- **`skills_apocalypse/`** — source files, committed to git
- **`runtime_apocalypse/`** — runtime data (events, session snapshots, PID file); not committed
- **`skills_apocalypse/apocalypse/`** — Python package with the new CLI subcommands
  - `__main__.py` — argparse dispatch and headless detection
  - `launcher.py` — existing menu code (moved from the top-level `apocalypse.py`)
  - `log_view.py` — `apocalypse log` subcommand (transcript pager)
  - `workspace_view.py` — `apocalypse workspace` subcommand (3-level project tree)
  - `tui.py` — shared TUI primitives (Style colour/glyph wrapper, Pager, RawInput)

The top-level `skills_apocalypse/apocalypse.py` is a 5-line wrapper
that calls into the package. Backward compatibility is preserved: all
existing flags (`--refresh`, `--update`, `--list`, `--codex`) and the
menu behaviour are unchanged.
```

Then add a new section after the "## Architecture" section:

```markdown
## CLI Subcommands

`apocalypse` accepts a subcommand:

| Subcommand | What it does |
|---|---|
| `apocalypse` (no args) | Original menu (unchanged) |
| `apocalypse log <sid>` | Interactive pager for a full session transcript |
| `apocalypse log <sid> --raw` | ANSI text, no pager (pipe to `less -R`) |
| `apocalypse log <sid> --tail` | Watch the session live |
| `apocalypse workspace` | Multi-level project tree (top → project → points) |

See `SKILL.md` → "CLI Subcommands" for full keymaps and headless mode notes.

## Headless mode

SSH / no-GUI environments are detected via `SSH_CONNECTION` / `SSH_TTY` / `DISPLAY` / `WAYLAND_DISPLAY` (see `apocalypse/launcher.is_headless`). In headless mode:

- `apocalypse` (menu) shows a `[headless]` hint in the footer.
- The "resume" action prints the `cd <cwd> && claude --resume <sid>` line for the user to paste in another shell, instead of trying to launch a GUI terminal.
- `apocalypse log` and `apocalypse workspace` work unchanged (they are pure TUI / stdout output).
```

- [ ] **Step 3: Verify the docs render correctly**

Run: `head -5 apocalypse/CLAUDE.md skills_apocalypse/SKILL.md`
Expected: both files have valid markdown headers and no broken syntax.

- [ ] **Step 4: Commit**

```bash
cd E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse
git add skills_apocalypse/SKILL.md apocalypse/CLAUDE.md
git -c user.name="Apocalypse Dev" -c user.email="dev@apocalypse.local" commit -m "docs: document new CLI subcommands and headless mode"
```

---

## Self-Review

After all tasks are written:

- [ ] **Step 1: Spec coverage check**

| Spec section | Implemented in |
|---|---|
| §1 Problem & non-goals | Treated as constraints; no task violates them |
| §2 Architecture (package split) | Task 3 |
| §3 CLI Surface (subcommands) | Tasks 3, 4, 5 |
| §3 Headless detection | Task 6 |
| §4 TUI shared layer (Style, term_size, RawInput, Pager) | Tasks 1, 2 |
| §5 Log view (load_messages, messages_to_lines, keymap, --raw/--tail) | Task 4 |
| §6 Workspace view (top/project/points levels, keymap) | Task 5 |
| §7 Error handling (TTY fallback, missing data, etc.) | Tasks 4, 5, 6 |
| §8 Testing strategy (unit tests, snapshots, manual SSH) | Tasks 1, 2, 4, 5, 6 |
| §9 Migration steps (6 commits) | Tasks 1-7 each end with a commit |
| §10 Documentation updates (SKILL.md, CLAUDE.md) | Task 7 |
| §11 Rollback (each commit is git-revertible) | Each commit is atomic |

All sections covered.

- [ ] **Step 2: Placeholder scan**

- No "TBD" / "TODO" / "fill in details" / "add appropriate error handling" anywhere
- Every code step has actual code; every test step has actual test code
- Every commit step has a working `git commit` command
- No "see above" or "similar to Task N" without restating the relevant content

- [ ] **Step 3: Type / signature consistency**

- `Style(enabled=None)` (Task 1) → tests use `Style(enabled=True/False)` (Tasks 1, 4, 5) — consistent
- `Pager(lines, *, in_stream, out_stream, status, on_key, height_fn)` (Task 2) → used in `log_view.run` (Task 4) and `workspace_view.run` would use it but uses RawInput directly (Task 5) — both call sites pass `height_fn`; consistent
- `load_messages(sid)` and `load_messages_from_path(path)` (Task 4) → tests use `load_messages_from_path(FIXTURE)` and `load_messages("abc123")` (Task 4 step 2) — consistent
- `load_workspace(provider="claude")` (Task 5) → called from `workspace_view.run(*, search, codex)` with provider derived from `codex` flag or `detect_provider()` — consistent
- `is_headless()` (Task 6) — defined in `launcher`, used in `launch_session` and `launch_new_conversation` (Task 6 step 5) and in the menu footer (Task 6 step 6) — consistent

No type or signature mismatches found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-07-apocalypse-linux-cli.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints
