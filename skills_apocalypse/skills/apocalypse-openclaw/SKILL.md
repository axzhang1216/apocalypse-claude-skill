---
name: apocalypse-openclaw
description: Bridge between OpenClaw (remote chat) and local Claude Code sessions. Use when the user wants to: (1) list/check all local Claude Code sessions, (2) read conversation records from past sessions, (3) send commands/questions to a specific past session, (4) investigate which model/provider was used, (5) query session status or activity, (6) detect and respond to stuck sessions waiting for input, (7) kill stuck processes and fix corrupted conversation files. Requires Apocalypse dashboard (localhost:7749) and ccr code CLI on the local machine.
---

# Apocalypse OpenClaw Bridge

Remote interface to local Claude Code sessions via the Apocalypse dashboard API + `ccr code` CLI.

## Prerequisites

- Apocalypse dashboard running at `http://localhost:7749`
- `ccr code` CLI available in PATH (Claude Code wrapped by claude-code-router)

## API: Session Listing & Reading

All session data comes from the Apocalypse dashboard HTTP API:

### List all sessions

```powershell
Invoke-RestMethod -Uri "http://localhost:7749/api/sessions2" -UseBasicParsing
```

Returns an array of sessions, each with:
- `session_id`: real session UUID (usable with `ccr code --resume`)
- `cwd`: working directory (for `cd` before resume)
- `project_name`: project name
- `last_ts`: last activity timestamp (ISO 8601 UTC)
- `status`: `"green"` (actively running), `"yellow"` (idle), `"grey"` (inactive >24h)

### Read conversation content of a session

```powershell
Invoke-RestMethod -Uri "http://localhost:7749/api/sessions2/<session_id>" -UseBasicParsing
```

Returns the full conversation transcript with roles: `user`, `assistant`, `thinking`, `tool`. Each message has `ts` (timestamp) and `text` content. Tool calls include `tool_use_id`, `tool` name, `input`, and `output`.

## Command: Send Questions to a Session

Use `ccr code --resume` in non-interactive print mode to query a past session:

```powershell
cmd /c "cd /d <cwd> && ccr code --resume <session_id> --print -p ""<question>"""
```

**Important rules:**
- Set `cwd` to the session's `cwd` from the session list (some sessions require project context)
- Use `ccr code` NOT `claude`: CCR wraps the Claude Code CLI
- `--print -p` for non-interactive mode (prints response and exits)
- Expect ~30-300s response time (goes through CCR -> provider)
- Use `timeout 300` or higher for long context resumption
- Session IDs from Apocalypse ARE the real UUIDs

## Workflows

### 1. Check what a session discussed

```
List sessions -> pick one -> read conversation -> summarize for user
```

### 2. Ask a session about its own conclusions

```
List sessions -> find target by project_name -> resume with question -> return answer
```

### 3. Investigate model/provider usage

The session has access to its own tool call logs. Ask directly:

```
ccr code --resume <id> --print -p "本session实际调用了哪个provider的什么模型？查看ccr日志或session记录"
```

### 4. Check currently running sessions

Filter sessions with status "green" (executing) or "yellow" (idle/awaiting input).

### 5. Find sessions by project or time

Session list is sortable by `last_ts`. Filter by `project_name` or date.

## Stuck Session Detection

A Claude Code session can get stuck waiting for user input (permission prompts, choices, etc).

### Detect via Apocalypse API

Check `status` in session list. Yellow = idle/awaiting.

### Detect via session files (precise)

```powershell
Get-Process claude | ForEach-Object {
    $f = "$env:USERPROFILE\.claude\sessions\$($_.Id).json"
    if (Test-Path $f) {
        Get-Content $f | ConvertFrom-Json | Select-Object pid, sessionId, status, waitingFor, cwd
    }
}
```

Key fields in `~/.claude/sessions/<PID>.json`:
- `status`: `"waiting"` = stuck, `"idle"` = waiting for next message, `"busy"` = executing tool
- `waitingFor`: what it's waiting for: `"permission prompt"`, `"user input"`, `"choice selection"`
- `sessionId`: UUID for the session (maps to Apocalypse session_id)

## Kill Stuck Sessions

Before using `--resume` on a running session, kill the original process to prevent concurrent file corruption.

### Kill just the Claude Code process

```powershell
Stop-Process -Id <PID> -Force
```

### Kill process + its parent terminal (cleaner kill)

```powershell
$proc = Get-CimInstance Win32_Process -Filter "ProcessId=<PID>"
Stop-Process -Id $proc.ParentProcessId -Force -ErrorAction SilentlyContinue
Stop-Process -Id <PID> -Force
```

### Recommended remote unstick workflow

1. Detect stuck session (check `status: "waiting"` and `waitingFor`)
2. Kill the original process to prevent concurrent writes
3. Fix any corrupted JSONL lines (if concurrent writes already happened)
4. Use `ccr code --resume --print -p "y"` to continue in the background
5. Return results to user

## Respond to Stuck Session

After killing the original process, use `--resume` to continue:

```powershell
# Approve a permission prompt
cmd /c "cd /d <cwd> && ccr code --resume <session_id> --print -p ""y"""

# Answer a yes/no question
cmd /c "cd /d <cwd> && ccr code --resume <session_id> --print -p ""yes"""

# Provide a choice selection
cmd /c "cd /d <cwd> && ccr code --resume <session_id> --print -p ""option 1"""
```

**How it works:** `--resume` loads the session context, appends the provided text as user input, sends it to the API, and returns the response. The conversation file on disk gets updated, and the Apocalypse dashboard reflects the new messages.

## Fix Corrupted Conversation Files

If two processes wrote to the same `.jsonl` concurrently, the file has partial/corrupted JSON lines. Fix by stripping invalid lines:

```powershell
$lines = Get-Content "<session>.jsonl"
$good = @()
foreach ($line in $lines) {
    try {
        $null = $line | ConvertFrom-Json
        $good += $line
    } catch {
        # skip corrupted line
    }
}
$good | Set-Content "<session>.jsonl"
```

## Caveats

- `ccr code --resume --print` consumes API credits (goes through the configured CCR provider)
- Do NOT use for trivial lookups: prefer reading conversation via Apocalypse API first
- The Apocalypse API is read-only; it never modifies session data
- `--resume` creates a parallel session; the original terminal remains unchanged
- Timeout handling: set appropriate timeout in exec calls (300s+ for large sessions)
- On first use, verify Apocalypse is running
- Always kill original process before `--resume` to prevent concurrent file corruption

## Quick Reference

| Goal | Method |
|------|--------|
| List sessions | `Invoke-RestMethod http://localhost:7749/api/sessions2` |
| Read conversation | `Invoke-RestMethod http://localhost:7749/api/sessions2/<id>` |
| Ask session a question | `cmd /c "cd /d <cwd> && ccr code --resume <id> --print -p ""question"""` |
| Detect stuck sessions | `Get-Content ~/.claude/sessions/<PID>.json` |
| Kill stuck process | `Stop-Process -Id <PID> -Force` |
| Fix corrupted JSONL | filter valid JSON lines |
| Approve permission prompt | `ccr code --resume <id> --print -p ""y"""` |
| Check Apocalypse alive | `Invoke-RestMethod http://localhost:7749/` |
