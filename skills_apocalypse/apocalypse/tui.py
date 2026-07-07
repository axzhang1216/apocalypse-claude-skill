"""Shared TUI primitives: ANSI colour, terminal size, raw key input, pager.

Used by launcher, log_view, and workspace_view. No third-party deps.
"""
from __future__ import annotations

import os
import sys
import shutil
from dataclasses import dataclass, field
from typing import Callable, List, Optional, TextIO

# Platform-specific imports
if sys.platform != "win32":
    import termios
    import tty


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
        if sys.platform != "win32" and self._in.isatty():
            self._old = termios.tcgetattr(self._in)
            tty.setcbreak(self._in.fileno())
        return self

    def __exit__(self, exc_type, exc, tb):
        if sys.platform != "win32" and self._old is not None:
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
        if sys.platform != "win32" and self._in.isatty():
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
        if sys.platform != "win32" and self._in.isatty():
            n1 = os.read(self._in.fileno(), 1).decode("utf-8", errors="replace")
        else:
            n1 = self._in.read(1)
            if not n1:
                return "ESC"
        if n1 != "[" and n1 != "O":
            return "ESC"
        if sys.platform != "win32" and self._in.isatty():
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
        if sys.platform != "win32" and self._in.isatty():
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