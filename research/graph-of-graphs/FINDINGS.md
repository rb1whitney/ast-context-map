# Findings: graphs of graphs across 20 real repositories

Evidence for an article on combining ast-grep, the semantic code graph, and Graphify into a graph of graphs. Every number below was produced by a script in `experiments/` or read from `results.tsv`.

## Thesis

Merging per-repo code graphs does not produce a graph of graphs. It produces a larger graph that is too big to use as agent context and whose cross-repo links are mostly shared standard-library names. A useful graph of graphs needs explicit dependency edges, a hierarchy (repos, then communities, then symbols), and a node budget that tells the reader how to go deeper. The graph answers a structural question in a fraction of the tokens that reading files costs, but it is incomplete, so the deeper step is a targeted search rather than more graph.

## Corpus and method

- 20 clones of public repositories (19 from Google, plus Kubernetes) (not included; fetch them at the pinned commits with `corpus/clone_corpus.sh`). Commit of each clone: `corpus/corpus-shas.tsv`.
- 18 graphs built with `graphify extract --code-only` (Graphify 0.9.86, local AST, no API key). Kubernetes and Filament timed out at 3000 seconds and have no graph.
- Each graph's `built_at_commit` equals its clone's HEAD for all 18 (`corpus/corpus-graph-commits.tsv`), so the commits are authoritative.
- Graph sizes and extraction times come from `corpus/results.tsv`; counts of nodes and edges come from the extraction logs.

## Finding 1: raw graphs are too big to hand to an agent

| Repo | Nodes | Edges | Graph file | Extraction time |
| :--- | ---: | ---: | ---: | ---: |
| gson | 5,131 | 17,738 | 9.1 MB | 56 s |
| guava | 80,690 | 243,787 | 128.6 MB | 584 s |
| adk-python | 73,357 | 194,459 | 94.8 MB | 1,001 s |
| gvisor | 49,929 | 280,422 | 91.0 MB | 1,527 s |

Other graph sizes: or-tools 65.8 MB, flatbuffers 38.1 MB, dagger 38.4 MB, libphonenumber 9.2 MB, googletest 7.0 MB, magika 3.1 MB. A 128 MB graph is not context; it needs budgeting before an agent can use it.

## Finding 2: `graphify merge-graphs` is concatenation

Experiment: `experiments/merge_stats.py`, nine small repos (gson, yapf, brotli, zx, ax, magika, langextract, libphonenumber, googletest).

| Measure | Value |
| :--- | ---: |
| Input nodes / edges (sum) | 34,271 / 78,954 |
| Merged nodes / edges | 34,005 / 78,954 |
| Merged file size | 42.9 MB |
| Merge time | about 5 s |
| Edges within one repo | 72,911 |
| Edges directly between two repos | 0 |
| Edges touching a shared node | 6,043 |

Edges equal the sum of the inputs and 266 nodes were merged by id. No edge connects a node of one repo to a node of another. The only cross-repo connectivity runs through nodes that the merge unified.

## Finding 3: the bridges are standard-library names

179 shared nodes have neighbors in two or more repos. They link 23 of the 36 possible repo pairs.

- Highest degree: `os`, `sys`, `collections`, `io`, `tempfile`, `subprocess`, `re`, `pathlib` (Python); `stdint`, `errno`, `string` (C); `IOException`, `ArrayList`, `List` (Java).
- A classifier using Python's `sys.stdlib_module_names` plus small C and Java stoplists labels 74 of the 179 as standard library or generic.
- I read the top 40 of the remaining 104 by degree: all were standard library (Go `fmt`, `testing`, `os`; C++ `cstdint`, `iostream`), test helpers (`assertThat`, `assertEquals`), or ubiquitous packages (`pytest`, `requests`). The last 64 are unchecked.

Merging links repos because they all import the standard library, not because one depends on another.

## Finding 4: real dependency edges are sparse and must be extracted explicitly

Experiment: `experiments/manifest_deps.py`, all 20 clones, 380 ordered pairs. An edge means a repo declares a dependency matching an identity another repo owns, within the same ecosystem.

Result: 7 edges, each checked against its evidence line.

| From | To | Where |
| :--- | :--- | :--- |
| dagger | guava | `MODULE.bazel` |
| gson | guava | `gson/pom.xml` (test scope) |
| libphonenumber | guava | `metadata/pom.xml` |
| flatbuffers | googletest | `benchmarks/CMakeLists.txt` |
| gvisor | googletest | `MODULE.bazel` |
| or-tools | googletest | `MODULE.bazel` |
| gvisor | kubernetes | `go.mod` (`k8s.io/api`) |

How it got there:

1. First run: 1 edge. Maven poms with `xsi:schemaLocation` failed to parse after namespace stripping, and the error was swallowed.
2. Adding Bazel, Gradle and CMake parsing: 8 edges, one false. The Rust `googletest` crate in `comprehensive-rust` is a different project from the C++ repo.
3. Requiring the same ecosystem on both sides: 7 edges.

Rejected on purpose: a PyPI `kubernetes` client dependency in `adk-python` (not the Kubernetes repo) and a Gradle file under `tests_data/` in `magika` (a fixture).

Recall: 7 of the 10 edges I know of. Known misses: `filament` and `libphonenumber` to `googletest` (CMake link lines), `flatbuffers` to `gson` (a Gradle version-catalog alias). This is not an exhaustive ground truth. Two of the edges are test or benchmark scope only; add a scope tag before calling them runtime dependencies.

The corpus is mostly independent repositories. Seven edges across twenty repos is the honest density.

## Finding 5: a hierarchy is far smaller (sizing only)

For the nine merged repos, minimal summaries of my own:

| Level | Entries | Size |
| :--- | ---: | ---: |
| Repos | 9 | 497 bytes |
| Communities | 1,481 | 183,701 bytes |
| Union graph | 34,005 nodes | 42,915,678 bytes |

The community level is about 234 times smaller than the union. These are sizes of summaries with a few fields. Whether a hierarchy answers questions well is not tested.

## Finding 6: simulated agent cost, graph versus reading files

Experiment: `experiments/simulate_cost.py`. No model is used. For each repo, the 10 best-connected non-test classes become questions of the form "what depends on X and where is it defined?", with the class name as the obvious keyword. Tokens are characters divided by 4, a rough proxy.

Median tokens per question at a 15-node budget:

| Repo | Reads whole files | Reads windows | Graph answer |
| :--- | ---: | ---: | ---: |
| gson | 40,026 | 3,700 | 990 |
| yapf | 15,612 | 1,690 | 524 |
| brotli | 24,791 | 2,707 | 510 |
| zx | 10,252 | 1,714 | 348 |
| magika | 18,754 | 2,204 | 493 |
| langextract | 30,844 | 2,459 | 665 |

The baseline agent runs `git grep -w` and reads the top 5 files (whole files, or one 60-line window around the first match in the top 3 files). The graph agent reads the symbol's inbound neighbors plus a 60-line window at the definition. The graph answer is 29 to 49 times smaller than whole-file reads and 3.2 to 5.3 times smaller than windowed reads.

Budget against coverage (coverage is the share of files containing the symbol that the graph answer names; precision was 1.00 everywhere):

| Repo | Budget 15 | Budget 50 | Budget 200 |
| :--- | :--- | :--- | :--- |
| gson tokens | 990 | 1,929 | 4,930 |
| gson coverage | 0.09 | 0.50 | 0.80 |
| yapf, brotli, magika coverage | 0.46, 0.36, 0.40 | unchanged | unchanged |

On gson, a 200-node answer costs more than the windowed baseline. On the other three repos coverage plateaus around 0.4, because the graphs hold no further inbound edges: the graph misses roughly 55 to 65 percent of files that mention a symbol. Precision of 1.00 is partly structural, since the edges come from references.

## Finding 7: measured agent trial, "before" (direct-usage questions)

Experiment: `experiments/trial/trial.py`, 36 real runs of the smallest model (haiku), each a fresh agent session with a hard per-run dollar cap. Two repos (gson, yapf), 3 questions each, 3 repeats, 2 conditions. Question: "which non-test source files use / depend on `<symbol>`?" with the symbol named. Scored by precision, recall and F1 against `git grep -w`. Condition A has Read, Grep and Glob. Condition B adds a prebuilt graph from this repository's own mapper, queried through the then-current `semantic_query.py`, which is uncapped and returns class and method names rather than files. Stored: `data/trial-before-runs.csv` (one row per run) and `data/trial-before-scores.txt`. The raw run files are not published because they contain local paths.

| Condition | Repo | Runs | Cost per run | Turns | Input tokens | Precision | Recall | F1 median (range) |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| A search | gson | 9 | $0.004 | 2 | 23,594 | 0.95 | 1.00 | 0.97 (0.88-1.00) |
| A search | yapf | 9 | $0.003 | 2 | 22,119 | 1.00 | 1.00 | 1.00 (0.71-1.00) |
| B graph | gson | 9 | $0.006 | 5 | 65,610 | 0.94 | 0.83 | 0.88 (0.85-0.92) |
| B graph | yapf | 9 | $0.005 | 5 | 60,762 | 1.00 | 1.00 | 1.00 (0.77-1.00) |

All 36 runs cost $0.181 in total (A $0.081, B $0.100). Input tokens include cached tokens.

Reading:

- Plain search was cheaper and at least as accurate on this question type. The graph condition used about 2.5 times the turns and 2.7 to 2.8 times the input tokens on both repos.
- On gson the graph condition lost recall (0.83 against 1.00), consistent with the coverage ceiling in Finding 6. On yapf the median F1 was equal.
- The ranges overlap, the sample is small, and the cost difference is under a cent per run, so this is a direction, not a significance test.
- Cause, from inspecting the tool rather than the runs: `find-usages JsonElement` prints 209 lines (14 KB) with no cap, and the agent has to convert class names to files. The test measured the tool as shipped, not graphs in general.
- The question names the symbol, which is the case search handles best. Multi-hop, no-keyword and large-repo questions were not tested here.
- One scoring note: an agent once answered with an extra leading repo folder (`yapf/yapf/pytree/...`). The scorer now accepts a repo-name prefix for both conditions, since the files were right.

## Finding 8: measured agent trial on multi-hop flow questions (dagger)

Experiment: `experiments/trial/trial.py` with `questions_flow.json`, 18 real runs of the same small model, 3 repeats, total cost $0.230. Repository: dagger (2,089 source files, 722 main-source Java files). Three entry classes in different modules. Question: "list the main-source files that take part in what the class does: the classes it uses, and the classes those use (two steps), excluding tests and its own file." The reference (26, 32 and 26 files) is a text-based closure with no graph: identifier references among uniquely named main-source classes, comments stripped, depth 2. Condition A has Read, Grep and Glob. Condition B adds a prebuilt graph from this repository's own mapper, queried with `auto_context.py --top 40` and `semantic_query.py`. Stored: `data/trial-flow-runs.csv` (one row per run) and `data/trial-flow-scores.txt`.

| Entry class | Reference files | Cond | Cost per run | Turns | Input tokens | Precision | Recall | F1 median (range) |
| :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| MissingBindingValidator | 26 | A search | $0.015 | 12 | 253,264 | 0.53 | 0.62 | 0.57 (0.56-0.59) |
| MissingBindingValidator | 26 | B graph | $0.009 | 9 | 125,825 | 0.47 | 0.54 | 0.50 (0.27-0.56) |
| HiltViewModelFactory | 32 | A search | $0.009 | 9 | 125,218 | 0.92 | 0.69 | 0.79 (0.73-0.83) |
| HiltViewModelFactory | 32 | B graph | $0.012 | 19 | 206,585 | 0.92 | 0.38 | 0.53 (0.50-0.81) |
| ActivityRetainedComponentManager | 26 | A search | $0.014 | 26 | 198,816 | 0.88 | 0.77 | 0.83 (0.80-0.84) |
| ActivityRetainedComponentManager | 26 | B graph | $0.010 | 15 | 159,050 | 0.92 | 0.46 | 0.62 (0.62-0.74) |
| All three, pooled | | A search | $0.014 | 20 | 201,368 | 0.88 | 0.69 | 0.79 (0.56-0.84) |
| All three, pooled | | B graph | $0.011 | 15 | 163,877 | 0.92 | 0.46 | 0.56 (0.27-0.81) |

Reading:

- Quality did not improve with the graph. Recall and median F1 were lower for B on all three questions, and pooled F1 was 0.56 against 0.79.
- Cost was mixed. B was cheaper on two questions (about 30 to 40 percent on the first) and more expensive on `HiltViewModelFactory` (19 turns against 9). Pooled, B used about 20 percent fewer turns and input tokens, a difference of about a third of a cent per run.
- The hypothesis that a graph wins where search has no obvious keyword is not supported by this tool. A likely cause, not tested here: `auto_context` returns a ranked list of 40 files by personalised PageRank, not the two-step closure the question asks for. B's precision was similar or higher and its recall lower, which fits an agent that stops after a partial list.
- Plain search itself reached only 0.57 to 0.83 F1, and A's precision of 0.53 on the first question suggests the agent and the approximate reference disagree about what "takes part" means. These questions are hard and the reference is imperfect.
- Three repeats per cell. Ranges overlap on two of the three questions, so read this as direction, not significance.

## Related work

I read abstracts and listings only, not the full papers or code, and did not search for published comparisons of graph-assisted agents against plain search.

- **LogicLens** (arXiv [2601.10773](https://arxiv.org/abs/2601.10773), January 2026): a semantic graph across repositories that combines structural analysis (dependencies, inheritance, invocations, within and across repositories) with an LLM-built layer of domain entities and workflows, queried in natural language. This work differs in two ways: no LLM is used to build the graphs, and cross-repository links come only from declared package-manifest dependencies. The two have not been compared.
- **codebadger** (arXiv [2603.24837](https://arxiv.org/abs/2603.24837), ICSE 2026 workshop): an MCP server over Joern's code property graph that gives an agent bounded tools (summary, taint sources, program slice) rather than the graph. This is the same direction as the budgeted drill-down here; it has not been evaluated in this work.
- **Community code-graph servers** such as [optave codegraph](https://github.com/optave/ops-codegraph-tool/wiki), [colbymchenry codegraph](https://cdn.jsdelivr.net/npm/@colbymchenry/codegraph@1.1.1/README.md) and [CodeCompass](https://pypi.org/project/codecompass-mcp/) expose blast-radius and impact tools over MCP. They are independent projects, not GitHub products. Tree-sitter graph tools for agents are therefore not novel; the contribution here is the measurements and their limits.

## Prior art in this repository

`graph_registry.py` routes a question to the right repo's graph. On 18 repos and 20 user-written questions: 11 confident and correct, 1 confident and wrong, 8 ambiguous. This was not a held-out test and its thresholds are uncalibrated (see `scripts/graph_registry.py`).

## What is safe to claim

- Union graphs of real repositories reach tens to hundreds of megabytes.
- `merge-graphs` concatenates; it produced no direct cross-repo edge, and its bridges are mostly standard-library names.
- Explicit dependency extraction from manifests finds real edges but needs per-ecosystem parsing and care with name collisions between ecosystems.
- For structural questions on the sampled repos, a budgeted graph answer is several times smaller than reading files and tens of times smaller than reading whole files, at the cost of coverage.
- With an uncapped, symbol-level tool, an agent using the graph spent more turns and tokens than plain search on "who uses X" questions, with equal or lower accuracy (Finding 7).
- With a ranked-file tool on two-step flow questions in dagger, graph-assisted agents were about 20 percent cheaper on average but found fewer of the right files (recall 0.46 against 0.69; Finding 8).

## What not to claim

- That the graph replaces search. Coverage plateaus near 0.4 on three of four repos, and in the trial plain search was cheaper on direct-usage questions.
- That graphs lose in general. Findings 7 and 8 tested two tool shapes on two question types with one small model.
- That graphs win on multi-hop questions. Finding 8 did not support that with the tool tested.
- That a hierarchy answers questions well. Only its size was measured.
- Absolute token or dollar figures. The token count is characters divided by 4, and the baseline agent is a simulated policy, not measured agent traces.
- Results for the repository's own mapper. All graphs here come from the external Graphify.
- That the 7 dependency edges are complete or all runtime dependencies.

## Limits of the evidence

- The question set is hub classes, which biases toward well-connected code.
- The reference set for coverage (files containing the word) includes comments, documentation and strings.
- Twenty repos, mostly Google and mostly independent; results may differ elsewhere.
- Nine repos were merged, not all eighteen; the merge comparison is not yet like-for-like with the dependency edges, which involve larger graphs.

## Reproduce

All commands run from `research/graph-of-graphs` after fetching the corpus (see README), and are read-only except `trial.py run`, which makes paid model calls.

```bash
python3 experiments/merge_stats.py --out-dir <new empty dir>
python3 experiments/manifest_deps.py > edges.json
python3 experiments/simulate_cost.py gson yapf brotli zx magika langextract
python3 experiments/simulate_cost.py gson yapf brotli magika --budget 50
```

## Next steps

1. Give the graph tool the shape the flow question asks for: a traversal with `--depth` and `--limit` that returns the two-step closure, then rerun the flow trial. Also try a graph-first, search-second agent prompt.
2. Add a column for a graph-first, grep-second agent (the intended workflow).
3. Compare `merge-graphs` and the manifest edges on a repo set that contains real dependencies (gson, libphonenumber, googletest, flatbuffers, dagger).
4. Test whether the hierarchy answers the registry's 20 questions.
5. Add a dependency scope tag (runtime, test, benchmark) to the manifest edges.
6. Add `--files` and `--limit` to `semantic_query.py` and rerun the 36-run trial as the "after" into a new results directory.
