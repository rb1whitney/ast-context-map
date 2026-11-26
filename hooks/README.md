# Noise gate hook

`noise_gate.py` is a PreToolUse hook for Claude Code and Antigravity (`agy`) that sends an agent to a code map only when a search is
noisy. It counts the files a search pattern matches (`git grep -l`), allows the search if there are 100 or fewer, and otherwise denies
it once with a reason that names the map commands. After one map command, or one denial, searches proceed. It fails open: on any error
or unreadable input the call is allowed, and each decision is appended to `NOISE_LOG` when set. Everything has a default; tune with the
environment variables in the file's docstring (`NOISE_MIN_HITS`, `NOISE_HINT`, `NOISE_NOTE`, `NOISE_CMD_RE`, `NOISE_MAX_DENIES`).
What was measured: Finding 20 in `research/graph-of-graphs/FINDINGS.md` (silent on quiet searches on both harnesses; it did not lower
cost by itself).

## Claude Code (`.claude/settings.json`)

```json
{"hooks": {"PreToolUse": [
  {"matcher": "Grep|Bash",
   "hooks": [{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/hooks/noise_gate.py || true"}]}
]}}
```

## Antigravity (`.agents/hooks.json`)

Commands run from `<workspace>/.agents/`, and a hook that fails blocks the tool call, so use a `../` path and fall back to allow:

```json
{"hooks": {"PreToolUse": [
  {"matcher": "run_command|grep_search|find_by_name",
   "hooks": [{"type": "command", "timeout": 20,
              "command": "python3 ../hooks/noise_gate.py || echo '{\"decision\":\"allow\"}'"}]}
]}}
```
