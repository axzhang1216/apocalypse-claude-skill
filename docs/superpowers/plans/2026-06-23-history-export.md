# Apocalypse History Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export each project's `point.messages` (existing discussion-decision slices) as human/Claude-readable markdown files into `<project-cwd>/.apocalypse/`, with per-session `.md` files, rolling `.old.N.md` siblings when over a size cap, and idempotent updates to the project's `CLAUDE.md` and `.gitignore`.

**Architecture:** All logic lives in `skills_apocalypse/workspace_init.py` (one new function `export_history()`, plus `load_config()`/`save_config()` helpers, plus a new `--export-history` CLI flag). The export function reads `workspace.json` and writes per-project files atomically. The existing `update_workspace()` flow is extended to invoke `export_history()` after `extract_points()`.

**Tech Stack:** Python 3 stdlib only (json, os, re, pathlib, datetime). No new dependencies.

**Reference spec:** `docs/superpowers/specs/2026-06-23-history-export-design.md`

**Reference code paths to know:**
- `skills_apocalypse/workspace_init.py:17-20` — `PROJECTS_DIR`, `DATA_DIR`, `WORKSPACE_FILE`, `HAIKU_MODEL` constants
- `skills_apocalypse/workspace_init.py:331-344` — existing `load_workspace()` / `save_workspace()` with atomic write pattern
- `skills_apocalypse/workspace_init.py:678-820` — existing `extract_points()` function and CLI plumbing to model after

---

## File Structure

**Modified files:**
- `skills_apocalypse/workspace_init.py` — add `load_config()`, `save_config()`, `export_history()` functions; add `--export-history` flag; chain into `update_workspace()` end (note: `update_workspace()` lives in `apocalypse.py:662+`, not in `workspace_init.py` itself — see Task 6)
- `skills_apocalypse/apocalypse.py` — call `export_history()` from `update_workspace()` after extract-points
- `skills_apocalypse/SKILL.md` — document `--export-history`, the install notice, and the new behaviour
- `skills_apocalypse/install.sh` — append the install notice at the end

**Created at runtime** (not source-controlled):
- `~/.claude/apocalypse/config.json` — auto-created on first `load_config()` if absent
- `<project-cwd>/.apocalypse/*.md` and `.gitignore` updates

**No new files in `skills_apocalypse/`** beyond modifications.

---

## Task 1: Config helpers

**Files:**
- Modify: `skills_apocalypse/workspace_init.py:17-20` (add `CONFIG_FILE` constant after existing constants)

- [ ] **Step 1: Add `CONFIG_FILE` constant**

After line 19 (`WORKSPACE_FILE = DATA_DIR / "workspace.json"`), add:

```python
CONFIG_FILE = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "export_history": True,
    "max_md_kb": 64,
    "old_kept": 3,
}
```

- [ ] **Step 2: Verify file is syntactically valid**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -m py_compile skills_apocalypse/workspace_init.py`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

Run:
```bash
cd "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse"
git add skills_apocalypse/workspace_init.py
git commit -m "feat(history-export): add CONFIG_FILE and DEFAULT_CONFIG constants"
```

---

## Task 2: `load_config()` and `save_config()`

**Files:**
- Modify: `skills_apocalypse/workspace_init.py` (add after `save_workspace()`, around line 345)

- [ ] **Step 1: Add `load_config()` and `save_config()` functions**

Insert after `save_workspace()`:

```python
def load_config() -> dict:
    """Load ~/.claude/apocalypse/config.json, falling back to defaults.

    On first call, creates the file with DEFAULT_CONFIG so users can
    discover and edit it.
    """
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_CONFIG)
    # Merge with defaults so new keys added in future versions get sensible values
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def save_config(cfg: dict) -> None:
    """Atomically write ~/.claude/apocalypse/config.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_FILE)
```

- [ ] **Step 2: Verify syntactically valid**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -m py_compile skills_apocalypse/workspace_init.py`
Expected: exit 0.

- [ ] **Step 3: Smoke-test the helpers**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -c "
from workspace_init import load_config, save_config, DEFAULT_CONFIG
cfg = load_config()
assert cfg == DEFAULT_CONFIG, f'expected defaults, got {cfg}'
import json
written = json.loads(open(r'C:\Users\Administrator\.claude\apocalypse\config.json').read())
assert written == DEFAULT_CONFIG, f'file content mismatch: {written}'
print('config helpers OK:', cfg)
"`

Expected output: `config helpers OK: {'export_history': True, 'max_md_kb': 64, 'old_kept': 3}`

- [ ] **Step 4: Commit**

Run:
```bash
cd "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse"
git add skills_apocalypse/workspace_init.py
git commit -m "feat(history-export): add load_config/save_config helpers"
```

---

## Task 3: Markdown rendering helpers

**Files:**
- Modify: `skills_apocalypse/workspace_init.py` (add after `save_config()`)

- [ ] **Step 1: Add `_slugify()` and `_render_session_md()` functions**

```python
def _slugify(text: str, max_len: int = 40) -> str:
    """Convert a topic title into a filename-safe slug, max 40 chars."""
    import re as _re
    s = (text or "").lower()
    s = _re.sub(r"[^a-z0-9一-鿿]+", "-", s)
    s = s.strip("-")
    if len(s) > max_len:
        s = s[:max_len].rsplit("-", 1)[0] or s[:max_len]
    return s or "untitled"


def _render_session_md(proj_title: str, session_id: str, session_meta: dict, points: list) -> str:
    """Render one session's points as a Markdown document.

    points: list of point dicts with keys topic, decision, ts, related_to, messages, id.
    """
    goal = session_meta.get("user_goal") or "(no recorded goal)"
    msg_count = session_meta.get("msg_count", 0)
    exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Title uses session goal (semantic, lets Claude find by meaning)
    title_first = goal.strip().split("\n", 1)[0].strip() or "(untitled session)"
    if len(title_first) > 120:
        title_first = title_first[:117] + "..."

    lines = [
        f"# {title_first}",
        "",
        f"**Project**: {proj_title}",
        f"**Session ID**: `{session_id}`",
        f"**Goal**: {goal}",
        f"**Messages**: {msg_count}",
        f"**Exported**: {exported_at}",
        "",
        "---",
        "",
    ]

    # Map point id -> "Discussion N" for related_to cross-refs
    pid_to_n = {p.get("id", ""): i + 1 for i, p in enumerate(points)}

    for i, p in enumerate(points, 1):
        topic = (p.get("topic") or "(no topic)").strip()
        decision = (p.get("decision") or "").strip()
        related_ids = p.get("related_to") or []
        related_labels = [f"Discussion {pid_to_n[rid]}" for rid in related_ids if rid in pid_to_n]

        lines.append(f"## Discussion {i}: {topic}")
        lines.append("")
        if decision:
            lines.append(f"**Decision**: {decision}")
            lines.append("")
        if related_labels:
            lines.append(f"**Related**: {', '.join(related_labels)}")
        else:
            lines.append("**Related**: (none)")
        lines.append("")

        for m in (p.get("messages") or []):
            role = m.get("role", "user").capitalize()
            text = (m.get("summary") or m.get("text") or "").strip()
            if not text:
                continue
            lines.append(f"### {role}")
            lines.append("")
            # Use blockquote for multi-line; collapse blank lines
            for ml in text.split("\n"):
                ml = ml.strip()
                if ml:
                    lines.append(f"> {ml}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_apocalypse_readme() -> str:
    """The .apocalypse/README.md describing the directory contents."""
    return """\
# Apocalypse 项目历史

此目录由 [Apocalypse](https://...) 自动维护。每个 `.md` 文件是一次
Claude Code session 的讨论归档，按"讨论/决策"分段。

**用途**：让未来的 Claude 看到本项目之前讨论过什么、做了什么决策。

**注意事项**：
- 主 md（不带 `.old` 后缀）是当前活跃的，会被 Apocalypse 自动重写
- `.old.*.md` 是历史滚动文件，不会被 Claude 默认读到
- 每次 `update workspace` 时此目录会被重新生成

**不要**手动编辑此目录——下次更新会覆盖。
"""
```

- [ ] **Step 2: Verify syntactically valid**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -m py_compile skills_apocalypse/workspace_init.py`
Expected: exit 0.

- [ ] **Step 3: Smoke-test rendering with synthetic data**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -c "
from workspace_init import _render_session_md, _slugify
# slugify
assert _slugify('Initialize React project') == 'initialize-react-project'
assert _slugify('中文标题测试') == '中文标题测试'
assert _slugify('!!!') == 'untitled'
# truncate
long = 'a ' * 50
slug = _slugify(long)
assert len(slug) <= 40, f'too long: {len(slug)}'
# render
md = _render_session_md('TestProj', 'abc12345-rest', {'user_goal': 'Test goal', 'msg_count': 10}, [
    {'id': 'p1', 'topic': 'Topic A', 'decision': 'Use X', 'related_to': ['p2'], 'messages': [
        {'role': 'user', 'text': 'Hello?'},
        {'role': 'assistant', 'text': 'World!', 'summary': 'Said world'},
    ]},
    {'id': 'p2', 'topic': 'Topic B', 'decision': '', 'related_to': [], 'messages': [
        {'role': 'user', 'text': 'Bye'},
    ]},
])
assert '# Test goal' in md
assert '## Discussion 1: Topic A' in md
assert '**Decision**: Use X' in md
assert '**Related**: Discussion 2' in md
assert '### User' in md
assert '> Said world' in md  # prefers summary
assert '## Discussion 2: Topic B' in md
print('rendering OK')
print('---')
print(md[:500])
"`

Expected: prints `rendering OK` followed by the first 500 chars of the rendered md (which should contain the assertions above).

- [ ] **Step 4: Commit**

Run:
```bash
cd "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse"
git add skills_apocalypse/workspace_init.py
git commit -m "feat(history-export): add session md rendering helpers"
```

---

## Task 4: Rolling helper (per-session md)

**Files:**
- Modify: `skills_apocalypse/workspace_init.py` (add after `_render_apocalypse_readme()`)

- [ ] **Step 1: Add `_roll_session_md()` function**

```python
def _roll_session_md(main_path: Path, content: str, old_kept: int) -> None:
    """Write a session md, rolling old content into .old.N.md siblings if oversized.

    `main_path` is the file we want to write to (e.g., `.apocalypse/2026-06-15-abc12345-init.md`).
    `content` is the newly-rendered md text.
    `old_kept` is how many .old.N.md siblings to keep (max N).
    """
    cap = max(0, old_kept)
    base = main_path.stem  # without .md
    parent = main_path.parent

    # If new content fits within cap, just write and return
    if len(content.encode("utf-8")) <= cap * 1024 if False else len(content.encode("utf-8")) <= 64 * 1024:
        # First write to a .tmp then atomic-replace (preserves behavior when no rolling)
        tmp = main_path.with_suffix(main_path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, main_path)
        # Note: actual cap check uses the configured max_md_kb; handled by caller.
        return

    # Shift .old.N.md siblings upward before moving the current main to .old.1
    # Build the chain we want to shift first to avoid clobbering during rename
    existing_olds = []
    for n in range(1, cap + 2):  # we may need to look one beyond kept range to know what to shift
        p = parent / f"{base}.old.{n}.md"
        if p.exists():
            existing_olds.append((n, p))
    # Delete beyond kept range first
    for n, p in existing_olds:
        if n > cap:
            try:
                p.unlink()
            except Exception as e:
                print(f"[history-export] could not delete {p}: {e}", file=sys.stderr)

    # Now shift kept ones up: .old.1 -> .old.2, .old.2 -> .old.3, etc.
    for n in range(cap, 0, -1):
        src = parent / f"{base}.old.{n}.md"
        dst = parent / f"{base}.old.{n + 1}.md"
        if src.exists():
            try:
                os.replace(src, dst)
            except Exception as e:
                print(f"[history-export] could not roll {src} -> {dst}: {e}", file=sys.stderr)

    # Move current main to .old.1
    if main_path.exists():
        dst = parent / f"{base}.old.1.md"
        try:
            os.replace(main_path, dst)
        except Exception as e:
            print(f"[history-export] could not move {main_path} -> {dst}: {e}", file=sys.stderr)

    # Write new main
    tmp = main_path.with_suffix(main_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, main_path)
```

Wait — the cap check above is wrong. Let me rewrite cleanly:

```python
def _roll_session_md(main_path: Path, content: str, max_kb: int, old_kept: int) -> None:
    """Write a session md, rolling old content into .old.N.md siblings if oversized.

    `main_path` is the file we want to write (e.g. `…/2026-06-15-abc12345-init.md`).
    `content` is the newly-rendered md text.
    `max_kb` is the soft cap; `old_kept` is how many `.old.N.md` siblings to keep.
    """
    cap_bytes = max_kb * 1024
    base = main_path.stem
    parent = main_path.parent

    new_size = len(content.encode("utf-8"))
    if new_size <= cap_bytes:
        # Fits — plain write, no rolling
        tmp = main_path.with_suffix(main_path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, main_path)
        return

    # Oversized — roll.
    # Step 1: delete any .old.N.md beyond old_kept range
    for n in range(old_kept + 1, old_kept + 10):  # bounded scan; no infinite loop
        p = parent / f"{base}.old.{n}.md"
        if not p.exists():
            break
        try:
            p.unlink()
        except Exception as e:
            print(f"[history-export] could not delete {p}: {e}", file=sys.stderr)

    # Step 2: shift kept ones up: .old.(N) -> .old.(N+1), reverse order to avoid clobbering
    for n in range(old_kept, 0, -1):
        src = parent / f"{base}.old.{n}.md"
        dst = parent / f"{base}.old.{n + 1}.md"
        if src.exists():
            try:
                os.replace(src, dst)
            except Exception as e:
                print(f"[history-export] could not roll {src} -> {dst}: {e}", file=sys.stderr)

    # Step 3: move current main to .old.1
    if main_path.exists():
        dst = parent / f"{base}.old.1.md"
        try:
            os.replace(main_path, dst)
        except Exception as e:
            print(f"[history-export] could not move {main_path} -> {dst}: {e}", file=sys.stderr)

    # Step 4: write new main
    tmp = main_path.with_suffix(main_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, main_path)
```

- [ ] **Step 2: Verify syntactically valid**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -m py_compile skills_apocalypse/workspace_init.py`
Expected: exit 0.

- [ ] **Step 3: Smoke-test rolling with a real fs scratch dir**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -c "
import shutil, tempfile, os
from pathlib import Path
from workspace_init import _roll_session_md

td = Path(tempfile.mkdtemp(prefix='apoc-roll-'))
try:
    main = td / '2026-06-15-abc12345-init.md'
    # First write: small, no rolling
    _roll_session_md(main, 'small content', max_kb=64, old_kept=3)
    assert main.exists()
    assert not (td / '2026-06-15-abc12345-init.md.old.1.md').exists()

    # Now simulate a large content that should trigger rolling
    big = '# huge\n' + ('x' * 70_000)
    _roll_session_md(main, big, max_kb=64, old_kept=3)
    assert main.exists()
    assert (td / '2026-06-15-abc12345-init.md.old.1.md').exists()

    # Roll again with another big content
    _roll_session_md(main, big + '\n## second\n' + ('y' * 70_000), max_kb=64, old_kept=3)
    assert (td / '2026-06-15-abc12345-init.md.old.2.md').exists()

    # With old_kept=2, the .old.3 should be deleted
    _roll_session_md(main, big + '\n## third\n' + ('z' * 70_000), max_kb=64, old_kept=2)
    assert not (td / '2026-06-15-abc12345-init.md.old.3.md').exists()
    print('rolling OK')
finally:
    shutil.rmtree(td)
"`

Expected: prints `rolling OK`.

- [ ] **Step 4: Commit**

Run:
```bash
cd "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse"
git add skills_apocalypse/workspace_init.py
git commit -m "feat(history-export): add _roll_session_md with .old.N.md shifting"
```

---

## Task 5: CLAUDE.md + .gitignore updaters

**Files:**
- Modify: `skills_apocalypse/workspace_init.py` (add after `_roll_session_md()`)

- [ ] **Step 1: Add `_update_claude_md()` and `_update_gitignore()`**

```python
APOCALYPSE_HISTORY_MARKER_START = "<!-- APOCALYPSE-HISTORY:START -->"
APOCALYPSE_HISTORY_MARKER_END = "<!-- APOCALYPSE-HISTORY:END -->"

APOCALYPSE_HISTORY_BLOCK = """\
<!-- APOCALYPSE-HISTORY:START -->
## Project History (Apocalypse)

此项目过往的 Claude Code session 已自动归档到 `.apocalypse/`，按"讨论/决策"
分章节组织（每 session 一个 md）。当用户问到本项目之前做过什么、决定过什么、
讨论过什么时，**先读** `.apocalypse/*.md`（不带 `.old` 后缀的）再回答。

- 主文件（活跃）= `.apocalypse/*.md`（无 `.old` 后缀）
- 历史滚动文件 = `.apocalypse/*.old.*.md`（默认不读，必要时翻）
- 目录说明 = `.apocalypse/README.md`

**不要修改** `.apocalypse/` 下的文件——下次 `update workspace` 会被覆盖。
<!-- APOCALYPSE-HISTORY:END -->"""


def _update_claude_md(cwd: Path) -> None:
    """Idempotently insert or replace the APOCALYPSE-HISTORY block in cwd/CLAUDE.md.

    - File missing: create with just the block.
    - Block present (START/END markers found): replace that range only.
    - Block absent: append at end with a leading blank line.
    Writes atomically; silent skip on permission errors.
    """
    target = cwd / "CLAUDE.md"
    try:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
    except Exception:
        return  # unreadable — skip silently

    if APOCALYPSE_HISTORY_MARKER_START in existing and APOCALYPSE_HISTORY_MARKER_END in existing:
        # Replace the block in place; preserve everything else verbatim
        import re
        pattern = re.compile(
            re.escape(APOCALYPSE_HISTORY_MARKER_START) + r".*?" + re.escape(APOCALYPSE_HISTORY_MARKER_END),
            re.DOTALL,
        )
        new_content = pattern.sub(APOCALYPSE_HISTORY_BLOCK, existing)
    else:
        # Append with leading blank line
        if existing and not existing.endswith("\n"):
            existing += "\n"
        new_content = existing + ("\n" if existing else "") + APOCALYPSE_HISTORY_BLOCK + "\n"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(new_content, encoding="utf-8")
        os.replace(tmp, target)
    except Exception as e:
        print(f"[history-export] could not write {target}: {e}", file=sys.stderr)


def _update_gitignore(cwd: Path) -> None:
    """Ensure cwd/.gitignore contains a line for `.apocalypse/`.

    Idempotent: uses regex to detect existing entry in multi-line mode.
    Silent skip on permission errors.
    """
    import re
    target = cwd / ".gitignore"
    pattern = re.compile(r"^\.apocalypse/?$", re.M)
    try:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
    except Exception:
        return

    if pattern.search(existing):
        return  # already covered

    addition = ".apocalypse/\n"
    if existing and not existing.endswith("\n"):
        existing += "\n"
    new_content = existing + addition

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(new_content, encoding="utf-8")
        os.replace(tmp, target)
    except Exception as e:
        print(f"[history-export] could not write {target}: {e}", file=sys.stderr)
```

- [ ] **Step 2: Verify syntactically valid**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -m py_compile skills_apocalypse/workspace_init.py`
Expected: exit 0.

- [ ] **Step 3: Smoke-test idempotent updates**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -c "
import shutil, tempfile
from pathlib import Path
from workspace_init import _update_claude_md, _update_gitignore, APOCALYPSE_HISTORY_BLOCK

td = Path(tempfile.mkdtemp(prefix='apoc-cwd-'))
try:
    # 1. CLAUDE.md doesn't exist — should be created
    _update_claude_md(td)
    cm = (td / 'CLAUDE.md').read_text(encoding='utf-8')
    assert 'APOCALYPSE-HISTORY:START' in cm
    print('case 1 OK: created new CLAUDE.md')

    # 2. CLAUDE.md exists without block — append
    (td / 'CLAUDE.md').write_text('# My Project\n\nSome user notes here.\n', encoding='utf-8')
    _update_claude_md(td)
    cm = (td / 'CLAUDE.md').read_text(encoding='utf-8')
    assert cm.startswith('# My Project') and 'APOCALYPSE-HISTORY:END' in cm
    assert 'Some user notes here.' in cm
    print('case 2 OK: appended, user content preserved')

    # 3. CLAUDE.md with existing block — replace only block
    (td / 'CLAUDE.md').write_text(
        '# My Project\n\nUser stuff.\n\n<!-- APOCALYPSE-HISTORY:START -->\nOLD BLOCK\n<!-- APOCALYPSE-HISTORY:END -->\n',
        encoding='utf-8')
    _update_claude_md(td)
    cm = (td / 'CLAUDE.md').read_text(encoding='utf-8')
    assert 'OLD BLOCK' not in cm
    assert 'APOCALYPSE-HISTORY:START' in cm
    assert 'User stuff.' in cm
    print('case 3 OK: replaced block only')

    # 4. .gitignore doesn't exist
    _update_gitignore(td)
    gi = (td / '.gitignore').read_text(encoding='utf-8')
    assert '.apocalypse/' in gi
    print('case 4 OK: .gitignore created')

    # 5. .gitignore exists without entry — append
    (td / '.gitignore').write_text('node_modules/\n*.log\n', encoding='utf-8')
    _update_gitignore(td)
    gi = (td / '.gitignore').read_text(encoding='utf-8')
    assert 'node_modules/' in gi and '.apocalypse/' in gi
    print('case 5 OK: .gitignore appended')

    # 6. .gitignore already has entry — no-op
    _update_gitignore(td)
    gi = (td / '.gitignore').read_text(encoding='utf-8')
    assert gi.count('.apocalypse/') == 1, 'should not duplicate'
    print('case 6 OK: idempotent')
finally:
    shutil.rmtree(td)
"`

Expected: prints six `OK` lines, one per case.

- [ ] **Step 4: Commit**

Run:
```bash
cd "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse"
git add skills_apocalypse/workspace_init.py
git commit -m "feat(history-export): add CLAUDE.md marked block + .gitignore updaters"
```

---

## Task 6: `export_history()` main function + CLI flag

**Files:**
- Modify: `skills_apocalypse/workspace_init.py` (add after `_update_gitignore()`)
- Modify: `skills_apocalypse/workspace_init.py:803-822` (CLI plumbing)

- [ ] **Step 1: Add `export_history()` function**

```python
def export_history() -> dict:
    """Export each project's discussion-decision points as markdown files
    under `<project-cwd>/.apocalypse/`, update per-project CLAUDE.md marked
    block and .gitignore. Idempotent — safe to re-run.

    Returns a summary dict {projects_processed, sessions_exported, skipped}.
    """
    cfg = load_config()
    if not cfg.get("export_history", True):
        print("[history-export] disabled in config.json (export_history=false), skipping")
        return {"projects_processed": 0, "sessions_exported": 0, "skipped": 0}

    max_kb = int(cfg.get("max_md_kb", 64))
    old_kept = int(cfg.get("old_kept", 3))

    ws = load_workspace()
    summary = {"projects_processed": 0, "sessions_exported": 0, "skipped": 0}

    for proj_key, proj in ws.get("projects", {}).items():
        cwd_str = proj.get("cwd", "")
        if not cwd_str:
            summary["skipped"] += 1
            continue
        cwd = Path(cwd_str)
        if not cwd.exists() or not cwd.is_dir():
            print(f"[history-export] skip {proj.get('title', proj_key)}: cwd not accessible ({cwd})", file=sys.stderr)
            summary["skipped"] += 1
            continue

        # Always update .gitignore first so any later crash doesn't leave md untracked.
        _update_gitignore(cwd)

        apo_dir = cwd / ".apocalypse"
        try:
            apo_dir.mkdir(parents=True, exist_ok=True)
            (apo_dir / "README.md").write_text(_render_apocalypse_readme(), encoding="utf-8")
        except Exception as e:
            print(f"[history-export] could not create {apo_dir}: {e}", file=sys.stderr)
            summary["skipped"] += 1
            continue

        proj_title = proj.get("title") or proj.get("name") or proj_key
        analyzed = proj.get("analyzed_sessions", {})
        points_by_sid = {}
        for p in proj.get("points", []) or []:
            sid = p.get("session_id")
            if sid:
                points_by_sid.setdefault(sid, []).append(p)

        n_sessions = 0
        for sid, s_meta in analyzed.items():
            session_points = points_by_sid.get(sid, [])
            if not session_points:
                continue
            # Skip sessions whose points have no messages (extract-points hasn't run)
            if not all(p.get("messages") for p in session_points):
                continue

            # Build md
            md_text = _render_session_md(proj_title, sid, s_meta, session_points)
            # Filename: <date>-<sid8>-<slug>.md (date from first point's ts)
            first_ts = session_points[0].get("ts") or s_meta.get("ts") or ""
            date_part = first_ts[:10] if first_ts else "unknown-date"
            slug = _slugify(session_points[0].get("topic", "") or s_meta.get("user_goal", ""))
            md_path = apo_dir / f"{date_part}-{sid[:8]}-{slug}.md"

            try:
                _roll_session_md(md_path, md_text, max_kb, old_kept)
                n_sessions += 1
            except Exception as e:
                print(f"[history-export] could not write {md_path}: {e}", file=sys.stderr)

        # Update CLAUDE.md marked block last (only if we managed to write something
        # or if the directory exists — i.e. always when we got this far)
        try:
            _update_claude_md(cwd)
        except Exception as e:
            print(f"[history-export] could not update CLAUDE.md in {cwd}: {e}", file=sys.stderr)

        summary["projects_processed"] += 1
        summary["sessions_exported"] += n_sessions
        if n_sessions:
            print(f"[history-export] {proj_title}: {n_sessions} session(s) → {apo_dir}")

    return summary
```

- [ ] **Step 2: Add `--export-history` CLI flag**

In the `__main__` block at `workspace_init.py:803-822`, replace the dispatcher:

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize Apocalypse workspace data")
    parser.add_argument("--incremental", action="store_true",
                        help="Only analyze sessions not yet in workspace.json")
    parser.add_argument("--dump-summaries", action="store_true",
                        help="Output compact project summaries for harness analysis")
    parser.add_argument("--set-themes", action="store_true",
                        help="Read theme mapping from stdin and update workspace.json")
    parser.add_argument("--extract-points", action="store_true",
                        help="Extract discussion-decision pairs from sessions")
    parser.add_argument("--export-history", action="store_true",
                        help="Export discussion-decision points as .apocalypse/ markdown per project")
    args = parser.parse_args()
    if args.dump_summaries:
        dump_summaries()
    elif args.set_themes:
        set_themes()
    elif args.export_history:
        result = export_history()
        print(json.dumps({"type": "done", **result}, ensure_ascii=False))
    elif args.extract_points:
        extract_points()
    else:
        run(incremental=args.incremental)
```

- [ ] **Step 3: Verify syntactically valid**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -m py_compile skills_apocalypse/workspace_init.py`
Expected: exit 0.

- [ ] **Step 4: Dry-run the flag (just verify it's wired)**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python skills_apocalypse/workspace_init.py --export-history 2>&1 | head -50`
Expected: prints `[history-export]` lines for each project, then a final JSON line like `{"type": "done", "projects_processed": N, "sessions_exported": M, "skipped": K}`. (No errors; if some projects are skipped due to inaccessible cwd, that's fine.)

- [ ] **Step 5: Commit**

Run:
```bash
cd "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse"
git add skills_apocalypse/workspace_init.py
git commit -m "feat(history-export): add export_history() + --export-history CLI flag"
```

---

## Task 7: Hook `export_history()` into `update_workspace()` flow

**Files:**
- Modify: `skills_apocalypse/apocalypse.py` — find `update_workspace()` function (around line 662) and chain `export_history()` after extract-points

- [ ] **Step 1: Locate the extract-points step in `apocalypse.py`**

Open `skills_apocalypse/apocalypse.py` and find the section in `update_workspace()` that runs the incremental + extract-points flow. The exact lines vary; find the call site that invokes `workspace_init.py --incremental` (search for "incremental" in this file). After that, the flow ends. We add our export step at the end.

- [ ] **Step 2: Add the export-history invocation**

At the very end of `update_workspace()` (after the theme refinement / harness-driven section), before the function returns, add:

```python
    # ── Step 3: Export discussion-decision history into each project's .apocalypse/
    try:
        from workspace_init import export_history
        result = export_history()
        if result.get("sessions_exported"):
            print(f"\n  {GREEN}已归档 {result['sessions_exported']} 个 session 到 {result['projects_processed']} 个项目的 .apocalypse/ {RESET}")
    except Exception as e:
        print(f"\n  {YELLOW}历史归档失败（不影响其他功能）: {e}{RESET}")
```

Note: `update_workspace()` lives in `apocalypse.py`, not `workspace_init.py`. The import inside the function body is intentional — it avoids making `apocalypse.py` fail to import on machines where `workspace_init.py` is missing (shouldn't happen in practice, but defensive). Confirm `GREEN` and `YELLOW` constants are already defined at the top of `apocalypse.py` (they are, per earlier reads).

- [ ] **Step 3: Verify syntactically valid**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -m py_compile skills_apocalypse/apocalypse.py`
Expected: exit 0.

- [ ] **Step 4: Smoke-test by invoking `apocalypse.py --refresh` with a tiny workspace**

Note: `--refresh` triggers `update_workspace()` which calls workspace_init + extract-points + theme refinement. The full flow runs Haiku calls (expensive). For this smoke test, instead:

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -c "
# Direct invocation test — just make sure the export_history import works
import sys
sys.path.insert(0, 'skills_apocalypse')
import apocalypse
import workspace_init
print('export_history callable:', callable(workspace_init.export_history))
# Now invoke the export step directly
result = workspace_init.export_history()
print('result:', result)
"`

Expected: prints `export_history callable: True`, then `result: {...}` with the summary dict. Some projects may print "skip ... cwd not accessible" warnings; that's expected if your workspace.json has projects from other machines or removed directories.

- [ ] **Step 5: Spot-check one project's `.apocalypse/` directory**

Pick any project that just got exported. Verify the files exist:

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -c "
import json, sys
sys.path.insert(0, 'skills_apocalypse')
from pathlib import Path
from workspace_init import load_workspace
ws = load_workspace()
# Find a project with a valid cwd that we just exported
for key, proj in ws.get('projects', {}).items():
    cwd = Path(proj.get('cwd', ''))
    if cwd.exists() and (cwd / '.apocalypse').exists():
        apo = cwd / '.apocalypse'
        files = sorted(apo.iterdir())
        print(f'Project: {proj.get(\"title\", key)}')
        print(f'cwd: {cwd}')
        print(f'Files in .apocalypse:')
        for f in files[:10]:
            print(f'  {f.name} ({f.stat().st_size} bytes)')
        # Spot-check CLAUDE.md and .gitignore
        cm = (cwd / 'CLAUDE.md').read_text(encoding='utf-8') if (cwd / 'CLAUDE.md').exists() else '(none)'
        gi = (cwd / '.gitignore').read_text(encoding='utf-8') if (cwd / '.gitignore').exists() else '(none)'
        print(f'CLAUDE.md has APOCALYPSE-HISTORY block: {\"APOCALYPSE-HISTORY:START\" in cm}')
        print(f'.gitignore has .apocalypse/: {\".apocalypse/\" in gi}')
        break
"

Expected: prints the project name, a list of files in `.apocalypse/`, and `True` for both block-presence checks.

- [ ] **Step 6: Commit**

Run:
```bash
cd "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse"
git add skills_apocalypse/apocalypse.py
git commit -m "feat(history-export): invoke export_history at end of update_workspace"
```

---

## Task 8: install.sh notice + SKILL.md updates

**Files:**
- Modify: `skills_apocalypse/install.sh` (append notice at end)
- Modify: `skills_apocalypse/SKILL.md` (document new behaviour)

- [ ] **Step 1: Append install notice to `install.sh`**

In `skills_apocalypse/install.sh`, after the final `echo` line (around line 70), add:

```bash
echo ""
echo "────────────────────────────────────────────────────────────"
echo "  Apocalypse 历史归档已默认开启"
echo "  每次 update workspace 会把聊天按讨论/决策切块，导出到"
echo "  各项目下的 .apocalypse/，并在 CLAUDE.md 插入说明段落。"
echo "  关闭方法：编辑 ~/.claude/apocalypse/config.json，"
echo "  设 \"export_history\": false"
echo "────────────────────────────────────────────────────────────"
```

- [ ] **Step 2: Update SKILL.md to mention `--export-history`**

In `skills_apocalypse/SKILL.md`, find the section that lists CLI commands (search for `apocalypse --refresh`). After it, add:

```markdown
## History export

Each project's discussion-decision slices (from `extract-points`) are exported as
markdown files into `<project-cwd>/.apocalypse/`, with one `.md` per session,
sections per discussion/decision. When this runs:

- A marked block (`APOCALYPSE-HISTORY:START/END`) is inserted into the project's
  `CLAUDE.md` pointing future Claude at the archive
- `.apocalypse/` is added to the project's `.gitignore` automatically
- Files roll into `.old.N.md` siblings when they exceed 64 KB (configurable)

Disable by editing `~/.claude/apocalypse/config.json` (`export_history: false`).
Re-run manually with:

```bash
python ~/.claude/skills/apocalypse/workspace_init.py --export-history
```
```

- [ ] **Step 3: Verify syntactic validity**

Run:
```bash
bash -n "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse/skills_apocalypse/install.sh" && echo "install.sh OK"
```

Expected: prints `install.sh OK`.

- [ ] **Step 4: Re-install and verify the notice appears**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && bash skills_apocalypse/install.sh 2>&1 | tail -15`
Expected: the install notice block (`───` lines + Chinese text) appears at the end of the output.

- [ ] **Step 5: Commit**

Run:
```bash
cd "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse"
git add skills_apocalypse/install.sh skills_apocalypse/SKILL.md
git commit -m "docs(history-export): install notice + SKILL.md updates"
```

---

## Task 9: Full end-to-end verification + final run on user's workspace

**Files:** (no code changes; this is the manual verification step)

- [ ] **Step 1: Restart the Apocalypse server to pick up changes**

Run:
```bash
# Find and kill the existing server, then restart
PID=$(cat ~/.claude/apocalypse/server.pid 2>/dev/null)
if [ -n "$PID" ]; then taskkill //F //PID "$PID" 2>/dev/null; fi
cd "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse" && bash skills_apocalypse/start.sh
```

Expected: prints `Apocalypse server started` (or "already running" if kill failed).

- [ ] **Step 2: Run the full export against the user's workspace**

Run: `cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python skills_apocalypse/workspace_init.py --export-history 2>&1 | tail -50`
Expected: prints `[history-export]` lines for each project, then a final JSON summary line. Some lines may say "skip ... cwd not accessible" — that's expected for projects whose cwd no longer exists.

- [ ] **Step 3: Spot-check 3 projects' `.apocalypse/` directories**

Pick three projects from the output. For each, verify:
1. `.apocalypse/README.md` exists
2. At least one `<date>-<sid8>-<slug>.md` file exists (if the project has any points with messages)
3. `CLAUDE.md` contains `APOCALYPSE-HISTORY:START` block
4. `.gitignore` contains `.apocalypse/`

Run:
```bash
cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -c "
import sys
sys.path.insert(0, 'skills_apocalypse')
from pathlib import Path
from workspace_init import load_workspace
ws = load_workspace()
checked = 0
for key, proj in ws.get('projects', {}).items():
    cwd = Path(proj.get('cwd', ''))
    if not cwd.exists():
        continue
    apo = cwd / '.apocalypse'
    if not apo.exists():
        continue
    md_files = [f for f in apo.iterdir() if f.suffix == '.md' and not f.name.startswith('.')]
    cm = (cwd / 'CLAUDE.md').read_text(encoding='utf-8') if (cwd / 'CLAUDE.md').exists() else ''
    gi = (cwd / '.gitignore').read_text(encoding='utf-8') if (cwd / '.gitignore').exists() else ''
    print(f'{proj.get(\"title\", key)}:')
    print(f'  .apocalypse/{len(md_files)} md files, README={\"README.md\" in [f.name for f in apo.iterdir()]}')
    print(f'  CLAUDE.md block: {\"APOCALYPSE-HISTORY:START\" in cm}')
    print(f'  .gitignore: {\".apocalypse/\" in gi}')
    if md_files:
        sample = md_files[0]
        content = sample.read_text(encoding='utf-8')[:300]
        print(f'  sample ({sample.name}):')
        for line in content.split('\n')[:8]:
            print(f'    {line}')
    checked += 1
    if checked >= 3:
        break
"
```

Expected: each of the 3 projects shows all checks `True`, with sample md content containing headers (`#`, `##`).

- [ ] **Step 4: Test opt-out works**

Run:
```bash
cd "E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse" && python -c "
import json, sys
sys.path.insert(0, 'skills_apocalypse')
from workspace_init import save_config, load_config, CONFIG_FILE
save_config({'export_history': False, 'max_md_kb': 64, 'old_kept': 3})
result = load_config()
assert result['export_history'] is False
print('opt-out config saved:', result)
"
# Now run export again — should print skip message
python skills_apocalypse/workspace_init.py --export-history 2>&1 | head -3
# Restore opt-in
python -c "
import sys; sys.path.insert(0, 'skills_apocalypse')
from workspace_init import save_config, DEFAULT_CONFIG
save_config(DEFAULT_CONFIG)
print('restored to defaults')
"
```

Expected: opt-out config saves, export prints `[history-export] disabled in config.json...`, config restored.

- [ ] **Step 5: Commit final state (if any tweaks were made)**

If the spot-check or opt-out test revealed fixes needed, commit them:
```bash
cd "E:/BaiduSyncdisk/ClaudeCode_Workspace/apocalypse"
git status
# If clean, no commit needed. If anything changed:
git add -A
git commit -m "chore(history-export): end-to-end verification fixes"
```

---

## Self-Review (by planner)

**1. Spec coverage:**

| Spec section | Task |
|---|---|
| `CONFIG_FILE` + `DEFAULT_CONFIG` | T1 |
| `load_config`/`save_config` | T2 |
| Markdown rendering (slug, render_session_md, README) | T3 |
| Rolling algorithm (.old.N.md shifting) | T4 |
| CLAUDE.md marked block updater | T5 |
| .gitignore idempotent updater | T5 |
| `export_history()` main function | T6 |
| `--export-history` CLI flag | T6 |
| Hook into `update_workspace()` flow | T7 |
| Install notice | T8 |
| SKILL.md docs | T8 |
| Manual verification (happy path, rolling, opt-out) | T9 |

All covered. ✓

**2. Placeholder scan:** No "TBD" / "implement later" / "similar to Task N". Each step has exact code or exact commands. ✓

**3. Type/name consistency:**
- `CONFIG_FILE`, `DEFAULT_CONFIG`, `load_config`, `save_config` — used consistently across T1, T2, T6
- `_slugify`, `_render_session_md`, `_render_apocalypse_readme`, `_roll_session_md`, `_update_claude_md`, `_update_gitignore`, `APOCALYPSE_HISTORY_BLOCK`, `APOCALYPSE_HISTORY_MARKER_START/END` — all defined in their first-use task and referenced consistently later
- `export_history()` returns `dict` with keys `projects_processed`, `sessions_exported`, `skipped` — T6 defines, T7 consumes with the right keys
- `_roll_session_md` signature `(main_path, content, max_kb, old_kept)` — T4 defines, T6 calls with 4 args

All consistent. ✓

**4. Ambiguity check:** All "how exactly" decisions (slug truncation rules, file format, marker syntax) are pinned in the spec. Each step's code is complete. ✓