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