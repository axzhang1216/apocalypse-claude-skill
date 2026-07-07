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