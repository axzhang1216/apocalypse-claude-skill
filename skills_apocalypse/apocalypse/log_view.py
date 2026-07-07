"""Session transcript viewer: parse jsonl, render to ANSI text, drive pager."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from apocalypse.tui import Style


PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Same noise prefixes as launcher.py (kept in sync with apocalypse.py NOISE_PREFIXES).
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


# ─── Block / Message types ───────────────────────────────────────────────


@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    tool_name: str
    summary: str
    full_input: str


@dataclass
class ToolResultBlock:
    content: str
    is_error: bool
    truncated: bool


@dataclass
class ThinkingBlock:
    text: str


Block = Union[TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock]


@dataclass
class Message:
    role: str  # "user" or "assistant"
    ts: str
    blocks: List[Block] = field(default_factory=list)


# ─── Parser ──────────────────────────────────────────────────────────────


def _is_noise(d: dict) -> bool:
    if d.get("isMeta"):
        return True
    msg = d.get("message") or {}
    content = msg.get("content", [])
    if isinstance(content, str):
        if any(content.startswith(p) for p in NOISE_PREFIXES):
            return True
        return False
    if not isinstance(content, list):
        return True
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            text = (c.get("text") or "").strip()
            if text and any(text.startswith(p) for p in NOISE_PREFIXES):
                return True
    return False


def _coerce_content(content) -> list:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return content
    return []


def _parse_blocks(content: list) -> List[Block]:
    blocks: List[Block] = []
    for c in _coerce_content(content):
        if not isinstance(c, dict):
            continue
        t = c.get("type")
        if t == "text":
            text = (c.get("text") or "").strip()
            if text:
                blocks.append(TextBlock(text=text))
        elif t == "thinking":
            text = (c.get("text") or "").strip()
            if text:
                blocks.append(ThinkingBlock(text=text))
        elif t == "tool_use":
            tool_name = c.get("name", "tool")
            inp = c.get("input", {})
            try:
                full_input = json.dumps(inp, ensure_ascii=False, indent=2)
            except Exception:
                full_input = str(inp)
            summary = _tool_summary(tool_name, inp)
            blocks.append(ToolUseBlock(tool_name=tool_name, summary=summary, full_input=full_input))
        elif t == "tool_result":
            content = c.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    item.get("text", "") for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            content = content or ""
            is_error = bool(c.get("is_error", False))
            truncated = len(content) > 500
            if truncated:
                content = content[:500] + f"\n[...{len(content) - 500} more chars]"
            blocks.append(ToolResultBlock(content=content, is_error=is_error, truncated=truncated))
    return blocks


def _tool_summary(tool_name: str, inp: dict) -> str:
    if not isinstance(inp, dict):
        return tool_name
    if tool_name == "Bash":
        cmd = inp.get("command", "")
        return f"Bash: {cmd[:80]}"
    if tool_name in ("Read", "Edit", "Write"):
        path = inp.get("file_path", "")
        return f"{tool_name}: {path}"
    if tool_name == "Glob":
        return f"Glob: {inp.get('pattern', '')}"
    if tool_name == "Grep":
        return f"Grep: {inp.get('pattern', '')}"
    return tool_name


def load_messages_from_path(path: Path) -> List[Message]:
    messages: List[Message] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if _is_noise(d):
                continue
            role = d.get("type") or d.get("message", {}).get("role", "")
            if role not in ("user", "assistant"):
                continue
            ts = d.get("timestamp", "")
            msg = d.get("message") or {}
            blocks = _parse_blocks(msg.get("content", []))
            if not blocks:
                continue
            messages.append(Message(role=role, ts=ts, blocks=blocks))
    return messages


def load_messages(sid: str) -> List[Message]:
    """Find the session jsonl by ID and return its messages."""
    for jsonl in PROJECTS_DIR.glob(f"*/{sid}.jsonl"):
        return load_messages_from_path(jsonl)
    raise FileNotFoundError(f"Session {sid} not found under {PROJECTS_DIR}")


# ─── Renderer ────────────────────────────────────────────────────────────


def _wrap(text: str, width: int, prefix: str = "  ") -> List[str]:
    """Wrap `text` to `width` with a leading prefix on every line."""
    if not text:
        return [prefix.rstrip()]
    out: List[str] = []
    for line in text.split("\n"):
        if not line:
            out.append(prefix.rstrip())
            continue
        while line:
            out.append(prefix + line[: max(1, width - len(prefix))])
            line = line[max(1, width - len(prefix)) :]
    return out


def messages_to_lines(
    messages: List[Message],
    *,
    expanded_tools: bool,
    width: int,
    style: Style,
) -> List[str]:
    """Render messages to a list of pre-coloured lines."""
    lines: List[str] = []
    for m in messages:
        ts = (m.ts or "")[:19]  # YYYY-MM-DDTHH:MM:SS
        hh = ts[11:19] if len(ts) >= 19 else ts
        if m.role == "user":
            head = style.green(style.bold("user"))
        else:
            head = style.blue(style.bold("assistant"))
        if hh:
            lines.append(f"[{style.dim(hh)}] {head}")
        else:
            lines.append(head)
        for b in m.blocks:
            if isinstance(b, TextBlock):
                lines.extend(_wrap(b.text, width))
            elif isinstance(b, ThinkingBlock):
                # Always render dim, regardless of expanded_tools
                for ln in _wrap(b.text, width, prefix="  " + style.dim("… ")):
                    lines.append(ln)
            elif isinstance(b, ToolUseBlock):
                glyph = style.glyph("⚙")
                head = f"{style.yellow(glyph + ' ' + b.tool_name)}"
                if b.summary and b.summary != b.tool_name:
                    head += style.dim(f"  {b.summary}")
                lines.append(head)
                if expanded_tools:
                    for ln in _wrap(b.full_input, width):
                        lines.append(ln)
            elif isinstance(b, ToolResultBlock):
                ok_glyph = style.glyph("✅" if not b.is_error else "❌")
                color = style.yellow if not b.is_error else style.red
                head = f"{color(ok_glyph + ' ' + ('tool error' if b.is_error else 'tool result'))}"
                lines.append(head)
                if expanded_tools or not b.truncated:
                    for ln in _wrap(b.content, width):
                        lines.append(ln)
                else:
                    first = b.content.split("\n", 1)[0]
                    lines.extend(_wrap(first[:200] + (style.dim(" [↓ more]") if len(first) > 200 else ""), width))
        lines.append("")  # blank line between messages
    if lines and lines[-1] == "":
        lines.pop()
    return lines


# ─── Entry point ─────────────────────────────────────────────────────────


def run(sid: str, *, raw: bool = False, tail: bool = False) -> int:
    """Entry point invoked by apocalypse.__main__ for `apocalypse log`."""
    style = Style()
    try:
        messages = load_messages(sid)
    except FileNotFoundError as e:
        print(f"[apocalypse log] {e}", file=sys.stderr)
        return 1

    width = 100  # sensible default; Pager handles wrap if needed
    lines = messages_to_lines(messages, expanded_tools=False, width=width, style=style)

    if raw or not sys.stdout.isatty():
        if not raw and not sys.stdout.isatty():
            print(
                "[apocalypse log] stdout is not a TTY — falling back to --raw mode. "
                "Pass --raw explicitly to silence this.",
                file=sys.stderr,
            )
        for ln in lines:
            print(ln)
        return 0

    if tail:
        # Real tail implementation arrives in Task 5 follow-up; for now
        # just render once and exit.
        for ln in lines:
            print(ln)
        return 0

    from apocalypse.tui import Pager, PagerState

    expanded = [False]  # mutable closure state

    def on_key(key, state):
        if key == "t":
            expanded[0] = not expanded[0]
            return PagerState(
                messages_to_lines(messages, expanded_tools=expanded[0], width=width, style=style),
                top=state.top,
                query=state.query,
            )
        return state

    def status(state):
        if expanded[0]:
            return style.dim("[t] collapse tools    q quit")
        return style.dim("[t] expand tools    q quit")

    pager = Pager(lines, on_key=on_key, status=status, height_fn=lambda: 24)
    pager.run()
    return 0