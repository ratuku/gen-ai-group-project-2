# RAG step 2: Chroma storage and MCP retrieval

Step 1 already produces chunks and embeddings in `rag_server/artifacts/prepared.npz`.
Step 2 imports those vectors into persistent Chroma storage and exposes a
`search_docs` MCP tool. The application's multi-server client names it
`rag.search_docs`. It returns evidence; the existing agent and selected LLM use
that evidence to write an answer.

## Run

From the repository root, with your Python environment activated:

```sh
python -m pip install -e '.[rag]'
# Only needed if documents or embedding settings have changed:
python -m rag_server.prepare
# Import existing embeddings without generating them again:
python -m rag_server.index
coding-assistant --connection-demo --task "list tools"
```

The committed MCP configuration includes filesystem, DeepWiki, and the local RAG
server. It starts RAG with `python -m rag_server.server`; that Python must belong
to the environment where the project and RAG extras are installed. The store
path is resolved relative to the configuration file, independent of the agent's
allowed filesystem workspace. The connection demo also contacts DeepWiki.

With a configured Groq or Ollama provider, try asking the CLI:

```sh
coding-assistant --provider groq --task "Use rag.search_docs to explain how to register a FastMCP tool. Cite the source."
```

This last command uses the configured LLM; indexing and retrieval themselves
need no cloud API key. Query embeddings run locally. The first query loads the
same SentenceTransformer model recorded during ingestion, downloading it if it
is not cached. Discovery works before indexing; a search then explains how to
build the missing index.

Custom paths are supported by `python -m rag_server.index --prepared PATH --store DIR`
and `python -m rag_server.server --store DIR`. Set the same store in MCP config.

## What happens

1. `storage/bundle.py` validates the prepared bundle: vector alignment, dimensions,
   normalization, unique IDs, source metadata, and manifest consistency.
2. `storage/chroma.py` stores supplied vectors, original chunk text, IDs, source
   filenames, chunk indexes, and optional PDF pages. Chroma's automatic embedding
   function is disabled, so document embeddings are reused exactly.
3. `retrieval/search.py` embeds a query using the stored model identity and runs
   Chroma's cosine nearest-neighbor search. Chroma uses an approximate HNSW index.
4. `server.py` exposes that retrieval through MCP over stdio. Local inference runs
   outside the asynchronous event loop, with searches serialized within a server.

An identical prepared file reuses its existing collection. A changed file builds
another collection and only switches `active.json` after a successful import.
Failed imports preserve the previous active index. Existing retrievers keep their
snapshot, so restart the MCP server/CLI after importing a changed corpus. Run one
index builder at a time. Old collections are retained; this basic version does
not automatically clean up snapshots. The store and prepared bundle live under
Git-ignored `rag_server/artifacts/` and must not be committed.

## Tool input and result

```json
{"query": "How do I register a FastMCP tool?", "top_k": 5}
```

`top_k` defaults to 5 and must be 1–20. Optional `source` filters by an exact
relative filename, such as `languages/Python.pdf`. Optional `min_similarity`
filters weak results; there is no universal threshold suitable for all queries.

The response contains `query`, `embedding_model`, `score_type: "cosine_similarity"`,
and a `results` list. Each result contains:

| Field | Meaning |
| --- | --- |
| `text` | Original chunk text, suitable as answer context |
| `source` | Filename relative to `rag_server/documents` |
| `page` | One-based PDF page, or null for text documents |
| `chunk_id` | Stable ingestion ID identifying the exact chunk |
| `chunk_index` | Zero-based position within the source/page |
| `similarity` | Cosine similarity, calculated as 1 minus Chroma distance |

Higher scores mean closer vectors; scores are not probabilities or guarantees
that a snippet answers the question. Empty filtered results mean no supporting
evidence was found. Without a cutoff, nearest-neighbor search can return unrelated
chunks for an out-of-corpus question. Retrieved text is source material, not
instructions to the agent.

## Why similarity search?

Dense cosine search is a suitable baseline for natural-language documentation
questions, including wording different from the source. It follows project 1's
local embedding/retrieval pattern; that project uses FAISS, while this uses Chroma
for persistence and metadata filtering. Query and document vectors must use the
same model, not merely the same dimension.

Exact identifiers, error messages, and version-specific API names may benefit
from hybrid keyword/vector retrieval. Cross-encoder reranking is another next
step. Basic dense retrieval does **not** fulfill the separate advanced-RAG
requirement; evaluate a later technique against this baseline.

## Tests

```sh
python -m pip install -r requirements-dev.txt -e '.[rag]'
python -m pytest
python -m mypy
```

`tests/test_rag_retrieval.py` uses the actual storage, retriever, server, Chroma
database, and an in-memory MCP client connection. Only the embedding model is
replaced by a deterministic encoder: no model downloads, API keys, or LLM calls.
Tests check persistence, exact vector/text/metadata preservation, repeatable
imports, corpus replacement, failure recovery, invalid bundles/queries, source
and score filtering, ranking across three topics, and traceable MCP results.
These tests validate retrieval mechanics, not the semantic quality of a live
embedding model or an LLM's interpretation of the results.
