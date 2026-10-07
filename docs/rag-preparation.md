# RAG step 1: prepare documents and embeddings

This adapts project 1's local SentenceTransformer ingestion design. It loads the
corpus, splits it, and produces normalized semantic vectors. It does not create a
vector index, retrieve documents, or start an MCP server yet.

## Install and run

From the repository root in your Python 3.11+ virtual environment:

```sh
python -m pip install -e '.[rag]'
python -m rag_server.prepare
```

The default corpus is `rag_server/documents`, discovered recursively. Supported
formats are UTF-8 `.txt`, `.md`, `.mdx`, and text-based `.pdf` (case-insensitive).
Large combined text files work directly. Original documents are never modified.
PDF pages keep their original one-based page numbers. Empty pages produce a
warning; entirely image-based PDFs fail with an OCR message. OCR is not included.
Unsupported extensions are ignored; invalid supported documents fail the run.

The default model is `sentence-transformers/all-MiniLM-L6-v2`, matching project 1.
The first run downloads model weights from Hugging Face; embedding computation is
local and requires no cloud API key. Subsequent runs can use the cached model.

Chunks target 200 model tokens with up to 30 tokens of overlap, preferring
paragraph/line boundaries. Token counts include special tokens and are checked
against the model's limit before encoding to prevent silent truncation. Overlap
is best-effort at structural boundaries. Indentation is retained, but PDF text
extraction may change code layout; review extraction quality before evaluation.
Embeddings are computed in batches of 32, converted to float32, checked for valid
shape and finite nonzero values, and normalized for later cosine search.

```sh
python -m rag_server.prepare --documents rag_server/documents \
  --output rag_server/artifacts/prepared.npz --batch-size 32
```

The command atomically replaces the generated bundle only after successful
preparation. A failed run leaves the previous bundle intact. The corpus and
embeddings are held in memory, so this implementation is intended for a modest
documentation collection rather than a streaming ingestion service.

## The output contract for step 2

`rag_server/artifacts/prepared.npz` is a single compressed data bundle:

- `embeddings`: a matrix with one row per chunk, in chunk order.
- `chunks_json`: a JSON string containing IDs, text, relative source paths,
  PDF page numbers (null for text), and chunk indexes within each source/page.
- `manifest_json`: schema version, document/chunk counts, embedding model and
  dimension, normalization flag, and chunking settings.

```python
import json
import numpy as np

with np.load("rag_server/artifacts/prepared.npz", allow_pickle=False) as bundle:
    vectors = bundle["embeddings"]
    chunks = json.loads(str(bundle["chunks_json"]))
    manifest = json.loads(str(bundle["manifest_json"]))
# vectors[i] belongs to chunks[i]; step 2 can add these to FAISS or another store.
```

The programmatic entry point `prepare_corpus()` returns the same data in memory;
`save_prepared_corpus()` is optional. IDs are deterministic for unchanged source,
page, chunk position, and text. Rebuild the bundle when the corpus or embedding
configuration changes, and embed queries with the same model used for documents.

## How this fits the assignment

The embedding model and answer-generating LLM have separate responsibilities.
Project 1 uses local SentenceTransformer embeddings and Groq-hosted generation.
Project 2's `ModelProvider` protocol is the starting point for Ollama and cloud
adapters; concrete adapters remain separate work. Groq can be the cloud provider.

The remaining RAG stages are vector storage, retrieval, and MCP tool exposure.
Ordinary splitting and dense retrieval do not by themselves fulfill the advanced
RAG requirement. A later step can add cross-encoder reranking: retrieve candidate
chunks, score their relevance to the question, and return the best few. Evaluate
that against the baseline before claiming an improvement.

## Tests

```sh
python -m pip install -r requirements-dev.txt -e '.[rag]'
python -m pytest
python -m mypy
```

Tests inject a deterministic fake encoder to check metadata, normalization,
alignment, error handling, and bundle round-tripping without model downloads.
Running the CLI additionally exercises the real embedding model and corpus.
