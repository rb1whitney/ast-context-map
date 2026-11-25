# Graph of graphs: experiments and findings

Experiments on what happens when you combine per-repository code graphs, and on whether graph-assisted agents beat plain search. Start with [FINDINGS.md](FINDINGS.md): every number there comes from a script in `experiments/`, and it lists what is safe to claim and what is not.

## Layout

| Path | Contents |
| :--- | :--- |
| `FINDINGS.md` | Nineteen findings with a status table, runs and cost, answer keys, claim lists, limits |
| `experiments/merge_stats.py` | What `graphify merge-graphs` produces (size, cross-repo edges, bridge nodes) |
| `experiments/manifest_deps.py` | Cross-repo dependency edges from package manifests |
| `experiments/simulate_cost.py` | Simulated context cost of a search agent against a graph agent (no model) |
| `experiments/graph_ceiling.py` | The recall ceiling of a mapper graph against an answer key |
| `experiments/java_reference.py` | A name-resolving Java answer key (imports, packages, static imports) |
| `experiments/jdeps_reference.py`, `experiments/jdeps/stubs/` | A compiler-derived key for gson, and the stubs needed to compile it |
| `experiments/trial/nudge_trial.py` | The Claude Code nudge test (Finding 19): five conditions built from Graphify's real installer, hook-firing log, calibration scoring |
| `experiments/trial/agy_nudge_trial.py` | The same test for Antigravity (`agy`): installer rule, a PreToolUse gate (`../../hooks/agy/graph_gate.py`), gaps rule |
| `experiments/trial/trial.py` | Measured agent trial: conditions A to D, a dollar cap per run, tool-call logging |
| `experiments/trial/questions*.json` | The questions and answer keys (`questions_flow_v2.json` is the name-resolving key) |
| `corpus/` | Pinned commits, graph commits, extraction timings, `clone_corpus.sh` |
| `data/` | Per-run results and score tables for every trial (no local paths) |

## Reproduce

Run everything from this directory. The corpus is not included.

```bash
# 1. Fetch repositories at the pinned commits (small ones first)
corpus/clone_corpus.sh gson yapf brotli zx magika langextract libphonenumber googletest ax

# 2. Build graphs with the external Graphify CLI (version 0.9.86 was used), local AST only
for r in gson yapf brotli zx magika langextract libphonenumber googletest ax; do
  graphify extract "$r" --code-only
  mkdir -p "_graphs/$r" && cp -r "$r/graphify-out" "_graphs/$r/"
done

# 3. Experiments (read-only)
python3 experiments/merge_stats.py --out-dir /tmp/merge-run
python3 experiments/manifest_deps.py > edges.json
python3 experiments/simulate_cost.py gson yapf brotli zx magika langextract
```

The measured trial calls a model. Build this repository's own graphs first, then read the header of `experiments/trial/trial.py`:

```bash
python3 ../../scripts/code_mapper.py gson --force --out-dir experiments/trial/graphs/gson
python3 experiments/trial/trial.py run --pilot --dry-run   # prints the commands without running them
```

Each run has a hard dollar cap (`--cap`) and the whole trial stops at `--total-cap`. Every trial used the smallest model; all 168 saved Claude runs cost $2.09 in total (plus 45 Antigravity runs, reported in tokens). The full reproduce list, including the answer-key scripts and the closure trial, is at the end of [FINDINGS.md](FINDINGS.md).

## Caveats

- Findings 1 to 6 use graphs from the external Graphify; the agent trials use this repository's mapper.
- The agent trial used one small model, three repeats and two repositories. Treat results as direction, not significance.
- Raw run files are not published because they contain local paths; the `data/` folder has one scored row per run for every trial.
