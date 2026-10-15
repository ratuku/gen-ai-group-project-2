# Baseline setup checks - October 15, 2026

Supporting test record. The single submission report is [PROJECT_REPORT.pdf](../../PROJECT_REPORT.pdf).

Base revision: `6e4735d6b1b81ac2233d00d9e775ccaf5736d83b` (main).
The evaluation harness is an uncommitted addition on
`codex/issue-14-model-comparison` at the time of these checks.

## Completed checks

| Check | Observed result |
|---|---|
| Full regression suite (`python -m pytest`) | 204 passed |
| Strict type checking (`python -m mypy`) | No issues in 54 files |
| Evaluation-specific tests | 9 passed; includes real filesystem MCP round trip and timeout handling |
| Filesystem smoke test | Discovery, create/write/list/read, outside-workspace denial, cleanup passed |
| External-resource smoke test | DeepWiki discovery and a public MCP Python SDK question passed |
| Corpus preparation | 4 documents, 10,473 chunks, 384-dimensional MiniLM embeddings |
| Chroma indexing | 10,473 chunks indexed |
| Custom RAG over MCP | `rag.search_docs` discovered and reranked query returned three results without a tool error |

The harness tests use scripted responses solely to validate plumbing. They are
not results for either Groq model.

## Setup issues and retrieval observations

The initial RAG launch resolved `python` to the system installation, which lacked
`mcp`. A second launch explicitly used this repository's `.venv/Scripts/python.exe`
and succeeded. The local evaluation configuration pins that executable and uses
the downloaded embedding and reranking model caches in offline mode. This is a
local setup adjustment; the production MCP configuration was not changed.

Ingestion warned about 1 Java, 13 JavaScript, and 1 Python PDF pages without text.
Those pages were skipped by the existing loader; scanned content needs OCR.

The smoke query asked about UTF-8 `pathlib.Path.write_text`. Its three reranked
results came from `fastmcp_docs.txt` and discussed resource templates, key material,
and URI encoding. They did not document `Path.write_text`. This demonstrates
transport/inference operation, but provides weak evidence for that coding task.
Inspect whether the live models recognize missing support rather than cite these
snippets as proof. It does not establish whether reranking improves on cosine
retrieval; that requires ticket #15's separate comparison.

## Live model comparison: completed

Ran four fixed tasks three times with each of `openai/gpt-oss-20b` and
`openai/gpt-oss-120b`, using the configured Windows environment variable for access.
20B passed 4/12 attempts end to end and 4/12 code checks. 120B passed 1/12 end to
end and 3/12 code checks. The report distinguishes tool/model-output failures from
observed account limits and passing edits interrupted before completion.

The [reviewed baseline results](results/2026-10-15/BASELINE_MODEL_RESULTS.md) include outcomes, observed
differences, failure investigation, source-grounding review, and limitations.
All 24 retained source files reproduce their original check results and match
their source hashes. Sanitized traces, runtime metadata, diagnostics, the actual
CLI connection transcript, and final code are retained with the report.
