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