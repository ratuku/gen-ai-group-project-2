# Ticket #14: two-model end-to-end evaluation

This is the baseline before reliability fixes. See the
[subsequent implementation and validation](../2026-10-15-fixes/REPORT.md) for current changes.

On October 15, 2026, the assistant attempted the same four coding tasks three
times with each Groq model, for 24 scored runs. **GPT-OSS 20B passed 4/12 runs
end to end; GPT-OSS 120B passed 1/12.** The larger model also produced two
refactors that passed code checks before provider quota errors stopped completion.
The results expose reliability problems in the baseline assistant configuration.
They support observations about these tasks and account limits; they do not
establish a general ranking of the models.

## Method

Production code was evaluated at `6e4735d6b1b81ac2233d00d9e775ccaf5736d83b`.
The evaluation harness was an uncommitted addition on
`codex/issue-14-model-comparison`. No production provider, agent, dispatcher, or
MCP implementation was changed during the batch.

Both `openai/gpt-oss-20b` and `openai/gpt-oss-120b` used the production
`GroqProvider -> BasicAgentLoop -> ToolDispatcher -> PolicyMCPClient -> MCPClient`
path. Each run started with a fresh conversation and identical source code in
its own filesystem root. Task prompts differed only in the absolute workspace
path. Initial source hashes match across all six attempts for each task.

All runs discovered the same 18 tools: 14 filesystem, 3 DeepWiki, and 1 custom
RAG tool. Execution policy was auto, with at most 8 model iterations and a
180-second connection/agent deadline. Cleanup can extend measured elapsed time
slightly beyond the deadline. Models used production SDK defaults for sampling,
reasoning, and retries. Model order was reversed for the second repetition.

Correctness checks were evaluator-owned, outside the model's filesystem root,
and executed after each attempt with a 15-second subprocess limit. An end-to-end
pass required passing code checks, successful filesystem read and edit calls,
required retrieval calls for the documentation task, and a normal final answer.
Recovered tool errors were counted without automatically failing the run.

The RAG configuration pinned the project's virtual-environment Python because
the initial `python` launch selected a system interpreter without `mcp`.
Cached embedding and reranking models ran offline against a 10,473-chunk Chroma
index built from the four committed corpus documents. See [metadata](metadata.json),
[effective configuration](mcp-config.json), and [dependencies](dependencies.txt).

## Outcomes

| Model | End-to-end passes | Code checks passed | Tool calls | Tool errors | Median total seconds |
|---|---:|---:|---:|---:|---:|
| GPT-OSS 20B | 4/12 (33.3%) | 4/12 | 51 | 26 | 52.408 |
| GPT-OSS 120B | 1/12 (8.3%) | 3/12 | 65 | 49 | 50.437 |

Medians include failed and successful attempts, server setup, tools, and cleanup.
They exclude grading and do not measure model inference speed. Quotas, SDK
retries, differing completion paths, and external-service time limit comparisons.

| Task | 20B end to end | 20B code checks | 120B end to end | 120B code checks |
|---|---:|---:|---:|---:|
| Fix arithmetic mean and empty-input handling | 1/3 | 1/3 | 1/3 | 1/3 |
| Add unique ASCII words in first-seen order | 3/3 | 3/3 | 0/3 | 0/3 |
| Refactor region aggregation into a helper | 0/3 | 0/3 | 0/3 | 2/3 |
| Write a UTF-8 greeting using retrieved documentation | 0/3 | 0/3 | 0/3 | 0/3 |

The strongest task-level difference was the feature task: 20B completed all three
attempts; 120B repeatedly requested unqualified tool names and exhausted the
iteration limit. On refactoring, 120B produced valid helpers in two attempts;
20B never completed the requested helper change. Both models completed the bug
fix only on their third attempt, demonstrating substantial variation across runs.

## Failure investigation

Each failed run has one terminal category below. Counts sum to the failed
attempts for each model. Full errors and tool sequences are in [the traces](results.json).

| Terminal outcome | 20B | 120B |
|---|---:|---:|
| Iteration limit | 2 | 4 |
| Remote tool validation failure | 3 | 1 |
| Remote generation/argument parsing failure | 3 | 0 |
| HTTP 413: request exceeds token allowance | 0 | 2 |
| HTTP 429: rate limit | 0 | 2 |
| Task deadline | 0 | 1 |
| No usable final response or tool call | 0 | 1 |

**Exact tool names and recovery.** The dispatcher rejected 24 unknown-tool calls
from 20B and 49 from 120B. Examples included `list_directory` and `read_text_file`
instead of the advertised qualified names. Rejection responses supplied the valid
tool names, but models sometimes repeated the invalid name until the iteration
limit. In 20B's first feature run, the model recovered from three such errors,
read and edited the file, and passed in 7 iterations with 6 tool calls. Its second
feature run used just a qualified read and write, finishing in 3 iterations.

**Argument, path, and generation errors.** In 20B's first bug-fix and first
documentation attempts, Groq rejected null `head`/`tail` values for optional
numeric read arguments before execution. Later attempts included malformed tool
JSON and a tool name containing the literal channel marker
`<|channel|>commentary`. The provider surfaced these as errors and the agent
stopped. In 20B's second refactor attempt, one path inserted a space into
`full-run`, and another call attempted to list a parent directory. The filesystem
server denied both accesses. These two server errors account for the remainder
of 20B's 26 tool errors; its other 24 were unknown names. All 49 of 120B's tool
errors were unknown names. Remote provider failures are counted separately.

**Passing code followed by quota failure.** In 120B's refactor repetitions 1
and 2, the saved code passed behavioral checks and contained a real shared
aggregation helper. Manual review confirmed preservation of the north/south
defaults and aggregation of other regions. Subsequent requests were rejected
with HTTP 413: estimated request sizes were 8,542 and 9,010 tokens against an
8,000 TPM account limit. These are code-check passes and end-to-end failures.
Its documentation repetitions 2 and 3 ended with HTTP 429 token-rate limits.

**Empty output and isolated diagnostics.** The first 120B bug-fix attempt
surfaced no usable text or tool calls. The original native stream was not
retained, so its precise cause remains unresolved. A separate request using the
same initial prompt/tools returned a native tool-call stream. Four forced-choice
and four single-tool automatic-choice probes also preserved both dotted and
underscore names correctly, across both models. These probes show that tool-name
round trips can succeed in simpler contexts; they do not explain all larger-context
failures. They are excluded from scores. See [stream diagnostics](stream-diagnostic.json),
[forced-name probes](name-diagnostic.json), and [automatic-name probes](name-auto-diagnostic.json).
The nine diagnostic requests overlapped the batch, so account load was not fully
controlled for timing comparisons.

## Code and explanation review

All 24 retained source files were rechecked after export and reproduced their
recorded pass/fail outcomes. Their hashes match [the source manifest](source-manifest.json).
Manual review covered the five completed answers and all seven files passing
code checks, including the two refactors interrupted by HTTP 413.

20B's three feature implementations extracted ASCII letter runs, lowercased the
matches, and used a set plus an ordered list to preserve first appearance.
Both successful bug fixes corrected the denominator and raised `ValueError` for
empty sequences. 20B additionally converted inputs to a list. 120B's final bug-fix
explanation claimed support for any numeric iterable, although its implementation
uses `len(values)` and does not support generators. The requested sequence cases
passed; the broader explanation overstates the implementation.

## Retrieval and grounding

| Model / repetition | RAG call succeeded | DeepWiki call succeeded | Code checks passed | Terminal outcome |
|---|---|---|---|---|
| 20B / 1 | No | No | No | Remote argument validation |
| 20B / 2 | Yes | Yes | No | Iteration limit |
| 20B / 3 | No | No | No | Remote tool-name validation |
| 120B / 1 | Yes | Yes | No | Deadline |
| 120B / 2 | No | No | No | Rate limit |
| 120B / 3 | No | No | No | Rate limit |

The successful RAG calls used reranking. Manual review found weak support for
`Path.write_text`: 120B received mainly FastMCP resource/URI snippets plus a Python
string-method passage; 20B received FastMCP resource, path-validation, and
configuration-writing snippets. These did not establish the requested pathlib
API behavior. DeepWiki returned directly relevant descriptions of the method's
character count and writing behavior, but both runs ended before implementation
and a final answer. No documentation attempt produced a final cited explanation,
so source-grounded answer quality could not be assessed. This does not measure
reranking improvement over cosine retrieval; that belongs to ticket #15.

## Validation, limits, and next steps

The full regression suite passed **204 tests**, including 9 evaluation tests.
Strict type checking passed for 54 files. Real filesystem and DeepWiki smoke
tests passed, and a direct custom-RAG MCP query returned reranked results. The
actual CLI connection check discovered all three servers and 18 tools; its
[transcript](cli-connection-check.txt) is retained. Scored coding tasks exercised
the production agent pipeline programmatically. An interactive model-backed CLI
session and video were not recorded in this evaluation.

This is a small synthetic task set with three attempts per task. Refactor tests
check behavior and helper presence, while design quality also needs review.
Hosted model versions and SDK defaults may change. Token usage, cost, per-turn
timing, and internal SDK retry counts were not recorded. Both LLMs ran on Groq;
local Ollama performance was not compared. Ingestion skipped PDF pages without
text, limiting corpus coverage. The setup and quota constraints prevent treating
the observed pass-rate difference as a general capability result.

The next engineering work should strengthen exact-name/argument instructions and
recovery, bound tool/history context to account limits, handle 429 retries and
413 failures distinctly, and improve documentation coverage for the task domain.
Preserve code-check results when a final response is interrupted. Rerun this fixed
suite after changes and retain the new results alongside this baseline.

Reproduction instructions and task definitions are in [the evaluation README](../../README.md).
Use a new output directory, the same task/configuration settings, and a configured
`GROQ_API_KEY`. This run pinned RAG's executable to its virtual environment; adjust
that command for a different checkout. The configuration snapshot uses
`${PROJECT_ROOT}` in place of local paths and needs that placeholder replaced
before direct reuse. Account identifiers are redacted and adjacent text chunks
are coalesced in the published traces. Raw local evidence remains in the ignored
evaluation directory. [Summary metrics](summary.json) and the
[generated per-run table](generated-report.md) accompany the full traces and
final source files.
