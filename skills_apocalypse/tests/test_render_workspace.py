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