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