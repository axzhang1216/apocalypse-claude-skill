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

    def run(self, search: Optional[str] = None) -> int:
        from apocalypse.tui import RawInput
        if search:
            # Future: pre-fill filter. For now, just print a notice.
            print(f"[apocalypse workspace] filter pre-fill not yet implemented: {search!r}", file=sys.stderr)
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
    return view.run(search=search)

