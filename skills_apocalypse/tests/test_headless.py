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
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(launcher, "get_platform", return_value="linux"):
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

    def test_windows_not_headless_without_gui_vars(self):
        # Windows never sets DISPLAY/WAYLAND_DISPLAY (those are X11/Wayland
        # Linux-only). It must still be treated as having a GUI via wt.exe /
        # cmd /k — see platform_utils._launch_windows.
        for k in ("SSH_CONNECTION", "SSH_TTY", "DISPLAY", "WAYLAND_DISPLAY"):
            os.environ.pop(k, None)
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(launcher, "get_platform", return_value="windows"):
            self.assertFalse(launcher.is_headless())

    def test_macos_not_headless_without_gui_vars(self):
        # macOS has Terminal.app — never headless just because DISPLAY is unset.
        for k in ("SSH_CONNECTION", "SSH_TTY", "DISPLAY", "WAYLAND_DISPLAY"):
            os.environ.pop(k, None)
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(launcher, "get_platform", return_value="macos"):
            self.assertFalse(launcher.is_headless())

    def test_windows_with_ssh_still_headless(self):
        for k in ("DISPLAY", "WAYLAND_DISPLAY"):
            os.environ.pop(k, None)
        with mock.patch.dict(os.environ, {"SSH_CONNECTION": "1.2.3.4 1234 5.6.7.8 22"}, clear=False), \
             mock.patch.object(launcher, "get_platform", return_value="windows"):
            self.assertTrue(launcher.is_headless())

    def test_linux_no_display_still_headless(self):
        # Linux without any GUI vars and no SSH is still headless.
        for k in ("SSH_CONNECTION", "SSH_TTY", "DISPLAY", "WAYLAND_DISPLAY"):
            os.environ.pop(k, None)
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(launcher, "get_platform", return_value="linux"):
            self.assertTrue(launcher.is_headless())


if __name__ == "__main__":
    unittest.main()