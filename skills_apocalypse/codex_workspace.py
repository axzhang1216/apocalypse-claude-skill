from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

CODEX_DIR = Path.home() / ".codex"
CODEX_SESSIONS_DIR = CODEX_DIR / "sessions"
CODEX_INDEX_FILE = CODEX_DIR / "session_index.jsonl"
CODEX_WORKSPACE_FILE = Path.home() / ".claude" / "apocalypse" / "codex_workspace.json"


def _project_name(cwd: str) -> str:
    if not cwd:
        return "unknown"
    s = str(cwd).replace("\\", "/").rstrip("/")
    return s.rsplit("/", 1)[-1] if s else "unknown"


def _fmt_dt(dt):
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(ts: str):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _truncate(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def load_codex_workspace() -> dict:
    if CODEX_WORKSPACE_FILE.exists():
        try:
            data = json.loads(CODEX_WORKSPACE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"version": 1, "last_scan": "", "projects": {}, "analyzed_session_ids": []}


def save_codex_workspace(ws: dict) -> None:
    CODEX_WORKSPACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CODEX_WORKSPACE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ws, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CODEX_WORKSPACE_FILE)


def _load_thread_names() -> dict:
    names = {}
    if not CODEX_INDEX_FILE.exists():
        return names
    try:
        with open(CODEX_INDEX_FILE, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                sid = d.get("id")
                thread_name = d.get("thread_name")
                if sid and thread_name:
                    names[sid] = thread_name
    except Exception:
        pass
    return names


def _iter_codex_session_paths():
    if not CODEX_SESSIONS_DIR.exists():
        return []
    return sorted(
        (path for path in CODEX_SESSIONS_DIR.rglob("*.jsonl") if path.is_file()),
        key=lambda p: p.as_posix(),
    )


def _find_codex_transcript(session_id: str):
    if not session_id or not CODEX_SESSIONS_DIR.exists():
        return None
    session_id = str(session_id).strip()
    if not session_id or "/" in session_id or "\\" in session_id or session_id.startswith("."):
        return None
    for path in _iter_codex_session_paths():
        if path.stem == session_id or path.name.endswith(f"{session_id}.jsonl"):
            return path
    return None


def _parse_codex_session(path: Path) -> dict:
    cwd = ""
    session_id = ""
    first_ts = None
    last_ts = None
    user_msgs = []
    last_assistant_msg = ""
    tools_used = []
    msg_count = 0

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
                if d.get("type") == "session_meta":
                    payload = d.get("payload") or {}
                    session_id = payload.get("id") or session_id
                    cwd = payload.get("cwd") or cwd
                    continue
                if d.get("type") != "response_item":
                    continue
                payload = d.get("payload") or {}
                ts = d.get("timestamp", "")
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except Exception:
                        dt = None
                    if dt:
                        if first_ts is None:
                            first_ts = dt
                        last_ts = dt
                ptype = payload.get("type")
                if ptype == "message":
                    role = payload.get("role")
                    if role == "developer":
                        continue
                    texts = [
                        c.get("text", "").strip()
                        for c in (payload.get("content") or [])
                        if isinstance(c, dict) and c.get("text")
                    ]
                    if not texts:
                        continue
                    joined = "\n".join(t for t in texts if t)
                    if role == "user":
                        user_msgs.append(joined)
                        msg_count += 1
                    elif role == "assistant":
                        last_assistant_msg = joined
                        msg_count += 1
                elif ptype in ("function_call", "custom_tool_call"):
                    name = payload.get("name") or ""
                    if name and name not in tools_used:
                        tools_used.append(name)
    except Exception:
        pass

    return {
        "session_id": session_id or path.stem,
        "cwd": cwd,
        "project_name": _project_name(cwd),
        "first_user_msg": user_msgs[0][:2000] if user_msgs else "",
        "last_assistant_msg": last_assistant_msg[:2000],
        "tools_used": tools_used,
        "msg_count": msg_count,
        "first_ts": _fmt_dt(first_ts),
        "last_ts": _fmt_dt(last_ts),
    }


def _session_sort_key(session: dict):
    return _parse_dt(session.get("ts", "")) or _parse_dt(session.get("last_ts", "")) or datetime.min.replace(
        tzinfo=timezone.utc
    )


def _project_sort_key(project: dict):
    return _parse_dt(project.get("last_active", "")) or datetime.min.replace(tzinfo=timezone.utc)


def _build_session_record(meta: dict, thread_name: str) -> dict:
    session_id = meta.get("session_id", "")
    cwd = meta.get("cwd", "")
    project_name = meta.get("project_name") or _project_name(cwd)
    project_key = cwd or project_name or "unknown"
    first_user_msg = meta.get("first_user_msg", "")
    last_assistant_msg = meta.get("last_assistant_msg", "")
    goal = thread_name or first_user_msg or project_name or session_id
    summary = last_assistant_msg or first_user_msg or thread_name or ""
    ts = meta.get("last_ts") or meta.get("first_ts") or ""
    outcome = "completed" if last_assistant_msg else "partial"
    return {
        "id": session_id,
        "session_id": session_id,
        "project_key": project_key,
        "project_name": project_name,
        "project_title": project_name,
        "goal": goal[:2000],
        "summary": summary[:2000],
        "category": "other",
        "ts": ts,
        "outcome": outcome,
        "cwd": cwd,
        "thread_name": thread_name or "",
        "first_user_msg": first_user_msg,
        "last_assistant_msg": last_assistant_msg,
        "tools_used": list(meta.get("tools_used") or []),
        "msg_count": int(meta.get("msg_count") or 0),
        "first_ts": meta.get("first_ts", ""),
        "last_ts": meta.get("last_ts", ""),
    }


def _rebuild_project_cache(ws: dict) -> None:
    projects = {}
    for session in (ws.get("sessions") or {}).values():
        project_key = session.get("project_key") or session.get("cwd") or session.get("project_name") or "unknown"
        project_name = session.get("project_name") or _project_name(session.get("cwd", ""))
        project = projects.setdefault(
            project_key,
            {
                "key": project_key,
                "name": project_name,
                "title": project_name,
                "tags": [],
                "last_active": "",
                "cwd": session.get("cwd", ""),
                "sessions": [],
            },
        )
        project["sessions"].append(
            {
                "id": session.get("id", ""),
                "goal": session.get("goal", ""),
                "summary": session.get("summary", ""),
                "category": session.get("category", "other"),
                "ts": session.get("ts", ""),
                "outcome": session.get("outcome", "partial"),
            }
        )
        ts = session.get("ts", "")
        if ts and (not project["last_active"] or ts > project["last_active"]):
            project["last_active"] = ts

    for project in projects.values():
        project["sessions"].sort(key=lambda item: _parse_dt(item.get("ts", "")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    ws["projects"] = projects


def update_codex_workspace(incremental: bool = False) -> dict:
    ws = load_codex_workspace()
    if not incremental:
        ws["projects"] = {}
        ws["analyzed_session_ids"] = []
        ws["sessions"] = {}
    else:
        if not isinstance(ws.get("projects"), dict):
            ws["projects"] = {}
        if not isinstance(ws.get("sessions"), dict):
            ws["sessions"] = {}
        if not isinstance(ws.get("analyzed_session_ids"), list):
            ws["analyzed_session_ids"] = []

    analyzed = set(ws.get("analyzed_session_ids", []))
    thread_names = _load_thread_names()
    scanned = 0
    added = 0
    skipped = 0

    for path in _iter_codex_session_paths():
        scanned += 1
        meta = _parse_codex_session(path)
        session_id = meta.get("session_id") or path.stem
        if incremental and session_id in analyzed:
            existing = ws["sessions"].get(session_id)
            if isinstance(existing, dict):
                existing["thread_name"] = thread_names.get(session_id) or existing.get("thread_name", "")
                existing["goal"] = existing["thread_name"] or existing.get("goal", "")
            skipped += 1
            continue

        ws["sessions"][session_id] = _build_session_record(meta, thread_names.get(session_id, ""))
        if session_id not in analyzed:
            ws["analyzed_session_ids"].append(session_id)
            analyzed.add(session_id)
        added += 1

    ws["analyzed_session_ids"] = list(dict.fromkeys(ws.get("analyzed_session_ids", [])))
    _rebuild_project_cache(ws)
    ws["last_scan"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_codex_workspace(ws)
    return {
        "projects": len(ws.get("projects", {})),
        "sessions": len(ws.get("sessions", {})),
        "scanned_sessions": scanned,
        "new_sessions": added,
        "skipped_sessions": skipped,
        "last_scan": ws["last_scan"],
    }


def load_codex_projects() -> list[dict]:
    ws = load_codex_workspace()
    projects = list((ws.get("projects") or {}).values())
    projects.sort(key=_project_sort_key, reverse=True)
    return projects


def load_codex_recent_sessions(limit: int = 5) -> list[dict]:
    ws = load_codex_workspace()
    sessions = list((ws.get("sessions") or {}).values())
    sessions.sort(key=_session_sort_key, reverse=True)
    if limit is None or limit < 0:
        return sessions
    return sessions[:limit]


def parse_codex_transcript_preview(session_id: str, max_user: int = 3, max_chars: int = 300) -> tuple[list[str], str]:
    path = _find_codex_transcript(session_id)
    if not path:
        return [], ""

    user_msgs = []
    last_assistant_msg = ""

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
                if d.get("type") != "response_item":
                    continue
                payload = d.get("payload") or {}
                if payload.get("type") != "message":
                    continue
                role = payload.get("role")
                if role == "developer":
                    continue
                content = payload.get("content") or []
                if not isinstance(content, list):
                    continue
                texts = [
                    c.get("text", "").strip()
                    for c in content
                    if isinstance(c, dict) and c.get("text")
                ]
                if not texts:
                    continue
                joined = "\n".join(t for t in texts if t)
                if role == "user" and len(user_msgs) < max_user:
                    user_msgs.append(_truncate(joined, max_chars))
                elif role == "assistant":
                    last_assistant_msg = _truncate(joined, max_chars)
    except Exception:
        return [], ""

    return user_msgs, last_assistant_msg


if __name__ == "__main__":
    ws = load_codex_workspace()
    assert isinstance(ws, dict)
    names = _load_thread_names()
    assert isinstance(names, dict)
    print("codex_workspace basic IO OK", len(names))
