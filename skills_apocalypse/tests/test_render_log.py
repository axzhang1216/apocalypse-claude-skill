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