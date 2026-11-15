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
- Limits: three repeats per cell, one small model, an approximate text-based reference, and plain search itself reached only 0.80 F1. Some F1 ranges overlap (A 0.57-0.86 against B 0.39-0.63). The reference cannot represent classes with short or duplicated simple names, which understates search precision (Finding 12).

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

Model and cost: every saved run used `claude-haiku-5-5` (from the run files). All 88 saved runs cost $0.825: 36 "who uses X" runs $0.181, 18 flow runs $0.230, 27 flow reruns $0.357, 5 pilot runs $0.026, and 2 interrupted rerun runs $0.031. The 81 measured runs, without pilots and the interrupted pair, cost $0.768. Interrupted runs that were not saved may have cost a little more. This excludes the cost of the assistant sessions that built and analysed the experiments.

## Related work

I read LogicLens and codebadger in full (text supplied by the author). The community tools below were read as listings only. This is not a survey of the wider literature.

- **LogicLens** (arXiv [2601.10773](https://arxiv.org/abs/2601.10773), Sourcesense, January 2026). Tree-sitter builds a multi-repository graph (Java, Python, Go, TypeScript) of Project and Code nodes with depends-on, calls and implements edges. Cross-repository references are unified by Java fully qualified name. An LLM then writes summaries for each code unit, project and system and extracts domain Entity nodes joined by verb-labelled edges, so repositories connect through shared entities. A ReAct agent queries the graph with five tools. Evaluation: 30 questions on one unnamed enterprise system, rated by one expert on a three-point scale, against an n8n agent over a Qdrant vector index. High accuracy 69.5% against 0%, high completeness 26.0% against 0%, high coherence 52.2% against 17.4%. Caveats: the baseline is vector retrieval, not search tools; the percentages are multiples of 1/23 rather than 1/30 and the baseline rows sum to 91 to 96 percent, so the sample size is unclear; no cost or token figures. Differences from this work: no LLM is used to build the graphs here, and cross-repository edges here come from package manifests. The paper does not discuss bridge nodes from shared standard-library types, so how its graph behaves on them is unknown.
- **codebadger** (arXiv [2603.24837](https://arxiv.org/abs/2603.24837), Lekssays, March 2026). An MCP server over Joern's code property graph that gives an agent high-level tools (codebase summary, taint sources, sinks and flows, program slice, data dependencies, call graph to a given depth) with a cap on the number of taint paths, instead of CPG query writing. The motivation is that token limits prevent loading whole repositories. It estimates hundreds of millions of tokens for an 8,000-method codebase; by my arithmetic its stated 246,000 lines are closer to a few million, so that figure should not be repeated. Evaluation: three qualitative case studies with one model (a memory-safety audit of GGML, a libtiff buffer overflow, a libxml2 CVE patch). No comparison with plain search, and the paper lists quantitative benchmark evaluation as future work. Bounded depth and path caps are the same shape as the `--depth` and `--limit` options planned here.
- **Community code-graph servers**, read as listings only: [optave codegraph](https://github.com/optave/ops-codegraph-tool/wiki), [colbymchenry codegraph](https://cdn.jsdelivr.net/npm/@colbymchenry/codegraph@1.1.1/README.md) and [CodeCompass](https://pypi.org/project/codecompass-mcp/) expose blast-radius and impact tools over MCP. They are independent projects, not GitHub products. Tree-sitter graph tools for agents are therefore not novel; the contribution here is the measurements and their limits.
- **Not found in the two papers read:** any comparison of a graph-assisted agent against an agent with plain search tools. That says nothing about the wider literature.

## Prior art in this repository

`graph_registry.py` routes a question to the right repo's graph. On 18 repos and 20 user-written questions: 11 confident and correct, 1 confident and wrong, 8 ambiguous. This was not a held-out test and its thresholds are uncalibrated (see `scripts/graph_registry.py`).

## What is safe to claim

- Union graphs of real repositories reach tens to hundreds of megabytes.
- `merge-graphs` concatenates; it produced no direct cross-repo edge, and its bridges are mostly standard-library names.
- Explicit dependency extraction from manifests finds real edges but needs per-ecosystem parsing and care with name collisions between ecosystems.
- For structural questions on the sampled repos, a budgeted graph answer is several times smaller than reading files and tens of times smaller than reading whole files, at the cost of coverage.
- With an uncapped, symbol-level tool, an agent using the graph spent more turns and tokens than plain search on "who uses X" questions. Accuracy depended on the reference: lower against a grep-built reference, higher against compiler-derived dependencies on gson (Findings 7 and 11).
- On gson the mapper graph's dependents match compiled dependencies (precision 1.00, recall 0.88 to 1.00), and modelling annotation types moved five annotation types from no dependents found to an exact match (Finding 11).
- On two-step flow questions in dagger, graph-assisted agents used about 40 percent fewer input tokens and cost 20 to 27 percent less, but found fewer of the right files (recall 0.46 against 0.75, F1 0.53 against 0.80). They used the graph in every run and a stronger nudge changed nothing (Finding 9).

## What not to claim

- That the graph replaces search. Coverage plateaus near 0.4 on three of four repos, and in the trial plain search was cheaper on direct-usage questions.
- That search is more accurate than graph answers: that comparison reversed when the reference changed from grep to compiled dependencies (Finding 11).
- That graphs lose in general. Findings 7 and 8 tested two tool shapes on two question types with one small model.
- Anything from Finding 8, where every graph run had denied tool calls; use Finding 9.
- That the graph tools help on multi-hop questions: in Finding 9 they were cheaper but found fewer of the right files.
- That the agents under-used the graph in the flow trial: their recall matched the graph's own ceiling (Finding 10).
- That a stronger prompt or hook is needed for agents to use the graph. Adoption was 9 of 9 even with the soft prompt in this setup.
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

1. Report what the mapper skipped (dynamic call sites, injection markers, unmodelled constructs) in each query answer and test it as a footer condition, graded against compiled dependencies. Check Finding 6 and the flow trial against compiled references on more repositories, and test the repository-size effect on a very large monolith.
2. Add a column for a graph-first, grep-second agent (the intended workflow).
3. Compare `merge-graphs` and the manifest edges on a repo set that contains real dependencies (gson, libphonenumber, googletest, flatbuffers, dagger).
4. Test whether the hierarchy answers the registry's 20 questions.
5. Add a dependency scope tag (runtime, test, benchmark) to the manifest edges.
6. Add `--files` and `--limit` to `semantic_query.py` and rerun the 36-run trial as the "after" into a new results directory.
