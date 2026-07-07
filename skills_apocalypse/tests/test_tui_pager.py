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