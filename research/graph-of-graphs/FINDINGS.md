# Findings: graphs of graphs across 20 real repositories

Evidence for an article on combining ast-grep, the semantic code graph, and Graphify into a graph of graphs. Every number below was produced by a script in `experiments/` or read from `results.tsv`.

## Thesis

Merging per-repository code graphs does not make a graph of graphs. It makes a bigger graph that is too large to use as agent context, and whose cross-repository links are mostly shared standard-library names. Real cross-repository edges come from package manifests, and a usable multi-repository view needs a hierarchy and a budget.

For agents, a graph tool changes the trade between cost and completeness, and the trade depends on the graph and on the shape of the tool. With the first mapper, agents were cheaper than search but found about half of the right files (recall 0.48 against 0.96), largely because the graph was missing data: annotation types and static imports. Fixing the mapper raised recall to 0.78 but erased the cost advantage, because agents walked the graph one hop at a time (33 queries and 36 turns, against 20 turns for search). A single `closure` call with a coverage footer cut the cost to $0.004 a run (a third of search) and input tokens to an eighth, at F1 0.84 against 0.94. In every logged run the agents answered from the graph and did not verify, even when told to. Which answer key is used can decide the winner: a grep-built key favors search, a compiler-derived key favored the graph on gson.

## Status of the findings

| Finding | Topic | Status |
| :--- | :--- | :--- |
| 1 | Raw graph sizes | Current |
| 2 | `merge-graphs` is concatenation | Current (edges equal the sum; 266 of the nodes were merged) |
| 3 | Bridges are standard-library names | Current; the last 64 of 104 non-stoplist bridges were not read |
| 4 | Manifest dependency edges | Current; recall 7 of the 10 edges known |
| 5 | Hierarchy size | Current; only size measured |
| 6 | Simulated cost | Current as a simulation; its coverage plateau was measured against grep-built keys (see 11 and 12) |
| 7 | "Who uses X" trial | Cost current; accuracy depends on the key (11); the yapf graph had no dependents (12) |
| 8 | First flow trial | Superseded by 9 (every graph run had denied tool calls) |
| 9 | Clean flow trial | Numbers current against the old key; its cause was superseded by 10; rescored in 14 |
| 10 | Graph recall ceiling | Current; the mapper gaps it found were fixed in 11 and 13 |
| 11 | Compiler-derived key on gson | Current |
| 12 | Answers to review questions | Current; one claim about `jdeps` and retention was corrected in the text |
| 13 | Static imports | Current; not checked against a compiler |
| 14 | Name-resolving key | Current; supersedes the old key |
| 15 | Closure query and footer | Current |
| 16 | Rebuilt graph | Current |
| 17 | Closure trial | Current |
| 18 | Build time against Graphify | Current; indicative, not a controlled benchmark |
| 19 | Graphify nudge probe and planned test | Probe current; experiment planned, not run |

## Runs and cost

| Trial | Findings | Runs | Cost | Per-run data |
| :--- | :--- | ---: | ---: | :--- |
| gson and yapf, search against graph | 7 | 36 | $0.181 | `data/trial-before-runs.csv` |
| dagger flow, first attempt (denied calls) | 8 | 18 | $0.230 | `data/trial-flow-runs.csv` |
| dagger flow, clean, A, B and C | 9 | 27 | $0.357 | `data/trial-flow-v3-runs.csv` |
| dagger flow, rebuilt graph, A and B | 16 | 18 | $0.286 | `data/trial-flow-v4-runs.csv` |
| dagger flow, closure, D | 17 | 9 | $0.034 | `data/trial-flow-v5-runs.csv` |
| pilots and two interrupted runs | | 7 | $0.057 | not published |
| **Total** | | **115** | **$1.145** | |

All runs used `claude-haiku-5-5` (from the run files). The cost excludes the assistant sessions that built and analysed the experiments and any unsaved interrupted runs.

## Which answer key each finding uses

| Key | Built from | Findings |
| :--- | :--- | :--- |
| grep-built | `git grep -w` over non-test files | 6, 7 |
| text closure, unique names | identifier mentions among classes of five or more letters occurring in one file | 8, 9, 10, 12, 13 |
| compiler-derived | `jdeps` over compiled gson classes (RUNTIME-retained annotations only) | 11 |
| name-resolving text | imports, own package, wildcard imports, static imports; comments, strings and import lines ignored | 14, 15, 16, 17 |

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
- Validity check on tool denials (added after the fact): 4 of the 18 graph-condition runs had at least one denied tool call, because the agent sometimes wrote a compound shell command that the allow-rule did not match. The 14 graph runs with no denial give the same picture (cost $0.006, 5 turns, recall 0.96, F1 median 0.92, against $0.004, 2 turns and F1 0.99 for search), so this finding does not depend on the denied runs. Whether the agents used the graph tool successfully in the other runs was not logged.
- One scoring note: an agent once answered with an extra leading repo folder (`yapf/yapf/pytree/...`). The scorer now accepts a repo-name prefix for both conditions, since the files were right.

## Finding 8: measured agent trial on multi-hop flow questions (dagger), superseded by Finding 9

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
- The hypothesis that a graph wins where search has no obvious keyword is not supported by this tool. A likely cause, not tested here: `auto_context` returns a ranked list of 40 files by personalised PageRank, not the two-step closure the question asks for. B's precision was similar or higher and its recall lower, which fits an agent that stops after a partial list. (Superseded: the Finding 9 logs show the agents did not use `auto_context`.)
- Plain search itself reached only 0.57 to 0.83 F1, and A's precision of 0.53 on the first question suggests the agent and the approximate reference disagree about what "takes part" means. These questions are hard and the reference is imperfect.
- Three repeats per cell. Ranges overlap on two of the three questions, so read this as direction, not significance.
- **Validity problem: this result is inconclusive.** All 9 graph-condition runs had at least one denied tool call (12 in total). The agents often wrote a compound shell command (`cd`, shell variables, a loop) that the allow-rule, which only matched commands starting with the script, refused. There are no clean graph runs to compare, so the lower recall cannot be separated from the agents being blocked from the tool. The conclusions above were drawn before this check and should be read as provisional. The harness now tells the agent to run one command per call and records denials per run; a rerun is needed.

## Finding 9: clean rerun of the flow trial with tool-use logging (dagger)

Experiment: the same three questions and references as Finding 8, rerun after fixing the denied-tool-call problem (the prompt now tells the agent to run one command per call) and with every tool call logged. 27 real runs of the same small model, 3 repeats, three conditions. A: search tools only. B: graph tools offered, with the soft prompt line "use it first; verify with search when unsure". C: B plus "before you search or read any source file, run a graph query first". Total cost $0.357. No denied tool calls. Stored: `data/trial-flow-v3-runs.csv` (one row per run, including tool-call counts) and `data/trial-flow-v3-scores.txt`.

| Condition | Runs | Graph used | Cost per run | Turns | Input tokens | Precision | Recall | F1 median (range) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| A search | 9 | 0 | $0.015 | 19 | 219,270 | 0.82 | 0.75 | 0.80 (0.57-0.86) |
| B graph, soft nudge | 9 | 9 | $0.012 | 28 | 131,063 | 0.89 | 0.46 | 0.53 (0.39-0.63) |
| C graph, strong nudge | 9 | 9 | $0.011 | 25 | 133,036 | 0.89 | 0.46 | 0.52 (0.39-0.62) |

By question (medians):

| Entry class | Cond | Cost | Turns | Recall | F1 | Graph calls | Grep or Glob | Reads |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MissingBindingValidator | A | $0.026 | 20 | 0.73 | 0.58 | 0 | 13 | 2 |
| MissingBindingValidator | B | $0.014 | 43 | 0.54 | 0.50 | 41 | 2 | 0 |
| MissingBindingValidator | C | $0.015 | 43 | 0.58 | 0.52 | 41 | 1 | 0 |
| HiltViewModelFactory | A | $0.013 | 17 | 0.75 | 0.83 | 0 | 11 | 5 |
| HiltViewModelFactory | B | $0.011 | 28 | 0.31 | 0.41 | 23 | 1 | 1 |
| HiltViewModelFactory | C | $0.011 | 29 | 0.25 | 0.39 | 26 | 3 | 0 |
| ActivityRetainedComponentManager | A | $0.015 | 25 | 0.81 | 0.81 | 0 | 8 | 17 |
| ActivityRetainedComponentManager | B | $0.009 | 22 | 0.46 | 0.62 | 20 | 1 | 0 |
| ActivityRetainedComponentManager | C | $0.009 | 24 | 0.46 | 0.62 | 22 | 1 | 0 |

Reading:

- The graph conditions cost 20 to 27 percent less and used about 40 percent fewer input tokens, but found fewer of the right files: recall 0.46 against 0.75 and F1 0.53 against 0.80. F1 was lower on all three questions and cost was lower on all three. Turns were higher on two of the three.
- The nudge made no difference. The graph was used in 9 of 9 runs in both B and C, and a graph call was the first tool call every time. The strong prompt changed neither cost nor F1. The low-adoption problem reported for other setups did not appear here (one small model, the tool described in the prompt).
- What the agents did: they ran the one-hop `semantic_query.py` a median of 23 (B) and 22 (C) times per run, searched about once or twice, and read no source files. They never used `auto_context.py`, the ranked-list tool the prompt listed first. The search-only agents ran a median of 11 searches and 5 file reads.
- This corrects the cause suggested for Finding 8, which assumed the agents used the ranked top-40 list. They did not. A better-supported hypothesis, not tested: hop-by-hop one-hop queries return class and method names rather than files, and the agents answered from them without reading code or searching, stopping before the two-step set was complete. (Superseded by Finding 10: the graph agents reached the graph's own recall ceiling, so the gap is in the graph.)
- Limits: three repeats per cell, one small model, an approximate text-based reference, and plain search itself reached only 0.80 F1. Some F1 ranges overlap (A 0.57-0.86 against B 0.39-0.63). The reference used in Findings 8 to 13 could not represent classes with short or duplicated simple names, which understated search precision; Finding 14 rescored against a name-resolving reference.

## Finding 10: the graph's own recall ceiling explains the flow result (dagger)

Analysis of the saved runs with no model. For each flow question, I computed which files are reachable within 1, 2 and 3 hops of the entry file in this repository's own mapper graph (file-level, from each edge's source file to the file of its target class), and compared that with the reference set.

| Entry class | Reference files | Reference files present in the graph | Graph ceiling at 2 hops | Graph agents, recall (B / C) | Search agents, recall (A) |
| :--- | ---: | ---: | ---: | :--- | ---: |
| MissingBindingValidator | 26 | 0.85 | 0.58 | 0.54 / 0.58 | 0.73 |
| HiltViewModelFactory | 32 | 0.50 | 0.31 | 0.31 / 0.25 | 0.75 |
| ActivityRetainedComponentManager | 26 | 0.62 | 0.46 | 0.46 / 0.46 | 0.81 |

Reading:

- The graph agents' recall matches the graph's own ceiling almost exactly. They did not stop early or under-use the graph; they extracted what it contained. Search agents exceeded the ceiling because they read files.
- 30 of the 84 reference entries (36 percent) are not in the graph at all, and all 30 are annotation type declarations (`@interface` files such as `Provides`, `Module`, `Component`, `BindsInstance` and `Nullable`). The mapper records class, method and constructor nodes only, so annotation types have no node and no edges. Dagger's public API is annotation-heavy, which makes it a hard case for a syntax graph.
- This replaces the hypothesis in Finding 9 that the agents answered from one-hop results and stopped early. The gap is in the graph.
- Caveats: the reference is a text closure, so it counts files that merely mention a name; "present in the graph" means the file has at least one node; the ceiling maps edge targets to files by class name, which is approximate; one repository.

The mapper change that models annotation types and annotation-use edges raised the 2-hop ceilings against that text reference to 0.58, 0.66 and 0.81 and put every reference file in the graph; Finding 11 checks the change against an independent reference. What followed from it: extract annotation types and annotation-use edges; have the mapper report what it skipped (unparsed or unmodelled constructs, dynamic calls, injection markers) in each query answer; and grade any such footer against a reference that does not come from text search, for example class dependencies from compiled classes with `jdeps`, since a footer built on `git grep` would close the gap against a grep-built reference by construction. The effect of repository size (does the gap shrink on a very large monolith?) is untested.

## Finding 11: an independent, compiler-derived reference (gson, jdeps)

Experiment: `experiments/jdeps_reference.py` (commands to reproduce are in its docstring). The gson main sources were compiled with `javac` (three generated or external annotation types stubbed, see `experiments/jdeps/stubs`) and `jdeps -verbose:class` produced class dependencies. A source file counts as a dependent of X when one of its compiled classes depends on X. This reference does not come from text search. Everything is restricted to the compiled module (`gson/src/main/java/`), so files in other modules count against no one.

Who uses a class (three symbols from the trial):

| Symbol | Files that depend on it (jdeps) | Files `git grep` names | grep precision / recall | Mapper graph before the fix, precision / recall | Mapper graph after the fix, precision / recall |
| :--- | ---: | ---: | :--- | :--- | :--- |
| JsonPrimitive | 8 | 10 | 0.80 / 1.00 | 1.00 / 0.88 | 1.00 / 0.88 |
| JsonParseException | 10 | 13 | 0.77 / 1.00 | 1.00 / 0.90 | 1.00 / 0.90 |
| JsonObject | 4 | 6 | 0.67 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |

Who uses gson's own annotation types (the direct test of the annotation fix):

| Annotation type | Dependent files (jdeps) | Mapper before the fix | Mapper after the fix |
| :--- | ---: | :--- | :--- |
| SerializedName | 2 | none found | 2 found, exact |
| Expose | 1 | none found | 1 found, exact |
| JsonAdapter | 2 | none found | 2 found, exact |
| Since | 1 | none found | 1 found, exact |
| Until | 1 | none found | 1 found, exact |

The 18 saved gson trial answers rescored against both references (median F1, answers restricted to the compiled module):

| Condition | F1 against the grep-built reference | F1 against the jdeps reference | Recall against jdeps |
| :--- | ---: | ---: | ---: |
| A: search only | 1.00 | 0.84 | 1.00 |
| B: graph offered | 0.89 | 1.00 | 1.00 |

Reading:

- The grep-built reference rewards files that merely mention a name. Against compiled dependencies it has recall 1.00 but precision 0.67 to 0.80. Against it, search looks best; against the compiler-derived reference, the ranking reverses on gson. The accuracy comparison in Finding 7 therefore depended on how the reference was built. The cost comparison (turns, tokens, dollars) does not depend on the reference and is unchanged.
- On gson the mapper graph agrees with compiled dependencies: precision 1.00 and recall 0.88 to 1.00. The coverage plateau in Finding 6 was measured against grep-built references; it was not re-measured against compiled dependencies on the other repositories.
- The annotation fix closes a real gap: all five annotation types went from no dependents found to exactly the files jdeps lists. On dagger the corresponding gain (Finding 10) was measured only against a text reference, because compiling dagger needs Bazel. Of the 19 unique annotation files in that reference, 8 are RUNTIME-retained (visible to jdeps) and 11 are CLASS-retained, which jdeps does not report (Finding 12), so a class-file tool could confirm only part of that gain. The five gson annotation types in the table above are RUNTIME-retained, so jdeps does report them.
- Limits: one module, three symbols plus five annotation types, nine runs per condition, jdeps does not see source-retention annotations or reflection, and four types are stubbed. This does not show that graph answers are more accurate in general.

## Finding 12: answers to review questions about the dagger result and the references

Free analyses on saved data, no model runs. Pooled counts are over the three flow questions (84 reference entries; the 30 annotation entries are 19 unique files).

Two-hop recall ceiling by what is being asked for (old mapper, mapper after annotation types were modelled, and the Graphify graph of the same repository):

| Entry class | Reference (annotation / other) | Old mapper: all / other / annotation | New mapper: all / other / annotation | Graphify: all / other / annotation |
| :--- | :--- | :--- | :--- | :--- |
| MissingBindingValidator | 26 (4 / 22) | 0.58 / 0.68 / 0.00 | 0.58 / 0.68 / 0.00 | 0.81 / 0.86 / 0.50 |
| HiltViewModelFactory | 32 (16 / 16) | 0.31 / 0.62 / 0.00 | 0.66 / 0.62 / 0.69 | 0.62 / 0.56 / 0.69 |
| ActivityRetainedComponentManager | 26 (10 / 16) | 0.46 / 0.75 / 0.00 | 0.81 / 0.75 / 0.90 | 0.81 / 0.81 / 0.80 |
| Pooled | 84 (30 / 54) | 37 of 84 (0.44) | 57 of 84 (0.68) | 62 of 84 (0.74) |

- Annotation types are not the whole story. Leaving them out, the old mapper's ceiling on the other 54 files is 0.69 (37 of 54), and the fix does not change it. The fix recovered 20 files; 27 of 84 are still unreachable at two hops (17 other files and 10 annotation files).
- The ceiling is computed the way the reference is: two hops, outgoing from the entry file, files as nodes, method-level edges rolled up to the file they start in, targets mapped to files by class name. What differs is what counts as an edge: the reference counts any identifier mention outside comments (imports, generic arguments, strings, annotation names), the graph counts the edge kinds it models. It is a fair bound on depth and direction, not a pure measure of true dependencies.
- Retention of the 19 unique annotation files: 8 RUNTIME, 10 CLASS (explicit), 1 with no `@Retention` (default CLASS), 0 SOURCE. In the gson build, jdeps reports dependencies on the RUNTIME-retained `JsonAdapter` (2 files) but none on the CLASS-retained stub `CanIgnoreReturnValue`, although 9 gson main files use it. So jdeps does not report class-retained annotations: only the 8 RUNTIME files are visible to a jdeps-style reference, and the other 11 are compile-time dependencies it cannot confirm. Restricted to what jdeps could confirm (67 of the 84 reference entries), the old mapper's two-hop ceiling is 37 of 67 (0.55) and the new mapper's is 43 of 67 (0.64), or 0.60, 0.59 and 0.75 per question.
- The 17 other files still unreachable: in the file that points at them, the name appears as a plain type or call use in 9 cases, via a static import in 6 (a call without a receiver, a real mapper gap), and only inside a string literal in 2 (likely reference noise). The 9 plain uses were not examined further.
- The Graphify graph of dagger has nodes for all 19 annotation files (the mapper had 0 before the fix and 19 after). It reaches more of the reference (0.74 against 0.68), better on one question and worse on another. This is a ceiling only; Graphify's reachable set is also larger, so it says nothing about precision.

"Who uses X" (gson and yapf trial):

- gson: the mapper graph can name 0.75, 0.72 and 0.78 of the grep reference (unchanged by the annotation fix), and the graph agents' recall was 1.00, 0.83 and 0.78: at the ceiling, or above it where the agent also searched. Against compiled dependencies the graph's recall is 0.88 to 1.00 (Finding 11); the gap to the grep reference is mostly files that only mention the name.
- yapf: the mapper graph has no dependents for `Leaf`, `Node` or `YapfError` (ceiling 0.00). The yapf graph condition therefore had nothing to offer, and its recall of 0.92 to 1.00 came from searching. The yapf rows of Finding 7 are not a test of a working graph.

What the Finding 6 coverage plateau is made of (Graphify graphs, no node budget, symbols as in Finding 6):

| Repository | Reference files | Named by the graph | Missed: code files (real use / comment only) | Missed: tests, docs, config |
| :--- | ---: | ---: | :--- | :--- |
| yapf | 63 | 19 (0.30) | 26 (24 / 2) | 12 tests, 4 docs |
| brotli | 142 | 48 (0.34) | 58 (45 / 13) | 21 tests, 3 docs, 5 config |
| magika | 137 | 45 (0.33) | 47 (44 / 3) | 26 docs, 9 tests, 1 config |
| gson | 812 | 605 (0.75) | 92 (12 / 80) | 54 tests, 39 docs, 13 config |

On yapf, brotli and magika the plateau is mostly real code uses the graph did not link, not annotations (the code is Python, C and mixed). On gson it is mostly files that mention the name only in comments or docstrings, which are not dependencies. "Real use" here means a line that is not an import or a comment; it was not checked by reading.

What the one-hop graph answer tells an agent: `find-usages MissingBindingValidator` returns a header and one line. Nothing in it reports a count, truncation, skipped files or possible incompleteness. The agents had no way to see what the graph could not.

Search agents' false positives, MissingBindingValidator (3 runs): 23 distinct entries were answered but are not in the reference. 21 are classes the reference cannot represent at all, because its class map only uses names of five or more letters that occur in exactly one file (about 100 of the 722 main-source files fall outside it): `BindingGraph`, `Binding`, `Key`, `DependencyRequest`, `DiagnosticReporter`, `DaggerElement` and others. Two sit at three and four hops. By name these are plausible dependencies of a missing-binding validator, so the search agents' precision of 0.53 on that question is understated by the reference. I did not verify each by reading. The mapper has the same limitation (it keys classes by simple name, so same-named classes collapse), so both conditions are affected, in different ways. Treat the dagger flow numbers as measured against a partial reference.

Model and cost: every saved run used `claude-haiku-5-5` (from the run files). At that point 88 saved runs had cost $0.825 (the final total is in "Runs and cost"): 36 "who uses X" runs $0.181, 18 flow runs $0.230, 27 flow reruns $0.357, 5 pilot runs $0.026, and 2 interrupted rerun runs $0.031. The 81 measured runs, without pilots and the interrupted pair, cost $0.768. Interrupted runs that were not saved may have cost a little more. This excludes the cost of the assistant sessions that built and analysed the experiments.

## Finding 13: resolving static imports in the mapper (dagger)

The review of Finding 10 found that 6 of the 17 non-annotation files the graph could not reach were pulled in by a static import: the caller writes a call without a receiver (`toImmutableSet()`), and the class is only named in `import static ...DaggerCollectors.toImmutableSet;`. The mapper looked such calls up in the current class and its supertypes only. It now also resolves them through single-member and wildcard static imports, for classes declared in the repository; a method of the current class still takes precedence, as in Java. Same-named classes still collapse, because the mapper keys classes by simple name.

- On dagger it resolved 1,704 more calls (resolved calls 9,712 to 11,416).
- Two-hop ceiling against the text reference: MissingBindingValidator 0.58 to 0.77, the other two questions unchanged (0.66 and 0.81), since their misses are not static imports. Pooled: 62 of 84 (0.74), up from 57 (0.68), equal to the Graphify graph's 0.74. Against the part of the reference a class-file tool can confirm (RUNTIME-retained annotations only, 67 entries): 48 of 67 (0.72), up from 43.
- These are measured against the same text reference as before, which includes mentions in imports and strings. Unlike the annotation change, this one has not been checked against a compiled-class reference (gson has few static-import calls; dagger needs Bazel to compile).
- Still unexplained: 9 files whose name appears in the predecessor file as an ordinary type or call use, and 2 whose only mention is in a string literal.

## Finding 14: a javac-style reference, and the graph the agents used was the weak one

Experiment: `experiments/java_reference.py`. The text closure used in Findings 8 to 13 could only represent classes whose simple name had five or more letters and occurred in exactly one file. The new reference resolves a name the way `javac` does: through the file's single-type imports, its own package and its wildcard imports, with static imports counted when the member appears in the code. Comments, string literals and import lines are ignored, so a name that appears only there is not a dependency, and same-named classes in different packages stay separate. It is still text-based (it does not model inherited members, generated code or nested-name references), and it has not been checked against a compiler on dagger. Questions and references: `experiments/trial/questions_flow_v2.json`.

| Entry class | Old reference | New reference | In both | Only old | Only new |
| :--- | ---: | ---: | ---: | ---: | ---: |
| MissingBindingValidator | 26 | 38 | 19 | 7 | 19 |
| HiltViewModelFactory | 32 | 26 | 24 | 8 | 2 |
| ActivityRetainedComponentManager | 26 | 23 | 21 | 5 | 2 |

The newly counted files for the first question include `Binding`, `BindingGraph`, `BindingGraphPlugin`, `ComponentDescriptor` and `Keys`, classes the old reference could not represent.

The 27 saved runs of Finding 9 against the new reference (median per condition):

| Condition | Precision | Recall | F1 median (range) | F1 against the old reference |
| :--- | ---: | ---: | :--- | ---: |
| A: search only | 0.93 | 1.00 | 0.96 (0.83-1.00) | 0.80 |
| B: graph, soft nudge | 0.90 | 0.48 | 0.65 (0.42-0.81) | 0.53 |
| C: graph, strong nudge | 0.85 | 0.48 | 0.61 (0.51-0.77) | 0.52 |

Two-hop recall ceiling of the mapper graph against the new reference (files reachable of files in the reference, summed over the three questions):

| Mapper version | MissingBindingValidator | HiltViewModelFactory | ActivityRetainedComponentManager | Pooled |
| :--- | ---: | ---: | ---: | ---: |
| Before annotation types (the graph the agents used) | 27 of 38 | 9 of 26 | 11 of 23 | 47 of 87 (0.54) |
| With annotation types | 27 of 38 | 19 of 26 | 19 of 23 | 65 of 87 (0.75) |
| With static imports | 35 of 38 | 19 of 26 | 19 of 23 | 73 of 87 (0.84) |

Reading:

- The search agents were scored unfairly low before: with a reference that can represent the classes they named, search reaches precision 0.93 and recall 1.00. The earlier "false positives" were mostly real dependencies. The gap between search and the graph agents did not shrink; it widened (F1 0.96 against 0.65).
- The graph agents worked with the weakest mapper version, whose ceiling against this reference was 0.54, and their recall (0.48) sits just under it. The improved mapper raises the ceiling to 0.84. Whether the agents reach it is untested: the flow trial needs a rerun with the rebuilt graph (`--graph-suffix -v3`) and the new questions file.
- Limits: the reference is still not a compiler, one repository, three questions, and the mapper still keys classes by simple name, so same-named classes collapse in the graph.

## Finding 15: a closure query with a coverage footer (dagger, no agent involved)

The mapper now flags each class with reflection call sites and parse errors, and `semantic_query.py` has a `closure <Class> --depth N --limit K` command plus a coverage footer on `closure`, `find-usages` and `impact`. The footer says how many files or classes the answer covers, where the graph is blind for those classes (reflection call sites, framework-wired classes, parse errors), how many results were cut and how to see them, and a `git grep -lw` command to verify.

The file list `closure` prints, scored against the javac-style reference of Finding 14 without any agent:

| Entry class | Limit 30: precision / recall | Full depth: precision / recall | Files at full depth |
| :--- | :--- | :--- | ---: |
| MissingBindingValidator | 0.93 / 0.74 | 0.92 / 0.92 | 38 |
| HiltViewModelFactory | 0.68 / 0.73 | 0.68 / 0.73 | 28 |
| ActivityRetainedComponentManager | 0.83 / 0.83 | 0.83 / 0.83 | 23 |

- At full depth the recall equals the two-hop ceiling of Finding 14 with the static-import fix (35 of 38, 19 of 26, 19 of 23). A first version that followed only the entry class, not its file, scored 0.74, 0.46 and 0.30 because nested classes were never expanded; the walk now follows files.
- An agent that copied the list unchanged would score F1 of about 0.92, 0.70 and 0.83, below the search agents' 0.96 median but from one command. Whether agents behave that way, and whether the footer makes them verify, was tested in Finding 17 with a new harness condition D (`--conds D`) that gives agents the closure command and footer. Condition B now also sees the footer on `find-usages` and `impact`, so earlier B runs are not comparable with new ones.
- On dagger the footer recorded no blind spots for the MissingBindingValidator closure, although the graph carries 21 reflection call sites in 17 files elsewhere in the repository. The flags are per class from the file's text, so they say little about code outside the answer.
- Limits: one repository, three questions, a text-based reference that is not a compiler, precision of 0.68 on the Hilt question means a third of the list is files the reference does not count.

## Finding 16: the rebuilt graph closes most of the quality gap, and the cost advantage disappears (dagger flow)

Experiment: the flow trial rerun with the mapper graph rebuilt with annotation types and static-import resolution (Findings 10 and 13). Conditions A (search) and B (graph, soft nudge) only, the javac-style reference of Finding 14, the same small model, 3 repeats, 18 runs, $0.286. The query script was the earlier one, with no `closure` command and no coverage footer, so only the graph changed. 0 denied tool calls and the graph was used in 9 of 9 graph runs. Stored: `data/trial-flow-v4-runs.csv` and `data/trial-flow-v4-scores.txt`.

Pooled medians (the first three rows are the same questions and reference):

| Condition | F1 | Recall | Precision | Cost per run | Turns | Input tokens | Graph / search / read calls |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| A search, earlier run (Finding 14) | 0.96 | 1.00 | 0.93 | $0.015 | 19 | 219,270 | 0 / 11 / 5 |
| B with the original graph (Finding 14) | 0.65 | 0.48 | 0.90 | $0.012 | 28 | 131,063 | 23 / 1 / 0 |
| A search, this run | 0.94 | 0.96 | 1.00 | $0.013 | 20 | 219,125 | 0 / 13 / 3 |
| B with the rebuilt graph, this run | 0.88 | 0.78 | 1.00 | $0.013 | 36 | 187,485 | 33 / 1 / 0 |

By question (this run, medians):

| Entry class | Cond | F1 (range) | Recall | Cost | Turns | Input tokens | Graph / search / read |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| MissingBindingValidator | A | 0.94 (0.90-0.97) | 0.97 | $0.022 | 23 | 503,082 | 0 / 20 / 2 |
| MissingBindingValidator | B | 0.93 (0.92-0.93) | 0.92 | $0.022 | 57 | 318,749 | 55 / 2 / 0 |
| HiltViewModelFactory | A | 0.98 (0.87-1.00) | 0.96 | $0.011 | 18 | 140,394 | 0 / 9 / 8 |
| HiltViewModelFactory | B | 0.87 (0.87-0.89) | 0.77 | $0.013 | 36 | 187,485 | 33 / 1 / 0 |
| ActivityRetainedComponentManager | A | 0.92 (0.92-1.00) | 0.96 | $0.013 | 21 | 219,125 | 0 / 12 / 7 |
| ActivityRetainedComponentManager | B | 0.85 (0.63-0.88) | 0.74 | $0.012 | 30 | 122,445 | 28 / 1 / 0 |

Reading:

- Quality: the mapper fixes closed most of the gap. Graph-agent F1 rose from 0.65 to 0.88 and recall from 0.48 to 0.78, close to the rebuilt graph's pooled ceiling of 0.84, with precision 1.00. The gap to search fell from 0.31 F1 to 0.06. It reached parity on MissingBindingValidator (0.93 against 0.94) and still trails on the other two.
- Cost: the advantage is gone. Both conditions cost $0.013 at the median. The graph agents used 36 turns against 20 and made a median of 33 one-hop graph queries per run (55 on the first question) with one search and no file reads. Input tokens fell 14 percent pooled, from 37 percent less to 34 percent more depending on the question.
- Interpretation: the earlier saving came partly from the graph returning less. Once it returns the right files, the agent spends its turns walking it hop by hop. That is what the `closure` command (Finding 15) collapses into one call; Finding 17 tests it.
- Search agents' F1 was 0.96 in the earlier run and 0.94 here, a sense of run-to-run noise. Ranges overlap (A 0.87-1.00, B 0.63-0.93).
- Limits: nine runs per condition, three questions, a text-based reference, one small model.

Cost of everything run so far: 106 saved runs, $1.11 (the earlier total of $0.825 plus this run's $0.286).

## Finding 17: one closure call cuts cost by two thirds and input tokens by nearly nine tenths, at ten points of F1 (dagger flow)

Experiment: condition D of the harness. The agent is told about `closure <Class> --depth 2 --limit 40`, its coverage footer, and the other graph queries. Same three questions, the javac-style reference of Finding 14, the same small model, 3 repeats, 9 runs, $0.034. The graph was rebuilt with the gap flags (its edges are the same as in Finding 16). Search (A) and the one-hop graph tools (B) are the runs of Finding 16, made earlier with the earlier query script (no `closure`, no footer). 0 denied tool calls; `closure` was used in 9 of 9 runs. Stored: `data/trial-flow-v5-runs.csv` and `data/trial-flow-v5-scores.txt`.

Bars set before the run, against the one-hop graph tools of Finding 16:

| Measure | One-hop tools (B) | Bar | Closure (D) | Met |
| :--- | ---: | :--- | ---: | :--- |
| Graph queries per run | 33 | 5 or fewer | 1 | yes |
| Turns | 36 | 20 or fewer | 2 | yes |
| Input tokens | 187,485 | below 150,000 | 26,662 | yes |
| Recall | 0.78 | 0.75 or more | 0.83 | yes |
| F1 | 0.88 | 0.85 or more | 0.84 | no, by 0.01 |

Pooled medians next to search and the one-hop tools:

| Condition | F1 (range) | Recall | Precision | Cost per run | Turns | Input tokens |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| A: search only (Finding 16) | 0.94 (0.87-1.00) | 0.96 | 1.00 | $0.013 | 20 | 219,125 |
| B: one-hop graph tools (Finding 16) | 0.88 (0.63-0.93) | 0.78 | 1.00 | $0.013 | 36 | 187,485 |
| D: closure with footer | 0.84 (0.72-0.92) | 0.83 | 0.86 | $0.004 | 2 | 26,662 |

By question (D, medians): MissingBindingValidator F1 0.92 (recall 0.92, precision 0.92, 2 turns); HiltViewModelFactory 0.72 (0.73, 0.70, 2 turns); ActivityRetainedComponentManager 0.84 (0.83, 0.86, 3 turns, 42,496 input tokens).

Reading:

- The tool shape was the cost bottleneck. One `closure` call replaced 33 one-hop queries. Cost fell from $0.013 to $0.004 (69 percent), input tokens by 88 percent against search, and turns from 20 to 2.
- The agents added nothing to the tool's answer. Each made one graph call and copied the list. The per-question F1 scores equal the tool's own scores from Finding 15 (0.92, 0.70 to 0.72, 0.83 to 0.84), and outcomes were nearly identical across repeats, so three repeats carry little information about variance. Only 3 of 9 runs searched at all (one search each) and none read a file: the footer's verification line did not cause extra work.
- The trade against search is ten points of F1 (0.84 against 0.94) for about a third of the cost. Against the one-hop tools it is four points of F1: higher recall (0.83 against 0.78) but lower precision (0.86 against 1.00), because `closure` lists every file within two hops where an agent walking hop by hop picks. Quality is bounded by the graph's ceiling and the reference; the weakest question (Hilt) is where the graph and reference disagree most.
- Whether that trade is good enough depends on the cost of a miss. The F1 bar was missed by 0.01, within the run-to-run noise seen for search (0.96 against 0.94).
- Limits: nine runs but effectively three distinct outcomes, comparison runs made earlier, D's prompt names `closure` where B's does not, one repository, one small model, a text-based reference.

Cost of everything run so far: 115 saved runs, $1.15.

## Finding 18: build time of this repository's mapper against Graphify, and what each builds

The mapper's build time was measured on four of the 20 repositories with `/usr/bin/time` (one run each, the guava run reporting 1.5 GB peak memory). Graphify's `extract --code-only` times are the extraction times recorded in `corpus/results.tsv` from the original corpus run, made in an earlier session on the same machine, so the ratios are indicative, not a controlled benchmark. Graph sizes are node counts of the two tools' graphs for the same commit.

| Repository | Graphify extraction | Mapper build | Time ratio | Graphify nodes | Mapper nodes | Graphify nodes per second | Mapper nodes per second |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gson | 56 s | 6.3 s | 8.9x | 5,131 | 3,790 | 92 | 605 |
| yapf | 25 s | 2.0 s | 12.5x | 2,055 | 73 | 82 | 36 |
| dagger | 440 s | 25.7 s | 17.1x | 21,980 | 11,760 | 50 | 457 |
| guava | 584 s | 77.1 s | 7.6x | 80,690 | 29,275 | 138 | 380 |

- The mapper was 7.6 to 17 times faster in wall-clock time. The ratio did not grow with repository size: 8.9 times on gson, 12.5 on yapf, 17.1 on dagger, 7.6 on guava. Any sentence saying the gap grows at scale is not supported; four points do not show a trend.
- The two tools do different amounts of work. The mapper builds 1.3 to 2.8 times fewer nodes on the Java repositories and, for Python, a module-level graph (73 nodes for yapf against 2,055). Per node the mapper is 2.8 to 9 times faster on the Java repositories and slower on yapf. Graphify also computes communities and a report, which the mapper does not.
- On guava the mapper's own graph is 24 MB (29,275 nodes, 52,336 edges) and its `code_map.md` is 7.7 MB, against Graphify's 128.6 MB graph. Both are too large to hand to an agent without a budget. The mapper recorded 13 files with parse errors, 463 reflection call sites in 162 files, 7,173 resolved static-import calls and 140 annotation types on guava.
- Limits: one run per tool and repository, different sessions, different graph contents, Graphify's parallelism (16 workers) and the mapper's single process not equalised.

## Finding 19: what Graphify's installed nudge does, and a pre-registered test of whether nudges matter (dagger flow, planned, not run)

Status: the probe below was run; the agent experiment has not been run. Nothing here is a result about agent behavior.

### Probe: what `graphify claude install` writes (Graphify 0.9.86)

Run in a new empty git repository, then each hook fed sample tool payloads on stdin. No model calls.

- `CLAUDE.md` section: for codebase questions run `graphify query` first when `graphify-out/graph.json` exists; use `graphify path` and `graphify explain`; run `graphify update .` after changing code.
- `.claude/settings.json`: two `PreToolUse` hooks, `Bash|Grep` running `graphify hook-guard search` and `Read|Glob` running `graphify hook-guard read`.
- Search hook output with a graph present and a search-like Bash command: `additionalContext` reading "MANDATORY: graphify-out/graph.json exists. You MUST run `graphify query "<question>"` before grepping raw files. Only grep after graphify has oriented you, or to modify/debug specific lines." It does not deny the call.
- Silent (no output, exit 0) when no graph exists, for a non-search command (`ls`), and for the one `Read` payload tried; what triggers the `Read|Glob` hook was not determined.
- The message says nothing about what the graph misses or that its answers need verifying.

Not checked: whether hooks fire under `claude -p` with project settings, and whether the hook text changes behavior. Earlier trials (Findings 9, 16, 17) put the nudge in the task prompt, so the hook has never been tested, and no condition has left the graph present with no mention at all.

### Hypotheses

1. With the graph in the repository and no mention anywhere, agents mostly do not use it.
2. The installer's `CLAUDE.md` section and hook raise graph use. A soft prompt already gave 9 of 9 graph use (Finding 9), so the increase may be small.
3. The "MANDATORY" wording raises confidence in graph answers without raising recall, so verification stays rare.
4. A calibration rule (the graph lists candidates and misses annotation and reflection uses; verify with one search; end with an `UNVERIFIED:` line) raises verification and the share of misses the agent flags.

### Design

Questions: the three dagger flow questions in `questions_flow_v2.json` (name-resolving key, Finding 14) plus one blind-spot question with a planted dependency the graph cannot see, written before any run. Three repeats per cell. Model `claude-haiku-5-5`. Graph: Graphify's own graph for dagger, since the nudge belongs to Graphify.

| Condition | Agent receives |
| :--- | :--- |
| N0 | graph in the repository, no mention anywhere |
| N1 | installer's `CLAUDE.md` section only |
| N2 | installer's hook only |
| N3 | both (the installer default) |
| N4 | N3 plus the calibration rule |

Measured per run: whether and when the graph was queried, searches and file reads after it, F1 against the key, cost, turns, whether the hook fired (logged), and calibration: for answers that miss reference files, whether the agent flagged uncertainty. Report denied calls and runs where the hook did not fire as invalid, not as zeros.

Planned size: 5 conditions, 4 questions, 3 repeats, 60 runs. Prior graph runs cost $0.013 to $0.04 each, so $0.8 to $2.4 is an estimate, not a measurement. The user launches the paid run; each run has a dollar cap and the trial stops at a total cap.

Pre-registered readings, fixed before running:
- Hypothesis 1 holds if N0 queries the graph in fewer than half the runs.
- Hypothesis 3 holds if N3 recall is not higher than N0 or N1 and N3 searches after the graph in fewer runs than N4.
- Hypothesis 4 holds if N4 flags uncertainty in more than half of the answers that miss files and N3 in fewer than a quarter.
- Antigravity is out of scope. Graphify installs differently there and this test uses Claude Code only.

What this finding does not support yet: any claim that the hook should be installed, or that telling an agent about a graph is required.

## Related work

I read LogicLens and codebadger in full (text supplied by the author). The community tools below were read as listings only. This is not a survey of the wider literature.

- **LogicLens** (arXiv [2601.10773](https://arxiv.org/abs/2601.10773), Sourcesense, January 2026). Tree-sitter builds a multi-repository graph (Java, Python, Go, TypeScript) of Project and Code nodes with depends-on, calls and implements edges. Cross-repository references are unified by Java fully qualified name. An LLM then writes summaries for each code unit, project and system and extracts domain Entity nodes joined by verb-labelled edges, so repositories connect through shared entities. A ReAct agent queries the graph with five tools. Evaluation: 30 questions on one unnamed enterprise system, rated by one expert on a three-point scale, against an n8n agent over a Qdrant vector index. High accuracy 69.5% against 0%, high completeness 26.0% against 0%, high coherence 52.2% against 17.4%. Caveats: the baseline is vector retrieval, not search tools; the percentages are multiples of 1/23 rather than 1/30 and the baseline rows sum to 91 to 96 percent, so the sample size is unclear; no cost or token figures. Differences from this work: no LLM is used to build the graphs here, and cross-repository edges here come from package manifests. The paper does not discuss bridge nodes from shared standard-library types, so how its graph behaves on them is unknown.
- **codebadger** (arXiv [2603.24837](https://arxiv.org/abs/2603.24837), Lekssays, March 2026). An MCP server over Joern's code property graph that gives an agent high-level tools (codebase summary, taint sources, sinks and flows, program slice, data dependencies, call graph to a given depth) with a cap on the number of taint paths, instead of CPG query writing. The motivation is that token limits prevent loading whole repositories. It estimates hundreds of millions of tokens for an 8,000-method codebase; by my arithmetic its stated 246,000 lines are closer to a few million, so that figure should not be repeated. Evaluation: three qualitative case studies with one model (a memory-safety audit of GGML, a libtiff buffer overflow, a libxml2 CVE patch). No comparison with plain search, and the paper lists quantitative benchmark evaluation as future work. Bounded depth and path caps are the same shape as the `--depth` and `--limit` options planned here.
- **Community code-graph servers**, read as listings only: [optave codegraph](https://github.com/optave/ops-codegraph-tool/wiki), [colbymchenry codegraph](https://cdn.jsdelivr.net/npm/@colbymchenry/codegraph@1.1.1/README.md) and [CodeCompass](https://pypi.org/project/codecompass-mcp/) expose blast-radius and impact tools over MCP. They are independent projects, not GitHub products. Tree-sitter graph tools for agents are therefore not novel; the contribution here is the measurements and their limits.
- **Not found in the two papers read:** any comparison of a graph-assisted agent against an agent with plain search tools. That says nothing about the wider literature.

## Prior art in this repository

`graph_registry.py` routes a question to the right repo's graph. On 18 repos and 20 user-written questions: 11 confident and correct, 1 confident and wrong, 8 ambiguous. This was not a held-out test and its thresholds are uncalibrated (see `scripts/graph_registry.py`).

## What is safe to claim

- Union graphs of real repositories reach tens to hundreds of megabytes (guava: 128.6 MB with Graphify's extractor, 24 MB with this repository's mapper). Both need a budget before an agent can use them.
- `merge-graphs` concatenates: its edges equal the sum of the inputs, it produced no direct cross-repository edge, and its bridges are mostly standard-library names.
- Package manifests give real cross-repository dependency edges, but they are sparse (7 among 20 repositories) and need per-ecosystem parsing and care with name collisions between ecosystems.
- Which answer key is used can decide the accuracy ranking. On gson, search scored F1 1.00 against a grep-built key and 0.84 against compiled dependencies; the graph scored 0.89 and 1.00 (Finding 11).
- Two mapper gaps were real and are fixed: annotation types (on gson, five annotation types went from no dependents found to an exact match against `jdeps`) and static-import calls (1,704 more resolved calls on dagger). Against the name-resolving key, the mapper's two-hop ceiling on three dagger questions rose from 0.54 to 0.84 (Findings 11, 13, 14).
- On dagger flow questions, scored against the name-resolving key: search F1 0.94 to 0.96; graph agents with the first mapper 0.65 (recall 0.48); with the rebuilt mapper 0.88 (recall 0.78) at the same cost and more turns; with the `closure` query and footer 0.84 (recall 0.83) at $0.004 a run, 2 turns and 26,662 input tokens, against $0.013, 20 turns and 219,125 for search (Findings 14, 16, 17).
- In every logged run (Findings 9, 16, 17) the agents used the graph, a soft prompt was as effective as a strong one, and they mostly did not verify: a median of one or two searches and no file reads.
- The mapper built its graph 7.6 to 17 times faster than Graphify's `extract --code-only` on four repositories, with a smaller graph (Finding 18).
- On gson and yapf "who uses X" questions with the class named, plain search was cheaper: 2 turns against 5 and about 2.7 times fewer input tokens (Finding 7).

## What not to claim

- That the graph replaces search or matches its quality. The closure query scored F1 0.84 against 0.94, and one pre-registered bar (F1 0.85) was missed by 0.01.
- That graphs lose in general, or that they win. The trials cover one small model, two question types, three flow questions and one large repository.
- That search is more accurate than graph answers. That comparison reversed when the key changed from grep to compiled dependencies (Finding 11).
- That the footer makes agents verify. In Finding 17 they made one call, copied the list, and mostly did not search or read. No task yet put a flagged blind spot in front of them.
- That agents "didn't know" they were trading. The prompts demanded a bare file list, so they had no way to say so; the `UNVERIFIED:` condition exists but has not been run.
- That a stronger prompt or an enforcing hook is needed for agents to use the graph: adoption was 9 of 9 with the soft prompt.
- That a hierarchy answers questions well. Only its size was measured.
- That the speed gap over Graphify grows with repository size (it did not: 9, 12.5, 17 and 7.6 times), or that the mapper is a better tool: it is narrower.
- That the name-resolving key is compiler-grade, or that Finding 13 was checked against a compiler. Only gson has a compiler-derived key.
- That the 7 manifest edges are complete or all runtime dependencies.
- Anything from Finding 8, or the cause given in Finding 9. Use Findings 10, 14 and 16.
- Absolute token figures from the simulation (characters divided by 4), or results from production systems, which are not reproducible here.

## Limits of the evidence

- Samples are small: three repeats per cell. In the closure trial the agents gave near-identical answers each time, so the nine runs are effectively three outcomes. Some score ranges overlap, and search itself moved from 0.96 to 0.94 F1 between runs.
- One model: `claude-haiku-5-5`, the smallest available. Larger models may use tools differently.
- Answer keys are approximate. Only one module of one repository (gson) has a compiler-derived key, `jdeps` reports only RUNTIME-retained annotations, and four types were stubbed to compile. The question set is hub classes, which biases toward well-connected code.
- Findings 1 to 6 use Graphify's graphs; the agent trials (7 and 9 to 17) use this repository's mapper. The mapper builds a smaller graph, and for Python only a module-level one.
- Twenty repositories, mostly Google and mostly independent of each other; results may differ elsewhere. Search was very strong at the size of dagger (about 2,000 files); the effect of a much larger repository is untested.
- Comparison runs were made at different times, and from Finding 16 on the query script changed (a coverage footer was added), so older graph runs are not comparable with newer ones.

## Reproduce

All commands run from `research/graph-of-graphs` after fetching the corpus (see README). Everything is read-only except `trial.py run`, which makes paid model calls.

```bash
# graph-of-graphs experiments (Graphify graphs under _graphs/<repo>/graphify-out/)
python3 experiments/merge_stats.py --out-dir <new empty dir>
python3 experiments/manifest_deps.py --root . > edges.json
python3 experiments/simulate_cost.py gson yapf brotli zx magika langextract

# this repository's mapper graphs, the inputs to the agent trials
python3 ../../scripts/code_mapper.py dagger --force --out-dir experiments/trial/graphs/dagger-v4

# answer keys and ceilings
python3 experiments/java_reference.py --clones . --repo dagger --questions experiments/trial/questions_flow.json --out experiments/trial/questions_flow_v2.json
python3 experiments/graph_ceiling.py --graph experiments/trial/graphs/dagger-v4/relationship_graph.json --questions experiments/trial/questions_flow_v2.json --clones . --repo dagger
python3 experiments/jdeps_reference.py --help        # compile gson with the stubs, then compare with jdeps

# the closure query, no agent involved
python3 ../../scripts/semantic_query.py --graph experiments/trial/graphs/dagger-v4/relationship_graph.json closure MissingBindingValidator --depth 2 --limit 40

# agent trials (paid; each run is capped, and the trial stops at --total-cap)
python3 experiments/trial/trial.py run --reps 3 --conds A,B,D --cap 0.20 --total-cap 3.0 --stop-on-denial --graph-suffix=-v4 --questions experiments/trial/questions_flow_v2.json --results-dir experiments/trial/results-flow-v5
python3 experiments/trial/trial.py score --questions experiments/trial/questions_flow_v2.json --results-dir experiments/trial/results-flow-v5
```

Conditions: A search only, B graph with a soft nudge, C graph with a strong nudge, D graph with `closure` and the coverage footer. `--uncertainty` adds an `UNVERIFIED:` line to the answer format.

## Next steps

1. Run the nudge test pre-registered in Finding 19 (it includes a blind-spot question). Earlier plan: put a flagged blind spot in front of the agents: a task whose closure contains reflection-wired or framework-wired files, a planted dependency the build cannot catch, and the `UNVERIFIED:` line. This is the test of whether the footer makes agents verify.
2. Test the effect of repository size on a very large monolith, where search returns long match lists.
3. Add Python class-usage edges: the yapf graph named no dependents.
4. Key classes by package-qualified name so same-named classes stop collapsing in the mapper.
5. Check the name-resolving key and the static-import change against a compiler on a second repository.
6. Compare `merge-graphs` and the manifest edges on a set of repositories that contains real dependencies, and test whether the hierarchy answers questions.
7. Add a dependency scope tag (runtime, test, benchmark) to the manifest edges.
8. Try a graph-first, search-second prompt variant.
