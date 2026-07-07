#!/usr/bin/env python3
"""Apocalypse Launcher - browse recent sessions and resume interactively.

Usage:
    python -m apocalypse              # show recent sessions -> detail -> resume
    python -m apocalypse --refresh    # update workspace first, then launch
    python -m apocalypse --list       # print JSON (non-interactive)
"""

import argparse
import io
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load sibling modules from the same directory as this script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from codex_workspace import (  # noqa: E402
    load_codex_projects,
    load_codex_recent_sessions,
    parse_codex_transcript_preview,
    update_codex_workspace,
)
from platform_utils import launch_in_terminal  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

WORKSPACE = Path.home() / ".claude" / "apocalypse" / "workspace.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

NOISE_PREFIXES = (
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<command-message>",
    "<command-name>",
    "<command-args>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "You are running as a local coding agent for a Multica",
    "You are running as a chat assistant for a Multica",
    "<persisted-output>",
)


def _relative_time(ts):
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hrs = mins // 60
        if hrs < 24:
            return f"{hrs}h ago"
        days = hrs // 24
        if days < 30:
            return f"{days}d ago"
        return f"{days // 30}mo ago"
    except Exception:
        return ""


def _trunc(text, n):
    t = (text or "").strip()
    return t if len(t) <= n else t[: n - 1] + "..."


def _read_tail_records(path, max_bytes=300_000, max_lines=80):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            sz = f.tell()
            f.seek(max(0, sz - max_bytes))
            chunk = f.read()
    except Exception:
        return []
    text = chunk.decode("utf-8", errors="replace")
    if text and text[0] != "\n":
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1 :]
    records = []
    for line in text.split("\n")[-max_lines:]:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return records


def _project_name(cwd):
    if not cwd:
        return "unknown"
    s = str(cwd).replace("\\", "/").rstrip("/")
    return s.rsplit("/", 1)[-1] if s else "unknown"


def _analyze_transcript(path):
    cwd = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("cwd"):
                    cwd = d["cwd"]
                    break
    except Exception:
        return None

    tail = _read_tail_records(path)
    last_ts = None
    for record in reversed(tail):
        if record.get("timestamp"):
            last_ts = record["timestamp"]
            break
    if last_ts is None:
        try:
            mt = path.stat().st_mtime
            last_ts = datetime.fromtimestamp(mt, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            last_ts = ""

    return {
        "session_id": path.stem,
        "cwd": cwd or "",
        "project_name": _project_name(cwd),
        "last_ts": last_ts,
        "mtime": path.stat().st_mtime,
    }


def _scan_recent_sessions(limit=5):
    if not PROJECTS_DIR.exists():
        return []
    results = []
    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        for jsonl in proj_dir.glob("*.jsonl"):
            try:
                meta = _analyze_transcript(jsonl)
                if meta:
                    results.append(meta)
            except Exception:
                continue
    results.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    return results[:limit]


def _load_claude_recent_sessions(limit=5):
    raw_sessions = _scan_recent_sessions(limit=limit)
    lookup = _build_session_lookup()
    enriched = []
    for raw_session in raw_sessions:
        sid = raw_session["session_id"]
        meta = lookup.get(sid, {})
        enriched.append(
            {
                "id": sid,
                "project_title": meta.get("project_title") or raw_session.get("project_name", "Unknown"),
                "project_key": meta.get("project_key", ""),
                "project_name": meta.get("project_name", ""),
                "goal": meta.get("goal", ""),
                "summary": meta.get("summary", ""),
                "category": meta.get("category", "other"),
                "outcome": meta.get("outcome", "partial"),
                "ts": raw_session.get("last_ts", ""),
                "cwd": meta.get("cwd") or raw_session.get("cwd", ""),
            }
        )
    return enriched


def _load_workspace():
    if not WORKSPACE.exists():
        return None
    try:
        return json.loads(WORKSPACE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_session_lookup():
    ws = _load_workspace()
    if not ws:
        return {}
    lookup = {}
    for key, project in ws.get("projects", {}).items():
        title = project.get("title") or project.get("name", "Unknown")
        cwd = project.get("cwd", "")
        for sid, session in project.get("analyzed_sessions", {}).items():
            lookup[sid] = {
                "goal": session.get("user_goal", ""),
                "summary": session.get("summary", ""),
                "category": session.get("category", "other"),
                "outcome": session.get("outcome", "partial"),
                "project_title": title,
                "project_key": key,
                "project_name": project.get("name", ""),
                "cwd": cwd,
            }
    return lookup


def load_all_sessions():
    ws = _load_workspace()
    if not ws:
        return []
    all_sessions = []
    for key, project in ws.get("projects", {}).items():
        title = project.get("title") or project.get("name", "Unknown")
        for sid, session in project.get("analyzed_sessions", {}).items():
            all_sessions.append(
                {
                    "id": sid,
                    "project_key": key,
                    "project_title": title,
                    "project_name": project.get("name", ""),
                    "goal": session.get("user_goal", ""),
                    "summary": session.get("summary", ""),
                    "category": session.get("category", "other"),
                    "ts": session.get("ts", ""),
                    "outcome": session.get("outcome", "partial"),
                    "cwd": project.get("cwd", ""),
                }
            )
    all_sessions.sort(key=lambda item: item["ts"], reverse=True)
    return all_sessions


def load_projects():
    ws = _load_workspace()
    if not ws:
        return []
    projects = []
    for key, project in ws.get("projects", {}).items():
        sessions = project.get("analyzed_sessions", {})
        if not sessions:
            continue
        project_sessions = []
        for sid, session in sessions.items():
            project_sessions.append(
                {
                    "id": sid,
                    "goal": session.get("user_goal", ""),
                    "summary": session.get("summary", ""),
                    "category": session.get("category", "other"),
                    "ts": session.get("ts", ""),
                    "outcome": session.get("outcome", "partial"),
                }
            )
        project_sessions.sort(key=lambda item: item["ts"], reverse=True)
        projects.append(
            {
                "key": key,
                "name": project.get("name", ""),
                "title": project.get("title") or project.get("name", "Unknown"),
                "tags": project.get("tags", []),
                "last_active": project.get("last_active", ""),
                "cwd": project.get("cwd", ""),
                "sessions": project_sessions,
            }
        )
    projects.sort(key=lambda item: item["last_active"], reverse=True)
    return projects


def run_incremental():
    subprocess.run(
        [
            sys.executable,
            str(WORKSPACE.parent.parent / "skills" / "apocalypse" / "workspace_init.py"),
            "--incremental",
        ],
        capture_output=True,
        timeout=300,
    )


def _is_noise(d):
    if d.get("isMeta"):
        return True
    msg = d.get("message") or {}
    content = msg.get("content", [])
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return True
    if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
        return True
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            text = (c.get("text") or "").strip()
            if text and any(text.startswith(prefix) for prefix in NOISE_PREFIXES):
                return True
    return False


def _find_transcript(session_id):
    for jsonl in PROJECTS_DIR.glob(f"*/{session_id}.jsonl"):
        return jsonl
    return None


def parse_transcript_preview(session_id, max_user=3, max_chars=300):
    path = _find_transcript(session_id)
    if not path:
        return [], ""
    user_msgs = []
    last_assistant = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                record_type = d.get("type", "")
                if record_type == "user":
                    if _is_noise(d):
                        continue
                    msg = d.get("message") or {}
                    content = msg.get("content", [])
                    if isinstance(content, str):
                        content = [{"type": "text", "text": content}]
                    if not isinstance(content, list):
                        continue
                    texts = [
                        c.get("text", "").strip()
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text" and (c.get("text") or "").strip()
                    ]
                    if texts and len(user_msgs) < max_user:
                        user_msgs.append("\n".join(texts)[:max_chars])
                elif record_type == "assistant":
                    msg = d.get("message") or {}
                    content = msg.get("content", [])
                    if isinstance(content, str):
                        content = [{"type": "text", "text": content}]
                    if not isinstance(content, list):
                        continue
                    texts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text" and (c.get("text") or "").strip()
                    ]
                    if texts:
                        last_assistant = texts[-1][:max_chars]
    except Exception:
        pass
    return user_msgs, last_assistant


CATEGORY_COLORS = {
    "frontend": CYAN,
    "backend": BLUE,
    "devops": MAGENTA,
    "debugging": RED,
    "refactoring": YELLOW,
    "ai_tools": GREEN,
}


class Menu:
    def __init__(self, title, items, footer=""):
        self.title = title
        self.items = items
        self.footer = footer
        self.sel = 0
        self.page = 0
        self.PAGE = 20

    def render(self):
        sys.stdout.write("\033[2J\033[H")
        lines = [
            f"\n  {BOLD}{CYAN}{self.title}{RESET}",
            f"  {DIM}{len(self.items)} items  |  Up/Down navigate  Enter select  q/Esc quit{RESET}",
            "",
        ]
        total_pages = max(1, (len(self.items) + self.PAGE - 1) // self.PAGE)
        self.page = min(self.page, total_pages - 1)
        start = self.page * self.PAGE
        end = min((self.page + 1) * self.PAGE, len(self.items))
        for idx in range(start, end):
            item = self.items[idx]
            selected = idx == self.sel
            arrow = f"{BOLD}{GREEN}>{RESET}" if selected else " "
            label = f"{BOLD}{item['label']}{RESET}" if selected else item["label"]
            lines.append(f"  {arrow} {item.get('color', '')}{label}{RESET}")
            if item.get("sub"):
                lines.append(f"    {DIM}{item['sub']}{RESET}")
        if total_pages > 1:
            lines.append(f"\n  {DIM}page {self.page + 1}/{total_pages}{RESET}")
        if self.footer:
            lines.append(f"\n  {DIM}{self.footer}{RESET}")
        lines.append("")
        sys.stdout.write("\n".join(lines))
        sys.stdout.flush()

    def run(self):
        if not self.items:
            print(f"\n  {RED}No options available{RESET}")
            return None
        try:
            import tty
            import termios

            old = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        except Exception:
            return self._fallback_run()
        try:
            return self._loop_tty()
        finally:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
            except Exception:
                pass

    def _loop_tty(self):
        while True:
            self.render()
            ch = sys.stdin.read(1)
            if ch in ("q", "\x1b", "\x03"):
                return None
            if ch == "\x1b":
                seq = sys.stdin.read(1)
                if seq == "[":
                    code = sys.stdin.read(1)
                    if code == "A" and self.sel > 0:
                        self.sel -= 1
                        if self.sel < self.page * self.PAGE:
                            self.page -= 1
                    elif code == "B" and self.sel < len(self.items) - 1:
                        self.sel += 1
                        if self.sel >= (self.page + 1) * self.PAGE:
                            self.page += 1
                    elif code == "C":
                        self.page = min(self.page + 1, max(0, (len(self.items) - 1) // self.PAGE))
                        self.sel = min(self.sel, len(self.items) - 1)
                    elif code == "D":
                        self.page = max(self.page - 1, 0)
                        self.sel = max(self.sel, self.page * self.PAGE)
                continue
            if ch == "j" and self.sel < len(self.items) - 1:
                self.sel += 1
                if self.sel >= (self.page + 1) * self.PAGE:
                    self.page += 1
            elif ch == "k" and self.sel > 0:
                self.sel -= 1
                if self.sel < self.page * self.PAGE:
                    self.page -= 1
            elif ch == "g":
                self.sel = 0
                self.page = 0
            elif ch == "G":
                self.sel = len(self.items) - 1
                self.page = max(0, (len(self.items) - 1) // self.PAGE)
            elif ch in ("\n", "\r", " "):
                return self.items[self.sel]
            elif ch == "h":
                self.page = max(self.page - 1, 0)
                self.sel = self.page * self.PAGE
            elif ch == "l":
                self.page = min(self.page + 1, max(0, (len(self.items) - 1) // self.PAGE))
                self.sel = min(self.sel, len(self.items) - 1)

    def _fallback_run(self):
        if sys.platform == "win32":
            try:
                import msvcrt

                return self._win_run(msvcrt)
            except ImportError:
                pass
        while True:
            self.render()
            try:
                choice = input("\n  Enter item number: ").strip()
            except (EOFError, KeyboardInterrupt):
                return None
            if choice.lower() == "q":
                return None
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(self.items):
                    return self.items[idx]
            except ValueError:
                pass

    def _win_run(self, msvcrt):
        while True:
            self.render()
            if not msvcrt.kbhit():
                import time

                time.sleep(0.05)
                continue
            ch = msvcrt.getwch()
            if ch in ("q", "\x1b", "\x03"):
                return None
            if ch in ("\x00", "\xe0"):
                code = msvcrt.getwch()
                if code == "H" and self.sel > 0:
                    self.sel -= 1
                    if self.sel < self.page * self.PAGE:
                        self.page -= 1
                elif code == "P" and self.sel < len(self.items) - 1:
                    self.sel += 1
                    if self.sel >= (self.page + 1) * self.PAGE:
                        self.page += 1
                elif code == "K":
                    self.page = max(self.page - 1, 0)
                    self.sel = self.page * self.PAGE
                elif code == "M":
                    self.page = min(self.page + 1, max(0, (len(self.items) - 1) // self.PAGE))
                    self.sel = min(self.sel, len(self.items) - 1)
                continue
            if ch == "j" and self.sel < len(self.items) - 1:
                self.sel += 1
                if self.sel >= (self.page + 1) * self.PAGE:
                    self.page += 1
            elif ch == "k" and self.sel > 0:
                self.sel -= 1
                if self.sel < self.page * self.PAGE:
                    self.page -= 1
            elif ch == "g":
                self.sel = 0
                self.page = 0
            elif ch == "G":
                self.sel = len(self.items) - 1
                self.page = max(0, (len(self.items) - 1) // self.PAGE)
            elif ch in ("\r", "\n", " "):
                return self.items[self.sel]
            elif ch == "h":
                self.page = max(self.page - 1, 0)
                self.sel = self.page * self.PAGE
            elif ch == "l":
                self.page = min(self.page + 1, max(0, (len(self.items) - 1) // self.PAGE))
                self.sel = min(self.sel, len(self.items) - 1)


def show_detail(session, provider):
    user_msgs, last_asst = provider["preview"](session["id"])
    while True:
        sys.stdout.write("\033[2J\033[H")
        lines = [
            f"\n  {BOLD}{CYAN}Session Detail{RESET}",
            f"  {DIM}{'-' * 60}{RESET}",
            f"  {BOLD}Provider:{RESET}  {provider['agent_label']}",
            f"  {BOLD}Project:{RESET}  {session.get('project_title', '')}",
            f"  {BOLD}Goal:{RESET}  {session.get('goal', '')}",
            f"  {BOLD}Time:{RESET}  {_relative_time(session.get('ts', ''))}  ({session.get('ts', '')[:10]})",
            f"  {BOLD}Outcome:{RESET}  {session.get('outcome', '')}",
            f"  {DIM}{'-' * 60}{RESET}",
        ]
        if user_msgs:
            lines.append(f"\n  {BOLD}User Messages:{RESET}")
            for idx, msg in enumerate(user_msgs):
                label = f"  [{idx + 1}]" if len(user_msgs) > 1 else "  "
                for msg_line in msg.split("\n")[:4]:
                    lines.append(f"  {DIM}{label}{RESET} {_trunc(msg_line, 72)}")
                    label = "   "
        if last_asst:
            lines.append(f"\n  {BOLD}Last Assistant Reply:{RESET}")
            for reply_line in last_asst.split("\n")[:3]:
                lines.append(f"  {_trunc(reply_line, 74)}")
        if not user_msgs and not last_asst:
            lines.append(f"\n  {DIM}(No transcript preview available){RESET}")
        lines += [
            f"\n  {DIM}{'-' * 60}{RESET}",
            f"  {BOLD}{GREEN}Enter{RESET} resume this session   {BOLD}b{RESET} back   {BOLD}q{RESET} quit",
            "",
        ]
        sys.stdout.write("\n".join(lines))
        sys.stdout.flush()
        try:
            import tty
            import termios

            old = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            try:
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        except Exception:
            if sys.platform == "win32":
                try:
                    import msvcrt
                    import time

                    while not msvcrt.kbhit():
                        time.sleep(0.05)
                    ch = msvcrt.getwch()
                    if ch in ("\x00", "\xe0"):
                        msvcrt.getwch()
                        ch = ""
                except Exception:
                    try:
                        ch = input().strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        ch = "q"
            else:
                try:
                    ch = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ch = "q"
        if ch in ("q", "\x03"):
            return None
        if ch == "b":
            return "back"
        if ch in ("\n", "\r", " "):
            return "resume"


def _find_cwd_for_session(session_id):
    ws = _load_workspace()
    if ws:
        for project in ws.get("projects", {}).values():
            if session_id in project.get("analyzed_sessions", {}):
                return project.get("cwd", "")
    path = _find_transcript(session_id)
    if path:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if d.get("cwd"):
                        return d["cwd"]
        except Exception:
            pass
    return ""


def get_provider(mode):
    if mode == "codex":
        return {
            "name": "codex",
            "agent_label": "Codex",
            "load_projects": load_codex_projects,
            "load_recent_sessions": load_codex_recent_sessions,
            "preview": parse_codex_transcript_preview,
            "ensure_workspace": update_codex_workspace,
        }
    return {
        "name": "claude",
        "agent_label": "Claude",
        "load_projects": load_projects,
        "load_recent_sessions": lambda limit=5: _load_claude_recent_sessions(limit),
        "preview": parse_transcript_preview,
        "ensure_workspace": lambda incremental=False: None,
    }


def _choose_permission_mode(provider, action_label):
    items = [
        {
            "label": "Standard permissions",
            "sub": f"Launch {provider['agent_label']} with its normal approval and sandbox flow",
            "value": "standard",
            "color": GREEN,
        },
        {
            "label": "All permissions",
            "sub": f"Launch {provider['agent_label']} in dangerous full-access mode",
            "value": "dangerous",
            "color": RED,
        },
    ]
    menu = Menu(
        f"Apocalypse | {provider['agent_label']} Permissions",
        items,
        footer=f"Choose launch mode for {action_label}  |  q back",
    )
    selected = menu.run()
    if not selected:
        return None
    return selected["value"]


def _build_launch_command(provider_name, cli_path, session_id=None, dangerous=False):
    if provider_name == "codex":
        parts = [f"\"{cli_path}\""]
        if session_id:
            parts.extend(["resume", session_id])
        if dangerous:
            parts.append("--dangerously-bypass-approvals-and-sandbox")
        return " ".join(parts)

    parts = [f"\"{cli_path}\""]
    if session_id:
        parts.extend(["--resume", session_id])
    if dangerous:
        parts.append("--dangerously-skip-permissions")
    return " ".join(parts)


def launch_session(session):
    sid = session["id"]
    cwd = session.get("cwd", "") or _find_cwd_for_session(sid)
    provider = get_provider(session.get("provider", "claude"))
    mode = _choose_permission_mode(provider, "session resume")
    if mode is None:
        return False
    cli_path = shutil.which(provider["name"]) or provider["name"]
    cmd = _build_launch_command(provider["name"], cli_path, session_id=sid, dangerous=(mode == "dangerous"))
    print(f"\n  {DIM}Launch: cd {cwd} && {cmd}{RESET}")
    launch_in_terminal(cmd, cwd=cwd or None)
    return True


def launch_new_conversation(project, provider):
    cwd = project.get("cwd", "")
    mode = _choose_permission_mode(provider, "new session")
    if mode is None:
        return False
    cli_path = shutil.which(provider["name"]) or provider["name"]
    cmd = _build_launch_command(provider["name"], cli_path, dangerous=(mode == "dangerous"))
    print(f"\n  {DIM}Launch new session: cd {cwd} && {cmd}{RESET}")
    launch_in_terminal(cmd, cwd=cwd or None)
    return True


def recent_sessions_menu(provider):
    provider["ensure_workspace"](incremental=True)
    raw_sessions = provider["load_recent_sessions"](limit=5)
    if not raw_sessions:
        print(f"\n  {RED}No {provider['agent_label']} sessions found.{RESET}")
        return

    fallback_item = {
        "label": "Browse all projects...",
        "sub": f"View {provider['agent_label']} sessions grouped by project",
        "color": YELLOW,
        "_fallback": True,
    }

    while True:
        items = []
        for session in raw_sessions:
            rel = _relative_time(session["ts"])
            color = CATEGORY_COLORS.get(session.get("category", ""), "")
            goal = _trunc(session["goal"], 65) if session["goal"] else _trunc(session.get("summary", ""), 65) or "(no summary)"
            sub = f"{session['project_title']}  |  {rel}"
            items.append(
                {
                    "label": goal,
                    "sub": sub,
                    "session": {**session, "provider": provider["name"]},
                    "color": color,
                }
            )
        items.append(fallback_item)

        menu = Menu(
            f"Apocalypse | Recent {provider['agent_label']} Sessions",
            items,
            footer="Up/Down navigate  |  Enter detail  |  q quit",
        )
        selected = menu.run()
        if not selected:
            return

        if selected.get("_fallback"):
            session = project_select_flow(provider)
            if session is None:
                return
            if launch_session(session):
                return
            continue

        action = show_detail(selected["session"], provider)
        if action == "resume":
            if launch_session(selected["session"]):
                return
            continue
        if action is None:
            return


def project_select_flow(provider):
    provider["ensure_workspace"](incremental=True)
    projects = provider["load_projects"]()
    if not projects:
        print(f"\n  {RED}Unable to load {provider['agent_label']} project data.{RESET}")
        return None
    while True:
        items = []
        for project in projects:
            count = len(project["sessions"])
            rel = _relative_time(project["last_active"])
            tags = project.get("tags", [])
            tags_str = ", ".join(tags[:3]) if tags else ""
            sub = f"{count} sessions  |  {rel}"
            if tags_str:
                sub += f"  |  {tags_str}"
            items.append({"label": project["title"], "sub": sub, "project": project, "color": BOLD})
        menu = Menu(
            f"Apocalypse | Choose {provider['agent_label']} Project",
            items,
            footer="Up/Down navigate  |  Enter select  |  q back",
        )
        selected = menu.run()
        if not selected:
            return None
        session = session_select_flow(provider, selected["project"])
        if session is None:
            continue
        return session


def session_select_flow(provider, project):
    while True:
        items = []
        cwd = project.get("cwd", "") or "(not set)"
        cmd_preview = "codex" if provider["name"] == "codex" else "claude"
        items.append(
            {
                "label": f"Start a new {provider['agent_label']} session here",
                "sub": f"cd {cwd} && {cmd_preview}",
                "_new_conversation": True,
                "color": GREEN,
            }
        )
        for session in project["sessions"]:
            rel = _relative_time(session["ts"])
            color = CATEGORY_COLORS.get(session.get("category", ""), "")
            goal = _trunc(session["goal"], 65) if session["goal"] else "(no goal)"
            outcome_icon = {"completed": "[done]", "partial": "[part]", "abandoned": "[drop]"}.get(
                session.get("outcome", ""),
                "",
            )
            sub = f"{rel}  |  {outcome_icon} {_trunc(session.get('summary', ''), 45)}"
            items.append(
                {
                    "label": goal,
                    "sub": sub,
                    "session": {
                        **session,
                        "project_title": project["title"],
                        "project_key": project["key"],
                        "project_name": project["name"],
                        "cwd": project.get("cwd", ""),
                        "provider": provider["name"],
                    },
                    "color": color,
                }
            )
        menu = Menu(
            f"Apocalypse | {provider['agent_label']} / {project['title']}",
            items,
            footer="Up/Down navigate  |  Enter detail  |  q back",
        )
        selected = menu.run()
        if not selected:
            return None
        if selected.get("_new_conversation"):
            if launch_new_conversation(project, provider):
                return None
            continue
        action = show_detail(selected["session"], provider)
        if action == "resume":
            return selected["session"]
        if action is None:
            return None


CATEGORY_LABELS = {
    "frontend": "前端开发",
    "backend": "后端开发",
    "devops": "部署运维",
    "debugging": "调试修复",
    "refactoring": "重构优化",
    "data": "数据处理",
    "docs": "文档写作",
    "config": "配置环境",
    "exploration": "探索研究",
    "ai_tools": "AI工具开发",
    "other": "其他",
}


def _run_incremental_and_collect():
    init_script = str(WORKSPACE.parent.parent / "skills" / "apocalypse" / "workspace_init.py")
    result = subprocess.run(
        [sys.executable, init_script, "--incremental"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    events = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return events


def _dump_summaries():
    init_script = str(WORKSPACE.parent.parent / "skills" / "apocalypse" / "workspace_init.py")
    result = subprocess.run(
        [sys.executable, init_script, "--dump-summaries"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        return json.loads(result.stdout)
    except Exception:
        return {}


def _set_themes(themes_map):
    init_script = str(WORKSPACE.parent.parent / "skills" / "apocalypse" / "workspace_init.py")
    payload = json.dumps({"projects": themes_map}, ensure_ascii=False)
    subprocess.run(
        [sys.executable, init_script, "--set-themes"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _auto_theme_from_categories(analyzed_sessions):
    cat_counts = {}
    sample_goals = []
    for session in analyzed_sessions.values():
        cat = session.get("category", "other")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if len(sample_goals) < 3 and session.get("user_goal"):
            sample_goals.append(session["user_goal"])
    if not cat_counts:
        return {"title": "", "tags": []}
    top_cats = sorted(cat_counts.items(), key=lambda item: item[1], reverse=True)
    main_cat = top_cats[0][0]
    title = CATEGORY_LABELS.get(main_cat, main_cat)
    tags = [CATEGORY_LABELS.get(cat, cat) for cat, _ in top_cats[:3]]
    if sample_goals:
        hint = _trunc(sample_goals[0], 30)
        if hint:
            title = hint
    return {"title": title, "tags": tags}


def update_workspace():
    print(f"\n  {BOLD}{CYAN}Apocalypse Workspace 更新{RESET}\n")
    print(f"  {DIM}扫描新 session 并分析中...{RESET}")
    events = _run_incremental_and_collect()

    done_evt = None
    project_evts = []
    for event in events:
        if event.get("type") == "project_done":
            project_evts.append(event)
        elif event.get("type") == "done":
            done_evt = event
        elif event.get("type") == "error":
            print(f"  {RED}错误: {event.get('message', '')}{RESET}")
            return

    total_new = done_evt.get("total_sessions", 0) if done_evt else 0
    if total_new == 0:
        print(f"  {DIM}没有新的 session 需要分析。{RESET}")
        return

    ws = _load_workspace()
    print(f"\n  {GREEN}分析完成：{total_new} 个新 session，{len(project_evts)} 个项目有更新{RESET}\n")

    for event in project_evts:
        proj_name = event.get("project", "")
        new_count = event.get("sessions", 0)
        proj_record = None
        proj_title = proj_name
        for project in (ws or {}).get("projects", {}).values():
            if project.get("name") == proj_name:
                proj_record = project
                proj_title = project.get("title") or proj_name
                break

        print(f"  {BOLD}{proj_title}{RESET}  {DIM}({proj_name}){RESET}")
        print(f"    新增 {GREEN}{new_count}{RESET} 个 session")

        if proj_record:
            analyzed = proj_record.get("analyzed_sessions", {})
            sorted_sids = sorted(analyzed.keys(), key=lambda sid: analyzed[sid].get("ts", ""), reverse=True)
            shown = 0
            for sid in sorted_sids:
                if shown >= new_count:
                    break
                session = analyzed[sid]
                goal = _trunc(session.get("user_goal", ""), 65) or "(无信息)"
                summary = _trunc(session.get("summary", ""), 55)
                cat = session.get("category", "other")
                cat_label = CATEGORY_LABELS.get(cat, cat)
                print(f"    {DIM}•{RESET} {goal}")
                print(f"      {DIM}{summary}  [{cat_label}]{RESET}")
                shown += 1

        title = proj_record.get("title", "") if proj_record else ""
        tags = proj_record.get("tags", []) if proj_record else []
        if title:
            print(f"    {DIM}当前主题:{RESET} {title}  {DIM}标签:{RESET} {', '.join(tags) if tags else '(无)'}")
        else:
            print(f"    {YELLOW}⚠ 无标题和标签，需要设定{RESET}")
        print()

    summaries = _dump_summaries()
    projects_list = summaries.get("projects", [])
    needs_theme = [project for project in projects_list if not project.get("title")]

    if needs_theme:
        print(f"  {BOLD}{YELLOW}以下 {len(needs_theme)} 个项目需要设定标题和标签：{RESET}\n")
        themes_to_set = {}
        for project in needs_theme:
            key = project["key"]
            analyzed = {}
            if ws and key in ws.get("projects", {}):
                analyzed = ws["projects"][key].get("analyzed_sessions", {})
            auto = _auto_theme_from_categories(analyzed)
            goals = project.get("sample_goals", [])[:2]
            cat_bd = project.get("category_breakdown", {})
            top_cat = max(cat_bd.items(), key=lambda item: item[1])[0] if cat_bd else "other"

            print(f"  {BOLD}{project['folder_name']}{RESET}")
            print(f"    {DIM}Sessions:{RESET} {project['session_count']}  |  {DIM}主分类:{RESET} {CATEGORY_LABELS.get(top_cat, top_cat)}")
            if goals:
                for goal in goals:
                    print(f"    {DIM}•{RESET} {_trunc(goal, 60)}")
            print(f"    {GREEN}建议标题:{RESET} {auto['title']}")
            print(f"    {GREEN}建议标签:{RESET} {', '.join(auto['tags'])}")
            print()
            themes_to_set[key] = auto

        print(f"  {DIM}{'-' * 50}{RESET}")
        try:
            choice = input(f"  {BOLD}确认以上标题和标签？(Y/n/edit): {RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "n"

        if choice == "n":
            print(f"  {DIM}已跳过主题设定。{RESET}")
        elif choice == "edit":
            print(f"  {DIM}请手动编辑 workspace.json 中的 title 和 tags 字段。{RESET}")
        else:
            _set_themes(themes_to_set)
            print(f"\n  {GREEN}已更新 {len(themes_to_set)} 个项目的标题和标签。{RESET}")
    else:
        print(f"  {DIM}所有项目已有标题和标签。{RESET}")

    print(f"\n  {DIM}提取讨论-决策节点...{RESET}")
    init_script = str(WORKSPACE.parent.parent / "skills" / "apocalypse" / "workspace_init.py")
    result = subprocess.run(
        [sys.executable, init_script, "--extract-points"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    points_total = 0
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
            if evt.get("type") == "done":
                points_total = evt.get("total_points", 0)
        except Exception:
            pass
    if points_total > 0:
        print(f"  {GREEN}提取了 {points_total} 个讨论-决策节点。{RESET}")
    else:
        print(f"  {DIM}没有新的讨论-决策节点需要提取。{RESET}")

    print(f"\n  {DIM}打开 http://localhost:7749/workspace.html 查看更新后的星图。{RESET}\n")

    try:
        from workspace_init import export_history

        result = export_history()
        if result.get("sessions_exported"):
            print(f"  {GREEN}已归档 {result['sessions_exported']} 个 session 到 {result['projects_processed']} 个项目的 .apocalypse/{RESET}")
        elif result.get("projects_processed"):
            print(f"  {DIM}已扫描 {result['projects_processed']} 个项目（无新增 session 需要归档）{RESET}")
    except Exception as exc:
        print(f"  {YELLOW}历史归档失败（不影响其他功能）: {exc}{RESET}")


def run(args=None):
    if args is None:
        import argparse
        parser = _build_argparser()
        args = parser.parse_args()

    provider = get_provider("codex" if args.codex else "claude")

    if args.list:
        provider["ensure_workspace"](incremental=True)
        projects = provider["load_projects"]()
        out = [
            {
                "title": project["title"],
                "name": project["name"],
                "tags": project["tags"],
                "session_count": len(project["sessions"]),
                "last_active": project["last_active"],
                "sessions": [{"id": session["id"], "goal": session["goal"], "ts": session["ts"]} for session in project["sessions"]],
            }
            for project in projects
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if args.update:
        update_workspace()
        return

    if args.refresh:
        print(f"  {DIM}Refreshing workspace...{RESET}")
        run_incremental()

    recent_sessions_menu(provider)


def _build_argparser():
    parser = argparse.ArgumentParser(description="Apocalypse Launcher")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update workspace: analyze new sessions, assign themes, show summary",
    )
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--codex",
        action="store_true",
        help="Launch the Codex CLI history browser instead of Claude",
    )
    return parser


def _dispatch(args):
    if args.subcommand == "log":
        from apocalypse import log_view
        log_view.main(args)
    elif args.subcommand == "workspace":
        from apocalypse import workspace_view
        workspace_view.main(args)
    else:
        print(f"Unknown subcommand: {args.subcommand}", file=sys.stderr)
        sys.exit(1)


def is_headless():
    """Stub implementation - real implementation in Task 6"""
    return False