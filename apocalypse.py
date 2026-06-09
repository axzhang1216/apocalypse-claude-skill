#!/usr/bin/env python3
"""Apocalypse Launcher — browse recent sessions and resume interactively.

Usage:
    python apocalypse.py              # show recent sessions → detail → resume
    python apocalypse.py --refresh    # update workspace first, then launch
    python apocalypse.py --list       # print JSON (non-interactive)
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
if sys.platform == "win32":
    os.system("")

WORKSPACE = Path.home() / ".claude" / "apocalypse" / "workspace.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"

RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
BLUE = "\033[34m"; MAGENTA = "\033[35m"; CYAN = "\033[36m"
DIM = "\033[2m"; BOLD = "\033[1m"; RESET = "\033[0m"

NOISE_PREFIXES = (
    "<local-command-caveat>", "<local-command-stdout>",
    "<command-message>", "<command-name>", "<command-args>",
    "<bash-input>", "<bash-stdout>", "<bash-stderr>",
    "You are running as a local coding agent for a Multica",
    "You are running as a chat assistant for a Multica",
    "<persisted-output>",
)


def _relative_time(ts):
    if not ts: return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
        if mins < 1:   return "刚刚"
        if mins < 60:  return f"{mins}分钟前"
        hrs = mins // 60
        if hrs < 24:   return f"{hrs}小时前"
        days = hrs // 24
        if days < 30:  return f"{days}天前"
        return f"{days // 30}月前"
    except Exception:
        return ""


def _trunc(text, n):
    t = (text or "").strip()
    return t if len(t) <= n else t[:n-1] + "…"


# ── Real-time transcript scanning (same approach as server.py) ─────────────────
def _read_tail_records(path, max_bytes=300_000, max_lines=80):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); sz = f.tell()
            f.seek(max(0, sz - max_bytes)); chunk = f.read()
    except Exception:
        return []
    text = chunk.decode("utf-8", errors="replace")
    if text and text[0] != "\n":
        nl = text.find("\n")
        if nl >= 0: text = text[nl + 1:]
    records = []
    for line in text.split("\n")[-max_lines:]:
        line = line.strip()
        if not line: continue
        try: records.append(json.loads(line))
        except Exception: continue
    return records


def _ts_to_dt(ts):
    if not ts: return None
    try: return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception: return None


def _project_name(cwd):
    if not cwd: return "unknown"
    s = str(cwd).replace("\\", "/").rstrip("/")
    return s.rsplit("/", 1)[-1] if s else "unknown"


def _analyze_transcript(path):
    """Read a transcript file and extract cwd + last timestamp."""
    cwd = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try: d = json.loads(line)
                except Exception: continue
                if d.get("cwd"):
                    cwd = d["cwd"]; break
    except Exception:
        return None

    tail = _read_tail_records(path)
    last_ts = None
    for r in reversed(tail):
        if r.get("timestamp"):
            last_ts = r["timestamp"]; break
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
    """Scan filesystem for the most recent transcript files. Real-time, no workspace.json dependency."""
    if not PROJECTS_DIR.exists(): return []
    results = []
    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir(): continue
        for jsonl in proj_dir.glob("*.jsonl"):
            try:
                meta = _analyze_transcript(jsonl)
                if meta: results.append(meta)
            except Exception: continue
    results.sort(key=lambda r: r.get("mtime", 0), reverse=True)
    return results[:limit]


def _load_workspace():
    if not WORKSPACE.exists(): return None
    try: return json.loads(WORKSPACE.read_text(encoding="utf-8"))
    except Exception: return None


def _build_session_lookup():
    """Build {session_id: {goal, summary, project_title, project_key, cwd, ...}} from workspace.json."""
    ws = _load_workspace()
    if not ws: return {}
    lookup = {}
    for key, p in ws.get("projects", {}).items():
        title = p.get("title") or p.get("name", "Unknown")
        cwd = p.get("cwd", "")
        for sid, s in p.get("analyzed_sessions", {}).items():
            lookup[sid] = {
                "goal": s.get("user_goal", ""),
                "summary": s.get("summary", ""),
                "category": s.get("category", "other"),
                "outcome": s.get("outcome", "partial"),
                "project_title": title,
                "project_key": key,
                "project_name": p.get("name", ""),
                "cwd": cwd,
            }
    return lookup


def load_all_sessions():
    ws = _load_workspace()
    if not ws: return []
    all_sessions = []
    for key, p in ws.get("projects", {}).items():
        title = p.get("title") or p.get("name", "Unknown")
        for sid, s in p.get("analyzed_sessions", {}).items():
            all_sessions.append({
                "id": sid, "project_key": key, "project_title": title,
                "project_name": p.get("name", ""),
                "goal": s.get("user_goal", ""), "summary": s.get("summary", ""),
                "category": s.get("category", "other"), "ts": s.get("ts", ""),
                "outcome": s.get("outcome", "partial"),
                "cwd": p.get("cwd", ""),
            })
    all_sessions.sort(key=lambda x: x["ts"], reverse=True)
    return all_sessions


def load_projects():
    ws = _load_workspace()
    if not ws: return []
    projects = []
    for key, p in ws.get("projects", {}).items():
        sessions = p.get("analyzed_sessions", {})
        if not sessions: continue
        ps = []
        for sid, s in sessions.items():
            ps.append({
                "id": sid, "goal": s.get("user_goal", ""),
                "summary": s.get("summary", ""), "category": s.get("category", "other"),
                "ts": s.get("ts", ""), "outcome": s.get("outcome", "partial"),
            })
        ps.sort(key=lambda x: x["ts"], reverse=True)
        projects.append({
            "key": key, "name": p.get("name", ""),
            "title": p.get("title") or p.get("name", "Unknown"),
            "tags": p.get("tags", []), "last_active": p.get("last_active", ""),
            "cwd": p.get("cwd", ""), "sessions": ps,
        })
    projects.sort(key=lambda x: x["last_active"], reverse=True)
    return projects


def run_incremental():
    subprocess.run([sys.executable, str(WORKSPACE.parent.parent / "skills" / "apocalypse" / "workspace_init.py"), "--incremental"],
                   capture_output=True, timeout=300)


# ── Transcript parsing for detail view ────────────────────────────────────────
def _is_noise(d):
    if d.get("isMeta"): return True
    msg = d.get("message") or {}
    content = msg.get("content", [])
    if isinstance(content, str): content = [{"type": "text", "text": content}]
    if not isinstance(content, list): return True
    if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content): return True
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            t = (c.get("text") or "").strip()
            if t and any(t.startswith(p) for p in NOISE_PREFIXES): return True
    return False


def _find_transcript(session_id):
    for jf in PROJECTS_DIR.glob(f"*/{session_id}.jsonl"):
        return jf
    return None


def parse_transcript_preview(session_id, max_user=3, max_chars=300):
    path = _find_transcript(session_id)
    if not path: return [], ""
    user_msgs, last_assistant = [], ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw: continue
                try: d = json.loads(raw)
                except Exception: continue
                t = d.get("type", "")
                if t == "user":
                    if _is_noise(d): continue
                    msg = d.get("message") or {}
                    content = msg.get("content", [])
                    if isinstance(content, str): content = [{"type": "text", "text": content}]
                    if not isinstance(content, list): continue
                    texts = [c.get("text", "").strip() for c in content
                             if isinstance(c, dict) and c.get("type") == "text" and (c.get("text") or "").strip()]
                    if texts:
                        if len(user_msgs) < max_user:
                            user_msgs.append("\n".join(texts)[:max_chars])
                elif t == "assistant":
                    msg = d.get("message") or {}
                    content = msg.get("content", [])
                    if isinstance(content, str): content = [{"type": "text", "text": content}]
                    if not isinstance(content, list): continue
                    texts = [c.get("text", "") for c in content
                             if isinstance(c, dict) and c.get("type") == "text" and (c.get("text") or "").strip()]
                    if texts: last_assistant = texts[-1][:max_chars]
    except Exception:
        pass
    return user_msgs, last_assistant


# ── Menu ──────────────────────────────────────────────────────────────────────
CATEGORY_COLORS = {
    "frontend": CYAN, "backend": BLUE, "devops": MAGENTA,
    "debugging": RED, "refactoring": YELLOW, "ai_tools": GREEN,
}


class Menu:
    def __init__(self, title, items, footer=""):
        self.title = title; self.items = items; self.footer = footer
        self.sel = 0; self.page = 0; self.PAGE = 20

    def render(self):
        sys.stdout.write("\033[2J\033[H")
        lines = [f"\n  {BOLD}{CYAN}{self.title}{RESET}",
                 f"  {DIM}{len(self.items)} 个选项  |  ↑↓ 导航  Enter 选择  q/Esc 退出{RESET}", ""]
        tp = max(1, (len(self.items) + self.PAGE - 1) // self.PAGE)
        self.page = min(self.page, tp - 1)
        s, e = self.page * self.PAGE, min((self.page + 1) * self.PAGE, len(self.items))
        for i in range(s, e):
            item = self.items[i]; sel = i == self.sel
            arrow = f"{BOLD}{GREEN}▶{RESET}" if sel else " "
            label = f"{BOLD}{item['label']}{RESET}" if sel else item["label"]
            lines.append(f"  {arrow} {item.get('color','')}{label}{RESET}")
            if item.get("sub"): lines.append(f"    {DIM}{item['sub']}{RESET}")
        if tp > 1: lines.append(f"\n  {DIM}页 {self.page+1}/{tp}{RESET}")
        if self.footer: lines.append(f"\n  {DIM}{self.footer}{RESET}")
        lines.append("")
        sys.stdout.write("\n".join(lines)); sys.stdout.flush()

    def run(self):
        if not self.items:
            print(f"\n  {RED}没有可用选项{RESET}"); return None
        try:
            import tty, termios
            old = termios.tcgetattr(sys.stdin); tty.setcbreak(sys.stdin.fileno())
        except Exception:
            return self._fallback_run()
        try:
            return self._loop_tty()
        finally:
            try: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
            except Exception: pass

    def _loop_tty(self):
        while True:
            self.render(); ch = sys.stdin.read(1)
            if ch in ("q", "\x1b", "\x03"): return None
            if ch == "\x1b":
                seq = sys.stdin.read(1)
                if seq == "[":
                    code = sys.stdin.read(1)
                    if code == "A" and self.sel > 0:
                        self.sel -= 1
                        if self.sel < self.page * self.PAGE: self.page -= 1
                    elif code == "B" and self.sel < len(self.items) - 1:
                        self.sel += 1
                        if self.sel >= (self.page + 1) * self.PAGE: self.page += 1
                    elif code == "C":
                        self.page = min(self.page + 1, max(0, (len(self.items)-1) // self.PAGE))
                        self.sel = min(self.sel, len(self.items) - 1)
                    elif code == "D":
                        self.page = max(self.page - 1, 0)
                        self.sel = max(self.sel, self.page * self.PAGE)
                continue
            if ch == "j" and self.sel < len(self.items)-1:
                self.sel += 1
                if self.sel >= (self.page+1)*self.PAGE: self.page += 1
            elif ch == "k" and self.sel > 0:
                self.sel -= 1
                if self.sel < self.page*self.PAGE: self.page -= 1
            elif ch == "g": self.sel = 0; self.page = 0
            elif ch == "G": self.sel = len(self.items)-1; self.page = max(0, (len(self.items)-1)//self.PAGE)
            elif ch in ("\n", "\r", " "): return self.items[self.sel]
            elif ch == "h": self.page = max(self.page-1, 0); self.sel = self.page*self.PAGE
            elif ch == "l": self.page = min(self.page+1, max(0,(len(self.items)-1)//self.PAGE)); self.sel = min(self.sel, len(self.items)-1)

    def _fallback_run(self):
        if sys.platform == "win32":
            try:
                import msvcrt; return self._win_run(msvcrt)
            except ImportError: pass
        while True:
            self.render()
            try: choice = input("\n  输入序号: ").strip()
            except (EOFError, KeyboardInterrupt): return None
            if choice.lower() == "q": return None
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(self.items): return self.items[idx]
            except ValueError: pass

    def _win_run(self, msvcrt):
        while True:
            self.render()
            if not msvcrt.kbhit():
                import time; time.sleep(0.05); continue
            ch = msvcrt.getwch()
            if ch in ("q", "\x1b", "\x03"): return None
            if ch in ("\x00", "\xe0"):
                code = msvcrt.getwch()
                if code == "H" and self.sel > 0:
                    self.sel -= 1
                    if self.sel < self.page*self.PAGE: self.page -= 1
                elif code == "P" and self.sel < len(self.items)-1:
                    self.sel += 1
                    if self.sel >= (self.page+1)*self.PAGE: self.page += 1
                elif code == "K": self.page = max(self.page-1,0); self.sel = self.page*self.PAGE
                elif code == "M": self.page = min(self.page+1,max(0,(len(self.items)-1)//self.PAGE)); self.sel = min(self.sel,len(self.items)-1)
                continue
            if ch == "j" and self.sel < len(self.items)-1:
                self.sel += 1
                if self.sel >= (self.page+1)*self.PAGE: self.page += 1
            elif ch == "k" and self.sel > 0:
                self.sel -= 1
                if self.sel < self.page*self.PAGE: self.page -= 1
            elif ch == "g": self.sel = 0; self.page = 0
            elif ch == "G": self.sel = len(self.items)-1; self.page = max(0,(len(self.items)-1)//self.PAGE)
            elif ch in ("\r", "\n", " "): return self.items[self.sel]
            elif ch == "h": self.page = max(self.page-1,0); self.sel = self.page*self.PAGE
            elif ch == "l": self.page = min(self.page+1,max(0,(len(self.items)-1)//self.PAGE)); self.sel = min(self.sel,len(self.items)-1)


# ── Detail view ───────────────────────────────────────────────────────────────
def show_detail(session):
    """Show session transcript preview. Returns 'resume', 'back', or None."""
    user_msgs, last_asst = parse_transcript_preview(session["id"])
    while True:
        sys.stdout.write("\033[2J\033[H")
        lines = [
            f"\n  {BOLD}{CYAN}会话详情{RESET}",
            f"  {DIM}{'─' * 60}{RESET}",
            f"  {BOLD}项目:{RESET}  {session.get('project_title', '')}",
            f"  {BOLD}目标:{RESET}  {session.get('goal', '')}",
            f"  {BOLD}时间:{RESET}  {_relative_time(session.get('ts', ''))}  ({session.get('ts', '')[:10]})",
            f"  {BOLD}结果:{RESET}  {session.get('outcome', '')}",
            f"  {DIM}{'─' * 60}{RESET}",
        ]
        if user_msgs:
            lines.append(f"\n  {BOLD}用户消息:{RESET}")
            for i, m in enumerate(user_msgs):
                lbl = f"  [{i+1}]" if len(user_msgs) > 1 else "  "
                for ml in m.split("\n")[:4]:
                    lines.append(f"  {DIM}{lbl}{RESET} {_trunc(ml, 72)}"); lbl = "   "
        if last_asst:
            lines.append(f"\n  {BOLD}助手最后回复:{RESET}")
            for al in last_asst.split("\n")[:3]:
                lines.append(f"  {_trunc(al, 74)}")
        if not user_msgs and not last_asst:
            lines.append(f"\n  {DIM}(无法读取对话记录){RESET}")
        lines += [
            f"\n  {DIM}{'─' * 60}{RESET}",
            f"  {BOLD}{GREEN}Enter{RESET} 恢复此会话   {BOLD}b{RESET} 返回列表   {BOLD}q{RESET} 退出", "",
        ]
        sys.stdout.write("\n".join(lines)); sys.stdout.flush()
        # Read key
        try:
            import tty, termios
            old = termios.tcgetattr(sys.stdin); tty.setcbreak(sys.stdin.fileno())
            try: ch = sys.stdin.read(1)
            finally: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        except Exception:
            if sys.platform == "win32":
                try:
                    import msvcrt, time
                    while not msvcrt.kbhit(): time.sleep(0.05)
                    ch = msvcrt.getwch()
                    if ch in ("\x00", "\xe0"): msvcrt.getwch(); ch = ""
                except Exception:
                    try: ch = input().strip().lower()
                    except (EOFError, KeyboardInterrupt): ch = "q"
            else:
                try: ch = input().strip().lower()
                except (EOFError, KeyboardInterrupt): ch = "q"
        if ch in ("q", "\x03"): return None
        if ch == "b": return "back"
        if ch in ("\n", "\r", " "): return "resume"


# ── Launch ────────────────────────────────────────────────────────────────────
def _find_cwd_for_session(session_id):
    """Find the working directory for a session from workspace.json."""
    ws = _load_workspace()
    if not ws: return ""
    for key, p in ws.get("projects", {}).items():
        if session_id in p.get("analyzed_sessions", {}):
            return p.get("cwd", "")
    # Fallback: read cwd from the transcript file itself
    path = _find_transcript(session_id)
    if path:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try: d = json.loads(line)
                    except Exception: continue
                    if d.get("cwd"): return d["cwd"]
        except Exception: pass
    return ""


def launch_session(session):
    """Open ccr code --resume in a new Windows Terminal tab (or new window)."""
    import tempfile
    sid = session["id"]
    cwd = session.get("cwd", "") or _find_cwd_for_session(sid)
    ccr_path = shutil.which("ccr") or "ccr"
    print(f"\n  {DIM}启动: cd {cwd} && ccr code --resume {sid}{RESET}")

    if sys.platform == "win32":
        # Write a temp .bat to avoid quoting issues
        bat = tempfile.NamedTemporaryFile(mode="w", suffix=".bat", delete=False, encoding="utf-8", dir=str(Path.home()))
        bat.write(f"@echo off\n")
        if cwd:
            bat.write(f'cd /d "{cwd}"\n')
        bat.write(f'"{ccr_path}" code --resume {sid}\n')
        bat.close()

        wt = shutil.which("wt")
        if wt:
            subprocess.Popen([wt, "-w", "0", "nt", "--title", "Claude Code",
                              "-d", cwd or ".", "cmd", "/k", bat.name])
        else:
            os.system(f'start "Claude Code" cmd /k "{bat.name}"')
    else:
        cd_cmd = f'cd "{cwd}" && ' if cwd else ''
        subprocess.Popen(["bash", "-c", f'{cd_cmd}{ccr_path} code --resume {sid} &'],
                         start_new_session=True)


# ── Main flow ─────────────────────────────────────────────────────────────────
def recent_sessions_menu():
    """Show 5 most recent sessions (real-time from filesystem) + browse projects fallback."""
    raw_sessions = _scan_recent_sessions(limit=5)
    if not raw_sessions:
        print(f"\n  {RED}没有已分析的 session。先运行 /apocalypse 初始化 workspace。{RESET}")
        return

    # Enrich with workspace.json metadata (goal, project_title, etc.)
    lookup = _build_session_lookup()
    enriched = []
    for rs in raw_sessions:
        sid = rs["session_id"]
        meta = lookup.get(sid, {})
        enriched.append({
            "id": sid,
            "project_title": meta.get("project_title") or rs.get("project_name", "Unknown"),
            "project_key": meta.get("project_key", ""),
            "project_name": meta.get("project_name", ""),
            "goal": meta.get("goal", ""),
            "summary": meta.get("summary", ""),
            "category": meta.get("category", "other"),
            "outcome": meta.get("outcome", "partial"),
            "ts": rs.get("last_ts", ""),
            "cwd": meta.get("cwd") or rs.get("cwd", ""),
        })

    fallback_item = {"label": "浏览所有项目...", "sub": "按项目分类查找", "color": YELLOW, "_fallback": True}

    while True:
        items = []
        for s in enriched:
            rel = _relative_time(s["ts"])
            color = CATEGORY_COLORS.get(s.get("category", ""), "")
            goal = _trunc(s["goal"], 65) if s["goal"] else s.get("summary", "")[:65] or "(无信息)"
            sub = f"{s['project_title']}  ·  {rel}"
            items.append({"label": goal, "sub": sub, "session": s, "color": color})
        items.append(fallback_item)

        m = Menu("月球系统 · 最近会话", items,
                 footer="↑↓ 导航  |  Enter 查看详情  |  q 退出")
        sel = m.run()
        if not sel: return

        if sel.get("_fallback"):
            session = project_select_flow()
            if session is None: return
            launch_session(session); return

        session = sel["session"]
        action = show_detail(session)
        if action == "resume":
            launch_session(session); return
        if action is None: return


def project_select_flow():
    projects = load_projects()
    if not projects:
        print(f"\n  {RED}无法加载项目数据{RESET}"); return None
    while True:
        items = []
        for p in projects:
            n = len(p["sessions"]); rel = _relative_time(p["last_active"])
            tags_str = ", ".join(p["tags"][:3]) if p["tags"] else ""
            sub = f"{n} sessions  ·  {rel}"
            if tags_str: sub += f"  ·  {tags_str}"
            items.append({"label": p["title"], "sub": sub, "project": p, "color": BOLD})
        m = Menu("月球系统 · 选择项目", items, footer="↑↓ 导航  |  Enter 选择  |  q 返回")
        sel = m.run()
        if not sel: return None
        session = session_select_flow(sel["project"])
        if session is None: continue
        return session


def session_select_flow(project):
    while True:
        items = []
        for s in project["sessions"]:
            rel = _relative_time(s["ts"]); color = CATEGORY_COLORS.get(s.get("category", ""), "")
            goal = _trunc(s["goal"], 65) if s["goal"] else "(无信息)"
            outcome_icon = {"completed": "✅", "partial": "△", "abandoned": "✖"}.get(s.get("outcome", ""), "")
            sub = f"{rel}  ·  {outcome_icon} {_trunc(s.get('summary', ''), 45)}"
            items.append({"label": goal, "sub": sub, "session": {
                **s, "project_title": project["title"], "project_key": project["key"],
                "project_name": project["name"], "cwd": project.get("cwd", ""),
            }, "color": color})
        m = Menu(f"月球系统 · {project['title']}", items,
                 footer="↑↓ 导航  |  Enter 查看详情  |  q 返回")
        sel = m.run()
        if not sel: return None
        action = show_detail(sel["session"])
        if action == "resume": return sel["session"]
        if action is None: return None


# ── Workspace update ──────────────────────────────────────────────────────────
CATEGORY_LABELS = {
    "frontend": "前端开发", "backend": "后端开发", "devops": "部署运维",
    "debugging": "调试修复", "refactoring": "重构优化", "data": "数据处理",
    "docs": "文档写作", "config": "配置环境", "exploration": "探索研究",
    "ai_tools": "AI工具开发", "other": "其他",
}


def _run_incremental_and_collect():
    """Run workspace_init.py --incremental and parse its JSONL output."""
    init_script = str(WORKSPACE.parent.parent / "skills" / "apocalypse" / "workspace_init.py")
    result = subprocess.run(
        [sys.executable, init_script, "--incremental"],
        capture_output=True, text=True, timeout=600,
    )
    events = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line: continue
        try: events.append(json.loads(line))
        except Exception: continue
    return events


def _dump_summaries():
    """Run --dump-summaries and return parsed JSON."""
    init_script = str(WORKSPACE.parent.parent / "skills" / "apocalypse" / "workspace_init.py")
    result = subprocess.run(
        [sys.executable, init_script, "--dump-summaries"],
        capture_output=True, text=True, timeout=60,
    )
    try: return json.loads(result.stdout)
    except Exception: return {}


def _set_themes(themes_map):
    """Write title/tags via --set-themes. themes_map: {proj_key: {title, tags}}."""
    init_script = str(WORKSPACE.parent.parent / "skills" / "apocalypse" / "workspace_init.py")
    payload = json.dumps({"projects": themes_map}, ensure_ascii=False)
    subprocess.run(
        [sys.executable, init_script, "--set-themes"],
        input=payload, capture_output=True, text=True, timeout=30,
    )


def _auto_theme_from_categories(analyzed_sessions):
    """Derive a provisional title and tags from session categories."""
    cat_counts = {}
    sample_goals = []
    for sid, s in analyzed_sessions.items():
        cat = s.get("category", "other")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if len(sample_goals) < 3 and s.get("user_goal"):
            sample_goals.append(s["user_goal"])
    if not cat_counts:
        return {"title": "", "tags": []}
    top_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)
    main_cat = top_cats[0][0]
    title = CATEGORY_LABELS.get(main_cat, main_cat)
    tags = [CATEGORY_LABELS.get(c, c) for c, _ in top_cats[:3]]
    # Try to build a more specific title from goals
    if sample_goals:
        # Use first goal as title hint (truncated)
        hint = _trunc(sample_goals[0], 30)
        if hint:
            title = hint
    return {"title": title, "tags": tags}


def update_workspace():
    """Run incremental update and present results. Assign themes to new projects."""
    print(f"\n  {BOLD}{CYAN}Apocalypse Workspace 更新{RESET}\n")

    # Step 1: Run incremental analysis
    print(f"  {DIM}扫描新 session 并分析中...{RESET}")
    events = _run_incremental_and_collect()

    done_evt = None
    project_evts = []
    for e in events:
        if e.get("type") == "project_done":
            project_evts.append(e)
        elif e.get("type") == "done":
            done_evt = e
        elif e.get("type") == "error":
            print(f"  {RED}错误: {e.get('message', '')}{RESET}")
            return

    total_new = done_evt.get("total_sessions", 0) if done_evt else 0
    if total_new == 0:
        print(f"  {DIM}没有新的 session 需要分析。{RESET}")
        return

    # Step 2: Load updated workspace and show detailed changes
    ws = _load_workspace()
    print(f"\n  {GREEN}分析完成：{total_new} 个新 session，{len(project_evts)} 个项目有更新{RESET}\n")

    # Group new sessions by project and show details
    for evt in project_evts:
        proj_name = evt.get("project", "")
        new_count = evt.get("sessions", 0)
        # Find this project in workspace.json to get session details
        proj_record = None
        proj_title = proj_name
        for key, p in ws.get("projects", {}).items():
            if p.get("name") == proj_name:
                proj_record = p
                proj_title = p.get("title") or proj_name
                break

        print(f"  {BOLD}{proj_title}{RESET}  {DIM}({proj_name}){RESET}")
        print(f"    新增 {GREEN}{new_count}{RESET} 个 session")

        if proj_record:
            # Show the newest sessions (those with ts close to now)
            analyzed = proj_record.get("analyzed_sessions", {})
            # Sort by timestamp descending, take the new ones
            sorted_sids = sorted(analyzed.keys(),
                                 key=lambda s: analyzed[s].get("ts", ""), reverse=True)
            shown = 0
            for sid in sorted_sids:
                if shown >= new_count: break
                s = analyzed[sid]
                goal = _trunc(s.get("user_goal", ""), 65) or "(无信息)"
                summary = _trunc(s.get("summary", ""), 55)
                cat = s.get("category", "other")
                cat_label = CATEGORY_LABELS.get(cat, cat)
                print(f"    {DIM}•{RESET} {goal}")
                print(f"      {DIM}{summary}  [{cat_label}]{RESET}")
                shown += 1

        # Show current theme status
        title = proj_record.get("title", "") if proj_record else ""
        tags = proj_record.get("tags", []) if proj_record else []
        if title:
            print(f"    {DIM}当前主题:{RESET} {title}  {DIM}标签:{RESET} {', '.join(tags) if tags else '(无)'}")
        else:
            print(f"    {YELLOW}⚠ 无标题和标签，需要设定{RESET}")
        print()

    # Step 3: Check for projects needing themes
    summaries = _dump_summaries()
    projects_list = summaries.get("projects", [])
    needs_theme = [p for p in projects_list if not p.get("title")]

    if needs_theme:
        print(f"  {BOLD}{YELLOW}以下 {len(needs_theme)} 个项目需要设定标题和标签：{RESET}\n")
        themes_to_set = {}
        for p in needs_theme:
            key = p["key"]
            analyzed = {}
            if ws and key in ws.get("projects", {}):
                analyzed = ws["projects"][key].get("analyzed_sessions", {})
            auto = _auto_theme_from_categories(analyzed)
            goals = p.get("sample_goals", [])[:2]
            cat_bd = p.get("category_breakdown", {})
            top_cat = max(cat_bd.items(), key=lambda x: x[1])[0] if cat_bd else "other"

            print(f"  {BOLD}{p['folder_name']}{RESET}")
            print(f"    {DIM}Sessions:{RESET} {p['session_count']}  |  {DIM}主分类:{RESET} {CATEGORY_LABELS.get(top_cat, top_cat)}")
            if goals:
                for g in goals:
                    print(f"    {DIM}•{RESET} {_trunc(g, 60)}")
            print(f"    {GREEN}建议标题:{RESET} {auto['title']}")
            print(f"    {GREEN}建议标签:{RESET} {', '.join(auto['tags'])}")
            print()
            themes_to_set[key] = auto

        # Confirm and write
        print(f"  {DIM}{'─' * 50}{RESET}")
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

    print(f"  {DIM}打开 http://localhost:7749/workspace.html 查看更新后的星图。{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Apocalypse Launcher")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--update", action="store_true",
                        help="Update workspace: analyze new sessions, assign themes, show summary")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        projects = load_projects()
        out = [{"title": p["title"], "name": p["name"], "tags": p["tags"],
                "session_count": len(p["sessions"]), "last_active": p["last_active"],
                "sessions": [{"id": s["id"], "goal": s["goal"], "ts": s["ts"]} for s in p["sessions"]]}
               for p in projects]
        print(json.dumps(out, ensure_ascii=False, indent=2)); return

    if args.update:
        update_workspace(); return

    if args.refresh:
        print(f"  {DIM}增量更新中...{RESET}"); run_incremental()

    recent_sessions_menu()


if __name__ == "__main__":
    main()
