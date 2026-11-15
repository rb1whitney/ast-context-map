# Graph of graphs: experiments and findings

Experiments on what happens when you combine per-repository code graphs, and on whether graph-assisted agents beat plain search. Start with [FINDINGS.md](FINDINGS.md): every number there comes from a script in `experiments/`, and it lists what is safe to claim and what is not.

## Layout

| Path | Contents |
| :--- | :--- |
| `FINDINGS.md` | Results, caveats, limits |
| `experiments/merge_stats.py` | What `graphify merge-graphs` produces (size, cross-repo edges, bridge nodes) |
| `experiments/manifest_deps.py` | Cross-repo dependency edges from package manifests |
| `experiments/simulate_cost.py` | Simulated context cost of a search agent against a graph agent (no model) |
| `experiments/trial/trial.py` | Measured agent trial with real model runs and a dollar cap per run |
| `corpus/` | Pinned commits, graph commits, extraction timings, `clone_corpus.sh` |
| `data/` | Per-run results of the first trial (no local paths) |

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

Each run has a hard dollar cap (`--cap`) and the whole trial stops at `--total-cap`. The first trial of 36 runs on the smallest model cost about $0.18.

## Caveats

- Graph sizes and extraction times come from the external Graphify, not from this repository's mapper.
- The agent trial used one small model, three repeats and two repositories. Treat results as direction, not significance.
- Raw run files are not published; `data/trial-before-runs.csv` has the scored runs.
