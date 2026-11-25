# agy PreToolUse hook: first search waits for one graph query

`graph_gate.py` is a generic Antigravity (`agy`) hook. When a graph file exists in the workspace, the first search-like tool
call (`grep_search`, `find_by_name`, or `run_command` running `grep`, `rg`, `find`) is denied once with a reason that names the
graph command. After one graph command runs, search is allowed again. It does not depend on Graphify: set the environment
variables below to use any graph tool.

Wire it in `<workspace>/.agents/hooks.json`:

```json
{"hooks": {"PreToolUse": [{"matcher": "run_command|grep_search|find_by_name",
  "hooks": [{"type": "command", "command": "GRAPH_GATE_LOG=/tmp/gate.log python3 /path/to/graph_gate.py", "timeout": 10}]}]}}
```

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `GRAPH_GATE_FILE` | `graphify-out/graph.json` | Graph whose presence enables the gate; relative paths resolve against the workspace in the hook payload |
| `GRAPH_GATE_CMD_RE` | `graphify\|semantic_query\.py\|auto_context\.py` | Commands that count as using the graph |
| `GRAPH_GATE_HINT` | `graphify query "<question>"` | Command named in the denial |
| `GRAPH_GATE_NOTE` | empty | Extra sentence appended to the denial, for example a verify-before-answering rule |
| `GRAPH_GATE_MAX_DENIES` | `1` | Denials allowed per state file, so a failing graph command cannot deadlock the agent |
| `GRAPH_GATE_STATE` | `<workspace>/.graph_gate_state` | State file |
| `GRAPH_GATE_LOG` | unset | Append-only decision log |

## What is verified

- Unit tests (`tests/test_graph_gate.py`): deny, allow after a graph command, deny limit, no graph file, custom hint and regex,
  unreadable payload, logging, workspace-relative graph path.
- One live `agy -p` run (Antigravity CLI 1.5.17, `gemini-3.8-flash-low`) in a folder not on the trusted list: the hook loaded and
  fired, denied the agent's first `rg`, the agent then ran `graphify query`, and later searches were allowed. One run is a smoke
  test, not a result about behavior.

## What is not verified

- Whether the gate improves answers. The planned test is in `research/graph-of-graphs/FINDINGS.md`, Finding 19.
- It can be bypassed: in the live run the agent later searched with inline `python3 -c` scripts, which the gate does not treat
  as search.
- A `PreInvocation` hook that injects context did not log any firing in an earlier run; the cause is unknown.
- Hooks in `~/.gemini/config/hooks.json` (global) were not tested.

See also `hooks/noise_gate.py`, which gates only noisy searches (it counts the files a pattern matches and denies above a threshold) and serves both Claude Code and Antigravity. It is built for Finding 20 and has not been run on a model yet.
