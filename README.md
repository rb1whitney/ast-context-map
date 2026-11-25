# ast-context-map

Give a coding agent a structural map of a codebase (symbols, calls, dependencies) instead of raw files.

Tree-sitter AST extraction builds a relationship graph. You query the graph (definitions, usages, blast radius, lineage) and hand the agent the answer, not the files. The same graph format also covers Kubernetes, Crossplane, Terraform and Vault topology (Graphify format).

Background: [Stop Dumping Raw Code into LLMs](https://medium.com/@rb1whitney/stop-dumping-raw-code-into-llms-why-semantic-graphs-lead-to-scalable-ai-agents-707c9c3220b0).

## Quickstart

```bash
pip install -r requirements.txt

# 1. Map a directory (writes code_map.md and relationship_graph.json)
python3 scripts/code_mapper.py examples/payments-java --out-dir /tmp/map

# 2. Ask a structural question
python3 scripts/semantic_query.py --graph /tmp/map/relationship_graph.json impact PaymentRequest
```

Output of step 2:

```text
Impact of changing 'PaymentRequest':
- AuditLogger (depth 1, via PaymentRequest)
- PaymentGatewayClient (depth 1, via PaymentRequest)
- PaymentOrchestrator (depth 1, via PaymentRequest)
```

`semantic_query.py` subcommands: `find-definition`, `find-usages`, `trace-dependencies`, `impact`, `query`, `lineage`, `shortest-path`, `diff-impact`.

## Kubernetes and Vault (offline samples)

The same graph tooling checks infrastructure state. Everything below runs offline against synthetic data in `examples/`. No cluster, no Vault server, no tokens.

### Vault configuration lint

The Vault sample uses the `api_paths` YAML format (as used by [vault_controller](https://github.com/rb1whitney/vault_controller)): a top-level `api_paths` list, each item with `api_path`, an optional `api_action`, and an `api_payload`. An optional `_namespace` key scopes a file.

```bash
python3 scripts/state_graph.py lint --vault examples/vault-sample
```

The sample contains one deliberately bad item per rule and clean counterparts. Output (condensed from the JSON):

| Rule | Severity | File | Finding |
| :--- | :--- | :--- | :--- |
| `policy-read-write-mix` | repo-rule | `_acl_policies.yaml` | `payments-admin`: `secret/data/payments/*` mixes read and write |
| `mount-ttl-over-1h` | repo-rule | `_secret_engines.yaml` | `secret`: `default_lease_ttl` 7200s exceeds 1h |
| `plaintext-secret` | repo-rule | `kv/payments-api/credentials.yaml` | key `webhook_token` is not Transit-encrypted |
| `insecure-tls` | advisory | `_auth.yaml` | `auth/ldap/config`: `insecure_tls` true |
| `transit-key-exportable` | advisory | `_secret_engines.yaml` | `transit/keys/payments-key` is exportable |

The clean `payments-reader` policy and the Transit-encrypted `api_key` are not flagged. The test suite asserts this.

### Drift against a snapshot

```bash
python3 scripts/state_graph.py drift --k8s examples/k8s-sample/manifests --live-k8s examples/k8s-sample/live-k8s.json
python3 scripts/state_graph.py drift --vault examples/vault-sample --live-vault examples/vault-sample/live-vault.json
```

| Source | Missing | Drifted | Unmanaged |
| :--- | :--- | :--- | :--- |
| Kubernetes | `Ingress/payments/payments-api` | `Deployment/payments/payments-api`: `spec.replicas` 3 vs 2, image `1.4.0` vs `1.3.9` | `Deployment/payments/legacy-worker` |
| Vault | mount `transit` | policy `payments-admin`: live lacks `delete` | none |

### Topology graph from a snapshot

```bash
python3 scripts/k8s_graphify_extract.py --live-k8s examples/k8s-sample/live-k8s.json \
  --manifests examples/k8s-sample/manifests --out /tmp/k8s-graph.json
```

Prints `Generated Kubernetes knowledge graph: 3 nodes, 1 links.` The graph is Graphify `node_link` JSON.

## Graph of graphs (many repositories)

`scripts/graph_of_graphs.py` builds a small, drillable index over many per-repository graphs (Graphify `node_link` JSON). Levels are repositories, then communities, then symbols. Every view takes `--limit` and ends with the command that goes one level deeper.

```bash
python3 scripts/graph_of_graphs.py build --graphs-dir graphs --repos gson guava dagger --clones clones --out gog.json
python3 scripts/graph_of_graphs.py overview gog.json --limit 5
python3 scripts/graph_of_graphs.py drill gog.json gson --limit 4
python3 scripts/graph_of_graphs.py drill gog.json gson 3
```

Cross-repository links come only from dependencies declared in package manifests (`scripts/manifest_deps.py`: Maven, Gradle, Bazel, Go, PyPI, npm, Cargo, CMake; matches only count within one ecosystem). Shared standard-library names are not links: merging graphs by node id connects repositories because they all import `os` or `java.util`. On seven real repositories (164,385 symbols) the index is 138 KB. See [research/graph-of-graphs](research/graph-of-graphs/FINDINGS.md) for the measurements and their limits.

## Scoring answers

`scripts/eval_score.py` scores a file-list answer (`FILE: <path>` lines) against a reference set: precision, recall, F1, and the matched, missing and extra files. Leading `./`, an absolute root, or an extra repository folder are normalised, since those are format slips and not wrong files.

```bash
python3 scripts/eval_score.py answer.txt --reference reference.json --repo gson
python3 scripts/eval_score.py batch --questions questions.json --results runs/ --clones clones --csv runs.csv
```

## When to use the graph and when to search

- **Named symbol, "who uses it":** search first (`git grep -w`). It was cheaper and at least as complete in trials.
- **Relations or a flow across hops:** query the graph for candidates, then read the files it names. Graph output alone missed about 40 percent of the right files.
- **Many repositories:** use `graph_of_graphs.py`, not merged graphs, and take cross-repo links from manifests.
- **Claiming a benefit:** score against an independent reference and report cost, turns, denied tool calls and whether the graph was used.

Details and numbers: [references/graph-vs-search.md](references/graph-vs-search.md).

## Research: graphs of graphs

Experiments on real repositories, with the caveats written down: [research/graph-of-graphs/FINDINGS.md](research/graph-of-graphs/FINDINGS.md).

- Merging per-repo graphs is concatenation: 0 direct cross-repo edges, and the bridges are mostly standard-library names.
- Real dependency edges can be extracted from package manifests, but they are sparse (7 among 20 repositories).
- A budgeted graph answer is far smaller than reading files, but its coverage is incomplete.
- In measured trials with real model runs (168 saved Claude runs, $2.09 in total, all on claude-haiku-5-5, plus 45 Antigravity runs), plain search was cheaper than graph tools on "who uses X" questions, and its accuracy ranking depended on the reference (graded against compiled dependencies on gson, graph answers scored higher). On two-step flow questions in a larger repository, a graph rebuilt with annotation types and static imports came within 0.06 F1 of search but cost the same, because agents walked it one hop at a time (33 queries, 36 turns). A single `closure` call with a coverage footer replaced those queries: 2 turns, one third of the cost and 12 percent of the input tokens, at ten points lower F1 (0.84 against 0.94); the agents copied the list and did not verify. Whether agents use a graph at all depended on the nudge: with no mention, 0 of 9 Claude runs and 0 of 9 Antigravity runs queried it; Graphify's installed `CLAUDE.md` section plus hook made it 9 of 9 on Claude, and a PreToolUse gate did on Antigravity. Answer quality did not change. These are small trials on one small model per harness.

## Closure query with a coverage footer

`semantic_query.py closure <Class> --depth 2 --limit 30` returns, in one call, the files a class's file depends on within N hops, nearest and most-linked first, with the hop, the classes involved and why. It walks files, so nested classes are followed with their file. Answers from `closure`, `find-usages` and `impact` end with a coverage note: how many files or classes the answer covers, where the graph is known to be blind (reflection call sites, framework-wired classes, parse errors), how many results were cut off and how to see them, and a `git grep -lw` command to verify before changing shared code.

```bash
python3 scripts/code_mapper.py <repo> --out-dir graph
python3 scripts/semantic_query.py --graph graph/relationship_graph.json closure MissingBindingValidator --depth 2 --limit 30
```

On dagger the file list it prints, scored against a javac-style reference with no agent involved, has recall 0.92, 0.73 and 0.83 on three flow questions at full depth, with precision 0.92, 0.68 and 0.83 (Finding 15).

## Safety rules

- Live Kubernetes extraction never lists `secrets`, `configmaps` or `tokenreviews`.
- A `Secret` object that arrives in an offline snapshot becomes a node (existence only). Its data and any `env` literals are stripped. A test asserts the values do not appear in the output.
- Output is written atomically at mode `0600`. The write is refused if a secret-shaped value survives (`SecretLeakError`).
- `*prod*` kubectl contexts are refused unless `--allow-prod-read` is passed.
- Vault lint and drift are read-only. With `--live-vault` the tool needs no Vault token. It never decrypts Transit ciphertext. Live Vault mode (no snapshot) calls the `vault` CLI with your own token for `list` and `read` only.

## What is in the box

| Path | Purpose |
| :--- | :--- |
| `scripts/code_mapper.py`, `graph_builder.py` | Tree-sitter extraction to `code_map.md` and a relationship graph |
| `scripts/semantic_query.py` | Graph queries: definition, usages, dependencies, impact, lineage, diff-impact |
| `scripts/auto_context.py` | Rank files for a task description within a token budget |
| `scripts/well_architected_audit.py`, `rules/`, `resources/` | ast-grep rule packs and a six-pillar structural audit |
| `scripts/state_graph.py` | Infrastructure-as-code vs live Kubernetes/Vault drift graph |
| `scripts/k8s_graphify_extract.py`, `k8s_catalog.py` | Secret-redacted Kubernetes/Crossplane/Terraform topology graph |
| `scripts/graph_registry.py` | Publish a graph per commit and query it without a checkout |
| `SKILL.md`, `skills/graphify/SKILL.md` | Agent Skill docs for the two entry points |

## Measured

Reproduce with `python3 benchmarks/token_compare.py`. The sample is a small synthetic Java service (5 classes) in `examples/payments-java`. "~tokens" is bytes / 4, a rough proxy, not a tokenizer.

| Scenario | Raw bytes | AST bytes | Saved |
| :--- | ---: | ---: | ---: |
| Whole repo: raw source vs `code_map.md` | 9668 | 3678 | 62.0% |
| Blast radius of `PaymentRequest`: files mentioning it vs `impact` query | 7914 | 186 | 97.6% |

Read this carefully: a whole-repo map saves a moderate amount on small, comment-light code. The large savings come from targeted queries that return only the answer. Results on a real repository depend on its size and density; measure on yours.

## Limitations

- Tree-sitter is syntactic. Call edges are resolved from names and declared types, not by a compiler. Reflection, dynamic dispatch and generated code are not captured.
- The rule-pack tests and `local_extract.py` need the `ast-grep` binary (installed by `requirements.txt` as `ast-grep-cli`).
- Dependencies are pinned to `tree-sitter==0.20.1` and `tree-sitter-languages==1.10.2`. CI runs Python 3.10 and 3.11.
- The benchmark is one small synthetic sample, not a statistical study.
- The Kubernetes and Vault extractors need cluster access. They are read-only, never list secrets or configmaps, strip sensitive values, and refuse `*prod*` contexts unless `--allow-prod-read` is set. Use a non-production context.

## Tests

```bash
python3 -m pytest -q
```

## Provenance

This repository started as an export of [Agentic-Project-Factory](https://github.com/rb1whitney/Agentic-Project-Factory) and is now maintained directly. Core scripts in `scripts/` are synced from the hub by hand when they change.

License: Apache-2.0.
