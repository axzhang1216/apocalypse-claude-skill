---
name: apocalypse
description: Start the Apocalypse agent monitoring dashboard. Use when the user types /apocalypse or asks to open the agent monitor, view agent status, see what Claude Code sessions are doing, or check running Claude Code agents on this machine.
---

# Apocalypse

When this skill is invoked, run the startup script and report the URL. Then check Workspace status and offer initialization if needed.

## Steps

1. Run the startup script:

   ```bash
   bash ~/.claude/skills/apocalypse/start.sh
   ```

2. Tell the user:
   - The dashboard is at **http://localhost:7749**
   - It shows real-time status for every Claude Code session on this machine
   - Session history persists to `~/.claude/apocalypse/` and survives terminal close
   - To stop the server: `kill $(cat ~/.claude/apocalypse/server.pid)`

3. Check Workspace status:

   ```bash
   curl -s http://localhost:7749/api/workspace/status
   ```

   - If `initialized` is `false`:
     > "发现你还没有初始化 Workspace。这会用 Claude API 分析所有历史 session，提取每个对话的目标和结果。可能需要几分钟。要现在开始吗？"
     - **User yes** → run full initialization (see step 4)
     - **User no** → skip, report dashboard URL, done

   - If `initialized` is `true`:
     - Run incremental update silently in the background:
       ```bash
       python ~/.claude/skills/apocalypse/workspace_init.py --incremental
       ```
     - Parse each `{"type":"project_done",...}` line from stdout and narrate if new sessions were found:
       > "已自动分析 N 个新 session（项目: X）"
     - On `{"type":"done","total_sessions":0}`: say nothing (no new sessions).
     - Then run the harness theme refinement (see step 5) on any newly analyzed or under-categorized projects.
     - Tell the user the Workspace view is at **http://localhost:7749/workspace.html**

## Step 4: Full Initialization (harness-driven)

The init process has three phases: **scan → report → confirm**.

### 4a. Session analysis (script)

Run the analysis script to scan all sessions and do per-session Haiku classification:

```bash
python ~/.claude/skills/apocalypse/workspace_init.py
```

Read stdout line by line and narrate each `project_done` event as it arrives:
> "{project} 分析完了——{sessions} 个 session。"

On the final `done` line, note the totals.

### 4b. Harness analysis (YOU are the harness)

Now comes the critical step that the standalone script cannot do well. **You** are the harness — use your own intelligence to produce meaningful project metadata.

The unit of classification is the **session** (single conversation), NOT the folder. A folder may contain sessions about different topics — each should land in the correct project.

Classification is a 4-step process:

#### Step 1: Initial folder-level grouping

Dump project summaries:

```bash
python ~/.claude/skills/apocalypse/workspace_init.py --dump-summaries
```

For each folder, review `sample_goals`, `category_breakdown`, `common_tools`, and `folder_name`. Assign a provisional title and tags.

#### Step 2: Session-level audit

For each folder, review every session's `user_goal` and `category`. If a session's topic clearly differs from the folder's main theme, split it out into its own project.

Example: The "Administrator" folder might contain sessions about Claude Code skill development (→ "Claude Code运维与工具开发"), but also sessions about a specific research project (→ should be its own project).

To check individual sessions, read the analyzed_sessions in workspace.json:

```bash
python -c "import json, pathlib; ws = json.loads(pathlib.Path.home().joinpath('.claude/apocalypse/workspace.json').read_text('utf-8')); ..."
```

#### Step 3: Merge related projects

After splitting, check if multiple projects should be merged:
- Multiple workdir sessions about the same topic → merge into one project
- Sessions from different folders about the same project (e.g. apocalypse sessions in both "Administrator" and "apocalypse" folders) → merge
- Multiple small projects with the same theme → merge

#### Step 4: Present for confirmation

Generate the final report (see step 4c).

**Important rules for tags:**
- Use **thematic tags**, NOT tool names. "Bash, Read, Write" is useless — every Claude Code session uses those.
- Think about the **domain** and **type of work**: "前端开发", "后端API", "调试修复", "重构优化", "配置部署", "数据分析", "文档写作", "代码探索", "AI工具开发", "DevOps", "自动化脚本", "监控运维", "游戏开发", "学术研究"

**Do NOT write metadata yet.** Proceed to step 4c.

### 4c. Init Report (present to user for confirmation)

Generate a formatted init report and present it to the user. The report must include:

1. **Overview**: total project folders, total sessions, date range
2. **Per-project table** with columns:
   - **项目**: descriptive title (derived from representative goals)
   - **项目文件夹**: the actual folder name on disk
   - **Sessions**: count
   - **时间范围**: first ~ last activity date
   - **标签**: thematic tags
   - **代表目标**: 1-2 representative user goals
3. **Failed sessions**: how many sessions had "Analysis failed" and why (short sessions, API errors, etc.)

Format the report as a markdown table. Example:

```
## Workspace Init Report

共 36 个项目文件夹，111 个 session（13 个分析失败）

| 项目 | 项目文件夹 | Sessions | 时间范围 | 标签 | 代表目标 |
|------|-----------|----------|----------|------|----------|
| Apocalypse监控仪表盘 | apocalypse | 8 | 05-27 ~ 06-04 | 前端开发, 3D可视化, AI工具开发 | 3D宇宙风格监控工作台... |
| Climate penalty论文 | Climate Panelty | 7 | 05-07 ~ 06-04 | 学术论文, 气候研究, LaTeX写作 | 写Climate penalty论文投npj... |
| ... | | | | | |

失败 session: 13 个（多为 "test"/"hello" 等极短对话）
```

Then ask the user:
> "以上是 init 分析报告。确认后我会更新到 Workspace 星图上。需要修改哪些项目吗？"

- **User confirms** → proceed to step 4d
- **User requests changes** → adjust the specific project title/tags per user feedback, then confirm again

### 4d. Apply metadata and update

Only after user confirmation, write project metadata back:

```bash
echo '{"projects": {"/path/to/proj": {"title": "项目标题", "tags": ["标签1", "标签2"]}, ...}}' | python ~/.claude/skills/apocalypse/workspace_init.py --set-themes
```

Then tell the user:
> "全部完成！已更新 {N} 个项目。打开 http://localhost:7749/workspace.html 查看 3D 宇宙图。"

## Step 5: Incremental Theme Refinement

When running incremental analysis (step 3, `initialized: true`), after the incremental script finishes:

1. If no new sessions were found (`total_sessions: 0`), skip to reporting dashboard URL. Done.
2. If new sessions were found, run `--dump-summaries` to get refreshed data.
3. Review projects that have new sessions or have `current_tags` that look like tool names (e.g. ["Bash", "Read", "Write"]).
4. Determine better title/tags for affected projects.
5. **Present a mini-report** to the user showing only changed projects:

   ```
   ## 增量更新报告

   新增 {N} 个 session：

   | 项目 | 项目文件夹 | 新增 Sessions | 当前标签 | 建议标签 |
   |------|-----------|--------------|----------|----------|
   | Apocalypse监控仪表盘 | apocalypse | 2 | AI工具开发, ... | 前端开发, 3D可视化, ... |
   ```

   > "以上是增量更新报告。确认后更新到星图。"

6. **User confirms** → write metadata via `--set-themes`, then report:
   > "已更新 {N} 个项目。"

## Standalone Workspace Update

Users can update the workspace independently of the `/apocalypse` skill invocation:

```bash
apocalypse --update
```

This runs the full update flow in one command:

1. **Scan**: runs `workspace_init.py --incremental` to analyze all new sessions since last update
2. **Report**: shows how many new sessions were found and which projects were affected
3. **Theme check**: identifies any new projects that lack title/tags (auto-assigns from session categories)
4. **Confirm**: presents proposed titles/tags and asks user to confirm before writing
5. **Write**: applies metadata via `--set-themes` and reports completion

For quick silent refresh (no UI):

```bash
apocalypse --refresh    # runs incremental analysis only, no summary
```

## Notes

Hooks are registered on first run via `~/.claude/settings.local.json`. Running this skill again is safe — it will not duplicate hooks or restart an already-running server.

The `workspace_init.py` script handles:
- **Session scanning and parsing** (mechanical, no AI needed)
- **Per-session Haiku classification** (fast, cheap, yields `user_goal`, `summary`, `outcome`, `category`, `key_tools`)
- **Data persistence** (reads/writes workspace.json, handles incremental updates)

The **harness** (you, via the skill) handles:
- **Project-level thematic analysis** (requires cross-session reasoning, pattern recognition, domain knowledge)
- **Theme quality control** (rejecting tool-name themes, ensuring labels are meaningful)

## Design Patterns & Lessons Learned

### 1. Noise filtering must happen at the record level

Session transcripts contain non-human messages: Multica bootstrap text, `<local-command-caveat>`, `<command-name>`, tool results, `isMeta` records. Filter these before any analysis.

Both `server.py` (`parse_conversation`) and `workspace_init.py` (`parse_session`) use the same `NOISE_PREFIXES` + `_is_noise_user()` pattern. Keep them in sync.

### 2. Haiku API: ThinkingBlock has no .text

Always iterate response content blocks to find a `TextBlock`:

```python
text = ""
for block in response.content:
    if hasattr(block, "text"):
        text = block.text.strip()
        break
```

Never assume `response.content[0].text`. Haiku extended thinking produces `ThinkingBlock` objects.

### 3. max_tokens must account for thinking budget

Haiku extended thinking consumes tokens. `max_tokens=256` is too small — use `max_tokens=1024` to leave room for both thinking and the actual JSON response.

### 4. Session is the classification unit, not folder

Folders like "Administrator", "ClaudeCode_Workspace", and "workdir" contain sessions about entirely different topics. The 4-step classification process handles this:

1. Folder-level grouping (provisional)
2. Session-level audit (split out misfits)
3. Merge related projects across folders
4. Present for user confirmation

### 5. workspace.html merges by title at display time

Projects with the same `title` are merged into one galaxy node. The merge logic adds `_totalSessions` and `_subKeys` (list of folder names) to the merged object. The tooltip shows folder count when >1. Solar system view shows all sessions from all merged sub-folders.

### 6. Confirm-before-writing pattern

Never write `--set-themes` until the user confirms the report. The harness generates title/tags, presents them as a table, and only writes after approval. This prevents wasted API calls and ensures the user owns the project structure.

### 7. workspace_init.py data model

Each project in workspace.json has:
- `name` — folder name (source of truth, set by scanner)
- `title` — human-readable project title (set by harness via `--set-themes`)
- `tags` — thematic labels (set by harness, replaces deprecated `top_themes`)
- `analyzed_sessions` — map of session_id → {user_goal, summary, outcome, category, key_tools, msg_count, ts}

`--set-themes` accepts `{"projects": {key: {title, tags}}}` format.
