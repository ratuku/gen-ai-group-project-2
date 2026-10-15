# Advanced RAG: retrieve, then rerank

The advanced technique is **cross-encoder reranking**. Cosine search remains the
first stage and the comparison baseline. A second, local model scores each
question/passage pair before selecting the final snippets. This addresses cases
where a passage shares the topic but does not help answer the question, such as
release notes ranking above usage instructions.

This follows the [Sentence Transformers retrieve-and-rerank design](https://sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html).
It reuses our existing Chroma index and embeddings; no re-ingestion is needed.
It is not query expansion, a new vector database, or an answer-generating LLM.

Reranking is included in the assignment's required
[NirDiamant RAG_Techniques catalog](https://github.com/NirDiamant/RAG_Techniques#advanced-techniques),
with a [reranking notebook](https://github.com/NirDiamant/RAG_Techniques/blob/main/all_rag_techniques/reranking.ipynb).
Our implementation applies its retrieve-then-reorder pattern with a local
cross-encoder, reusing Chroma rather than copying that notebook's storage setup.

## What changed

| | Cosine baseline | Reranking |
| --- | --- | --- |
| Initial search | Chroma cosine search | Same Chroma cosine search |
| Candidates fetched | `top_k` (default 5) | `candidate_k` (default 20) |
| Final ordering | Cosine similarity | Cross-encoder relevance score |
| Model input | Query embedded separately from documents | Query and each candidate read together |
| Returned evidence | Original text and source references | Same original text and source references |
| Extra cost | None | One local scoring pass over candidates |

The reranker receives `Source: <filename>` followed by the original chunk text.
A filename such as `languages/Python.pdf` supplies language context that may be
missing from a short snippet. This does not alter stored vectors or returned
text. A stable sort preserves cosine order if relevance scores tie.

`similarity` always retains the original cosine score. `rerank_score` is a
separate, unbounded relevance score (raw model logit), or null in baseline mode.
Higher values rank first; neither score is a confidence percentage. The payload
also records `mode`, `candidate_k`, `reranker_model`, and `ranking_score` so the
consumer can tell which score determined ordering. `score_type` continues to
describe the cosine `similarity` field for compatibility.

## Configuration and demo

The existing `rag.search_docs` tool now defaults to reranking:

```json
{"query": "How do I register a tool on a FastMCP server?", "top_k": 5, "candidate_k": 20}
```

Select the original baseline explicitly with the same tool:

```json
{"query": "How do I register a tool on a FastMCP server?", "top_k": 5, "mode": "cosine"}
```

| Option | Default | Meaning |
| --- | --- | --- |
| `mode` | `rerank` for MCP | `cosine` or `rerank` |
| `top_k` | 5 | Final result limit, 1–20 |
| `candidate_k` | 20 | Candidate limit, from `top_k` to 100; used only by reranking |
| `source` | null | Exact source filter applied in Chroma before ranking |
| `min_similarity` | null | Cosine cutoff applied before reranking; not a reranker-score threshold |

The programmatic `Retriever.search()` and `search_payload()` methods keep their
original cosine default; pass `mode="rerank"` to use the advanced technique.
If fewer candidates survive the filters, fewer results are returned. An empty
candidate list does not load or call the reranker.

The default model is `cross-encoder/ms-marco-MiniLM-L6-v2`, loaded lazily once per
server. It uses the existing `sentence-transformers` RAG dependency. First use
requires internet access to download weights; subsequent use can use the cache.
Inference runs locally without Groq, Ollama, or an API key. Discovery and cosine
mode do not load the reranker. A model failure returns an actionable MCP error;
it never silently presents cosine results as reranked results.

To use another compatible single-score cross-encoder, start the server with:

```sh
python -m rag_server.server --reranker-model cross-encoder/ms-marco-MiniLM-L6-v2
```

For the CLI, add `--reranker-model` and its value to the RAG server's `args` in
`config/mcp.json`. Restart the CLI/server after changing configuration. Large
models or slow first downloads may require increasing `timeoutSeconds` there.

## Compare end to end

From the activated project environment, after building the existing index:

```sh
python -m rag_server.compare \
  --query "How do I register a tool on a FastMCP server?" \
  --query "How does Python break stop a loop?" \
  --query "What is the difference between let and const in JavaScript?" \
  --top-k 5 --candidate-k 20 > rag_server/artifacts/retrieval-comparison.json
```

This optional command starts the production MCP server over **stdio** and calls
`search_docs` in both modes on the same open index. It prints JSON with ranked
snippets, IDs, source references, both scores, model names, and elapsed time.
Failures cause a nonzero exit. `--store` and `--reranker-model` allow comparing
other local indexes and models. Generated reports remain under ignored artifacts.

Inspect whether higher-ranked passages actually answer the question, rather than
comparing raw cosine scores to cross-encoder scores. Times include model loading
on first use and are not a controlled latency benchmark. The command is separate
from normal tests because it runs real models and may download weights. It does
not call a cloud LLM. For offline use after caching, set `HF_HUB_OFFLINE=1` and,
if needed, `HF_HOME`; the command forwards those settings to its MCP subprocess.

## Observed comparison on the current corpus

The larger [measured RAG evaluation](../evaluations/rag_evaluation/README.md) now
retains ten fixed retrieval questions, five complete same-model answer pairs,
explicit relevance/grounding judgments, and reproducible metrics. Its findings
appear on page 3 of the submission PDF. The three-query observations below are
earlier exploratory examples, not the final measured experiment.

A local run through the production stdio server used 10,473 indexed chunks,
`top_k=5`, and `candidate_k=20`. Both models were cached for the final run.

| Query | Cosine first result | Reranked first result |
| --- | --- | --- |
| Register a FastMCP tool | Release note about validating tool names | Tool-registration API documentation (previously second) |
| Python `break` | Definition, Python PDF page 28 | Loop example, Python PDF page 29 |
| JavaScript `let` versus `const` | Scope/reassignment discussion, JavaScript PDF page 44 | Variable-declaration comparison, same page |

All 30 returned snippets across both modes matched their original chunk text,
ID, source, page, and chunk index. The FastMCP change is a useful example of
improved first-result relevance. This small manual check is **not** a general
quality benchmark: reranking still put a JavaScript passage second for the Python
question, and some lower FastMCP matches discuss authentication rather than tools.
Use the source filter when language/document scope is known, and retain the
baseline for evaluating future models and candidate-pool settings.

## Tradeoffs and limits

Reranking cannot recover a passage absent from the candidate pool. Increasing
`candidate_k` gives it more options but increases latency. The general-purpose
model can still misrank code, language-specific snippets, and API versions.
Source filtering can help when the desired document is known. The model tokenizer
truncates question/passage pairs exceeding its context window; the full original
chunk is nevertheless returned. No model was trained on this project's corpus.

This is an appropriate advanced technique for the observed ordering problem, not
a claim that it is universally better. Hybrid keyword/vector search would address
a different weakness: candidate recall for exact identifiers and error messages.
A larger, independently judged query set is needed to measure quality reliably.

## Tests

Run `python -m pytest` and `python -m mypy` as usual.
`tests/test_rag_retrieval.py` exercises real Chroma, `Retriever`, and the MCP server.
Only embedding and pair-scoring inference are replaced with deterministic test
models. Tests demonstrate a relevant candidate moving from outside the baseline
final results to first place, while preserving its text, ID, cosine score, source,
and page. They cover candidate limits, filters, empty results, ties, malformed
scores, model failure, explicit baseline mode, and the default MCP mode. A small
adapter test checks lazy model loading and the actual query/passage call shape.
Default tests require no downloads, keys, or live LLM calls.
