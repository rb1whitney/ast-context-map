#!/usr/bin/env python3
"""Antigravity (agy) PreToolUse hook: make the first search wait for one graph query. Generic, no Graphify dependency.

Reads the hook payload on stdin and answers on stdout (`decision` is required by agy). Behaviour:
  * a graph command (matches GRAPH_GATE_CMD_RE) records that the graph was used and is allowed;
  * a search-like tool call (grep_search, find_by_name, or run_command running grep/rg/find) is denied with a reason
that
    names the graph command, at most GRAPH_GATE_MAX_DENIES times (default 1) so a broken graph command cannot
deadlock the
    agent, and only while the graph file exists;
  * everything else is allowed.
Every decision is appended to GRAPH_GATE_LOG when set. Wire it in `.agents/hooks.json`; see hooks/agy/README.md.

Environment (all optional):
  GRAPH_GATE_FILE         graph file whose presence enables the gate; relative paths resolve against the workspace
                          in the hook payload (default graphify-out/graph.json)
  GRAPH_GATE_CMD_RE       regex for a graph command (default `graphify|semantic_query\\.py|auto_context\\.py`)
  GRAPH_GATE_HINT         command to suggest in the denial (default `graphify query "<question>"`)
  GRAPH_GATE_NOTE         extra sentence appended to the denial (for example a verify-before-answering rule)
  GRAPH_GATE_MAX_DENIES   denials allowed per state file (default 1)
  GRAPH_GATE_STATE        state file (default: a private per-user temp directory, one file per workspace)
  GRAPH_GATE_LOG          append-only decision log
"""

import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import time
from pathlib import Path

SEARCH_TOOLS = {"grep_search", "find_by_name"}
SEARCH_CMD = re.compile(r"(^|[\s;&|(])(grep|egrep|fgrep|rg|ag|ack|find|git\s+grep)\s")


def _default_state(workspace: Path) -> Path:
    """Outside the workspace, where the repository cannot plant a link, in a directory only this user can open."""
    folder = Path(tempfile.gettempdir()) / f"graph_gate-{os.getuid()}"
    folder.mkdir(mode=0o700, exist_ok=True)
    info = os.lstat(folder)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise OSError(f"refusing {folder}")
    folder.chmod(0o700)
    return folder / hashlib.sha256(str(workspace.resolve()).encode()).hexdigest()[:16]


def append_log(path: str, line: str) -> None:
    """Append without following a link someone planted at the log path; a log failure never affects the hook."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "a") as fh:
            if os.fstat(fd).st_uid == os.getuid():  # not a file someone else created for us to fill
                fh.write(line)
    except OSError:
        pass


def decide(payload: dict, env=os.environ) -> tuple[dict, str]:
    """Return (hook output, short label for the log)."""
    call = payload.get("toolCall") or {}
    name, args = call.get("name", ""), call.get("args") or {}
    workspace = Path((payload.get("workspacePaths") or [os.getcwd()])[0])
    graph = Path(env.get("GRAPH_GATE_FILE", "graphify-out/graph.json"))
    if not graph.is_absolute():
        graph = workspace / graph  # hooks may run outside the workspace, so resolve against the payload's workspace
    state = Path(env["GRAPH_GATE_STATE"]) if env.get("GRAPH_GATE_STATE") else _default_state(workspace)
    cmd = str(args.get("CommandLine", "")) if name == "run_command" else ""
    if name == "run_command" and re.search(
        env.get("GRAPH_GATE_CMD_RE", r"graphify|semantic_query\.py|auto_context\.py"), cmd
    ):
        state.write_text(json.dumps({"graph_used": True, "denies": _load(state).get("denies", 0)}))
        return {"decision": "allow"}, "graph-command"
    search_like = name in SEARCH_TOOLS or (name == "run_command" and SEARCH_CMD.search(cmd))
    if not search_like or not graph.exists():
        return {"decision": "allow"}, "not-gated"
    saved = _load(state)
    if saved.get("graph_used"):
        return {"decision": "allow"}, "graph-already-used"
    limit = int(env.get("GRAPH_GATE_MAX_DENIES", "1"))
    if saved.get("denies", 0) >= limit:
        return {"decision": "allow"}, "deny-limit-reached"
    state.write_text(json.dumps({"graph_used": False, "denies": saved.get("denies", 0) + 1}))
    hint = env.get("GRAPH_GATE_HINT", 'graphify query "<question>"')
    reason = (
        f"A code graph exists at {graph}. Run `{hint}` first, then search or read the files it names. "
        "Search is allowed again right after that one graph command."
    )
    if env.get("GRAPH_GATE_NOTE"):
        reason += " " + env["GRAPH_GATE_NOTE"]
    return {"decision": "deny", "reason": reason}, "denied"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}))  # never block on a payload this hook cannot read
        return
    try:
        out, label = decide(payload)
    except Exception as exc:  # a hook must never break the agent
        out, label = {"decision": "allow"}, f"error:{type(exc).__name__}"
    log = os.environ.get("GRAPH_GATE_LOG")
    if log:
        tool = (payload.get("toolCall") or {}).get("name", "")
        append_log(log, f"{time.strftime('%H:%M:%S')}\t{tool}\t{label}\t{out['decision']}\n")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
