#!/usr/bin/env python3
"""Workspace initializer for Apocalypse — scans all Claude Code session transcripts,
summarizes each session via Claude Haiku, writes ~/.claude/apocalypse/workspace.json.

Usage:
    python workspace_init.py             # full init
    python workspace_init.py --incremental  # only analyze new sessions
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
DATA_DIR = Path.home() / ".claude" / "apocalypse"
WORKSPACE_FILE = DATA_DIR / "workspace.json"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

SKIP_TYPES = {
    "attachment", "file-history-snapshot", "last-prompt", "permission-mode",
    "ai-title", "queue-operation", "hook_success", "hook_failure", "system",
}


def _project_name(cwd: str) -> str:
    if not cwd:
        return "unknown"
    s = str(cwd).replace("\\", "/").rstrip("/")
    return s.rsplit("/", 1)[-1] if s else "unknown"


def _ts_to_dt(ts: str):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _fmt_dt(dt) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


NOISE_PREFIXES = (
    "<local-command-caveat>", "<local-command-stdout>",
    "<command-message>", "<command-name>", "<command-args>",
    "<bash-input>", "<bash-stdout>", "<bash-stderr>",
    "You are running as a local coding agent for a Multica",
    "You are running as a chat assistant for a Multica",
    "<persisted-output>",
)


def _is_noise_user_record(d):
    """Return True if this user record is noise (not natural language from a human)."""
    if d.get("isMeta"):
        return True
    msg = d.get("message") or {}
    content = msg.get("content", [])
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return True
    # Tool results are noise (not natural language)
    if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
        return True
    # Check text content for noise prefixes
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            text = (c.get("text") or "").strip()
            if text and any(text.startswith(p) for p in NOISE_PREFIXES):
                return True
    return False


def _extract_texts(content):
    """Extract non-empty text strings from a content list."""
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return []
    return [c.get("text", "").strip() for c in content
            if isinstance(c, dict) and c.get("type") == "text" and (c.get("text") or "").strip()]


def parse_session(path: Path):
    """Parse a .jsonl transcript, filtering noise.

    Returns dict with:
      cwd, first_user_msg, last_assistant_msg, conversation_trace,
      tools_used, msg_count, tool_call_count, first_ts, last_ts
    """
    cwd = None
    user_msgs = []       # All real user text messages (chronological)
    last_assistant_msg = ""
    tools_used = []
    msg_count = 0        # Count of natural language exchanges only
    tool_call_count = 0
    first_ts = None
    last_ts = None

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

                if cwd is None and d.get("cwd"):
                    cwd = d["cwd"]

                t = d.get("type", "")
                if t in SKIP_TYPES:
                    continue

                ts = d.get("timestamp", "")
                ts_dt = _ts_to_dt(ts)
                if ts_dt:
                    if first_ts is None:
                        first_ts = ts_dt
                    last_ts = ts_dt

                if t == "user":
                    # Skip noise records
                    if _is_noise_user_record(d):
                        continue
                    msg = d.get("message") or {}
                    content = msg.get("content", [])
                    texts = _extract_texts(content)
                    if texts:
                        combined = "\n".join(texts)
                        user_msgs.append(combined)
                        msg_count += 1

                elif t == "assistant":
                    msg = d.get("message") or {}
                    content = msg.get("content", [])
                    if isinstance(content, str):
                        content = [{"type": "text", "text": content}]
                    if not isinstance(content, list):
                        continue

                    texts = [c.get("text", "") for c in content
                             if isinstance(c, dict) and c.get("type") == "text" and (c.get("text") or "").strip()]
                    tool_uses = [c for c in content
                                 if isinstance(c, dict) and c.get("type") == "tool_use"]
                    if texts:
                        last_assistant_msg = texts[-1]
                        msg_count += 1
                    for tu in tool_uses:
                        tool_call_count += 1
                        name = tu.get("name", "")
                        if name and name not in tools_used:
                            tools_used.append(name)

    except Exception:
        pass

    # Build conversation trace for Haiku context
    trace_parts = []
    for i, um in enumerate(user_msgs[:3]):
        label = "User" if i == 0 else f"User[{i+1}]"
        trace_parts.append(f"[{label}] {um[:400]}")
    if last_assistant_msg:
        trace_parts.append(f"[Assistant] {last_assistant_msg[:400]}")
    conversation_trace = "\n".join(trace_parts)

    return {
        "cwd": cwd or "",
        "first_user_msg": user_msgs[0][:2000] if user_msgs else "",
        "last_assistant_msg": last_assistant_msg[:2000],
        "conversation_trace": conversation_trace,
        "tools_used": tools_used,
        "msg_count": msg_count,
        "tool_call_count": tool_call_count,
        "first_ts": _fmt_dt(first_ts),
        "last_ts": _fmt_dt(last_ts),
    }


SESSION_CATEGORIES = [
    "frontend", "backend", "devops", "debugging", "refactoring",
    "data", "docs", "config", "exploration", "ai_tools", "other",
]

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

CATEGORY_PROMPT = "\n".join(
    f"- {k}: {v}" for k, v in CATEGORY_LABELS.items()
)


def summarize_session(client, session_data: dict) -> dict:
    """Call Claude Haiku to extract structured info from a session."""
    trace = session_data.get("conversation_trace", "")
    if not trace:
        trace = (session_data.get("first_user_msg", "")[:500] or "(empty session)")

    prompt = f"""You are analyzing a Claude Code session. Classify it.

Conversation:
{trace}

Tools used: {', '.join(session_data['tools_used']) or 'none'}
Total messages: {session_data['msg_count']}

Pick the best category from:
{CATEGORY_PROMPT}

Reply in JSON only (no markdown fences):
{{
  "user_goal": "one sentence, what the user wanted",
  "summary": "one sentence, what was accomplished",
  "outcome": "completed|partial|abandoned",
  "category": "one of the category keys above",
  "key_tools": ["Tool1", "Tool2"]
}}"""

    try:
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                break
        # Strip markdown fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        result = json.loads(text)
        # Validate outcome
        if result.get("outcome") not in ("completed", "partial", "abandoned"):
            result["outcome"] = "partial"
        if not isinstance(result.get("key_tools"), list):
            result["key_tools"] = session_data["tools_used"][:5]
        # Validate category
        if result.get("category") not in SESSION_CATEGORIES:
            result["category"] = "other"
        return result
    except Exception as e:
        return {
            "user_goal": session_data["first_user_msg"][:80] or "unknown",
            "summary": "Analysis failed",
            "outcome": "partial",
            "category": "other",
            "key_tools": session_data["tools_used"][:5],
        }


def scan_projects():
    """Return {project_key: {cwd, name, sessions: [Path]}}."""
    projects = {}
    if not PROJECTS_DIR.exists():
        return projects
    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        for jsonl in proj_dir.glob("*.jsonl"):
            session_id = jsonl.stem
            # Peek at cwd
            cwd = ""
            try:
                with open(jsonl, "r", encoding="utf-8", errors="replace") as f:
                    for raw in f:
                        try:
                            d = json.loads(raw.strip())
                            if d.get("cwd"):
                                cwd = d["cwd"]
                                break
                        except Exception:
                            continue
            except Exception:
                pass
            name = _project_name(cwd) if cwd else proj_dir.name
            key = cwd or proj_dir.name
            if key not in projects:
                projects[key] = {"cwd": cwd, "name": name, "sessions": []}
            projects[key]["sessions"].append(jsonl)
    return projects


def load_workspace() -> dict:
    if WORKSPACE_FILE.exists():
        try:
            return json.loads(WORKSPACE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "last_full_init": "", "projects": {}, "analyzed_session_ids": []}


def save_workspace(ws: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = WORKSPACE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ws, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, WORKSPACE_FILE)


def run(incremental: bool = False):
    try:
        import anthropic
    except ImportError:
        print(json.dumps({"type": "error", "message": "anthropic SDK not installed. Run: pip install anthropic"}), flush=True)
        sys.exit(1)

    client = anthropic.Anthropic()
    ws = load_workspace()
    already_analyzed = set(ws.get("analyzed_session_ids", []))

    raw_projects = scan_projects()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    total_new_sessions = 0
    total_projects_done = 0

    for proj_key, proj_info in raw_projects.items():
        sessions = proj_info["sessions"]
        cwd = proj_info["cwd"]
        name = proj_info["name"]

        # Initialize project record if missing
        if proj_key not in ws["projects"]:
            ws["projects"][proj_key] = {
                "name": name,
                "cwd": cwd,
                "title": "",
                "tags": [],
                "sessions": [],
                "total_messages": 0,
                "total_tool_calls": 0,
                "first_seen": "",
                "last_active": "",
                "analyzed_sessions": {},
            }

        proj_record = ws["projects"][proj_key]
        proj_record["sessions"] = [s.stem for s in sessions]

        new_sessions_in_project = 0
        category_counts = {}

        for jsonl in sessions:
            session_id = jsonl.stem
            if incremental and session_id in already_analyzed:
                continue

            data = parse_session(jsonl)

            # Update project aggregates
            proj_record["total_messages"] = proj_record.get("total_messages", 0) + data["msg_count"]
            proj_record["total_tool_calls"] = proj_record.get("total_tool_calls", 0) + data["tool_call_count"]

            # Track timestamps
            if data["first_ts"]:
                if not proj_record["first_seen"] or data["first_ts"] < proj_record["first_seen"]:
                    proj_record["first_seen"] = data["first_ts"]
            if data["last_ts"]:
                if not proj_record["last_active"] or data["last_ts"] > proj_record["last_active"]:
                    proj_record["last_active"] = data["last_ts"]

            # Summarize via Claude Haiku
            analysis = summarize_session(client, data)
            proj_record["analyzed_sessions"][session_id] = {
                "summary": analysis["summary"],
                "user_goal": analysis["user_goal"],
                "outcome": analysis["outcome"],
                "category": analysis.get("category", "other"),
                "key_tools": analysis["key_tools"],
                "msg_count": data["msg_count"],
                "ts": data["last_ts"] or data["first_ts"] or now_str,
            }

            if session_id not in ws["analyzed_session_ids"]:
                ws["analyzed_session_ids"].append(session_id)
            already_analyzed.add(session_id)

            new_sessions_in_project += 1
            total_new_sessions += 1

            # Count categories for project-level themes
            cat = analysis.get("category", "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        if new_sessions_in_project > 0:
            # Build category-based themes for this project
            total_categorized = sum(category_counts.values())
            top_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
            project_themes = [CATEGORY_LABELS.get(c, c) for c, _ in top_cats[:4]]

            # Merge with existing top_themes (for incremental runs)
            existing = set(proj_record.get("top_themes") or [])
            existing.update(project_themes)
            proj_record["top_themes"] = list(existing)[:5]

            total_projects_done += 1
            print(json.dumps({
                "type": "project_done",
                "project": name,
                "sessions": new_sessions_in_project,
                "top_themes": project_themes,
            }, ensure_ascii=False), flush=True)

        # Save after each project so progress is durable
        save_workspace(ws)

    if not incremental:
        ws["last_full_init"] = now_str

    ws["last_analysis"] = now_str
    save_workspace(ws)

    print(json.dumps({
        "type": "done",
        "total_projects": total_projects_done,
        "total_sessions": total_new_sessions,
    }, ensure_ascii=False), flush=True)


def dump_summaries():
    """Output compact project summaries for harness analysis."""
    ws = load_workspace()
    projects = []
    for proj_key, proj in ws.get("projects", {}).items():
        analyzed = proj.get("analyzed_sessions", {})
        if not analyzed:
            continue
        sample_goals = []
        cat_breakdown = {}
        all_tools = set()
        for sid, s in analyzed.items():
            goal = s.get("user_goal", "")
            if goal and len(sample_goals) < 8:
                sample_goals.append(goal)
            cat = s.get("category", "other")
            cat_breakdown[cat] = cat_breakdown.get(cat, 0) + 1
            for t in (s.get("key_tools") or []):
                all_tools.add(t)
        projects.append({
            "key": proj_key,
            "folder_name": proj.get("name", ""),
            "title": proj.get("title", ""),
            "tags": proj.get("tags", []),
            "session_count": len(analyzed),
            "date_range": f"{proj.get('first_seen', '?')[:10]} ~ {proj.get('last_active', '?')[:10]}",
            "sample_goals": sample_goals,
            "category_breakdown": cat_breakdown,
            "common_tools": sorted(all_tools)[:10],
            "total_messages": proj.get("total_messages", 0),
            "current_tags": proj.get("tags", []),
        })
    projects.sort(key=lambda p: p["session_count"], reverse=True)
    print(json.dumps(
        {"type": "project_summaries", "total_projects": len(projects), "projects": projects},
        ensure_ascii=False, indent=2,
    ), flush=True)


def set_themes():
    """Read project metadata from stdin and update workspace.json.

    Input format:
    {
      "projects": {
        "/path/to/proj": {
          "title": "项目标题",
          "tags": ["标签1", "标签2"]
        }
      }
    }
    """
    data = json.loads(sys.stdin.read())
    ws = load_workspace()
    count = 0
    projects_map = data.get("projects", {})
    for proj_key, meta in projects_map.items():
        if proj_key in ws.get("projects", {}):
            if "title" in meta:
                ws["projects"][proj_key]["title"] = meta["title"]
            if "tags" in meta:
                ws["projects"][proj_key]["tags"] = meta["tags"]
                ws["projects"][proj_key]["top_themes"] = meta["tags"]  # compat
            count += 1
    save_workspace(ws)
    print(json.dumps({"type": "projects_updated", "count": count}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize Apocalypse workspace data")
    parser.add_argument("--incremental", action="store_true",
                        help="Only analyze sessions not yet in workspace.json")
    parser.add_argument("--dump-summaries", action="store_true",
                        help="Output compact project summaries for harness analysis")
    parser.add_argument("--set-themes", action="store_true",
                        help="Read theme mapping from stdin and update workspace.json")
    args = parser.parse_args()
    if args.dump_summaries:
        dump_summaries()
    elif args.set_themes:
        set_themes()
    else:
        run(incremental=args.incremental)
