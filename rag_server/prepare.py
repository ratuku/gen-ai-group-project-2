"""Step 1: load documents, split chunks, and generate embeddings for storage."""

import argparse
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile

import numpy as np
from numpy.typing import NDArray

from rag_server.chunking.splitter import (
    DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, split_documents,
)
from rag_server.embeddings.encoder import (
    DEFAULT_MODEL_NAME, EmbeddingModel, SentenceTransformerEmbedder, embed_chunks,
)
from rag_server.ingestion.loader import load_documents
from rag_server.models import DocumentChunk

DEFAULT_DOCUMENTS = Path(__file__).resolve().parent / "documents"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "artifacts" / "prepared.npz"


@dataclass(frozen=True)
class PreparedCorpus:
    chunks: list[DocumentChunk]
    embeddings: NDArray[np.float32]
    document_count: int
    model_name: str
    chunk_size: int
    chunk_overlap: int


def prepare_corpus(
    directory: Path = DEFAULT_DOCUMENTS,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    batch_size: int = 32,
    embedding_model: EmbeddingModel | None = None,
) -> PreparedCorpus:
    if chunk_size < 1 or not 0 <= chunk_overlap < chunk_size or batch_size < 1:
        raise ValueError("Invalid chunk size, overlap, or batch size")
    documents = load_documents(directory)
    model = embedding_model if embedding_model is not None else SentenceTransformerEmbedder(model_name)
    if chunk_size > model.max_tokens:
        raise ValueError(f"chunk_size must not exceed model limit ({model.max_tokens} tokens)")
    chunks = split_documents(
        documents, count_tokens=model.count_tokens,
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
    )
    embeddings = embed_chunks(chunks, model, batch_size=batch_size)
    return PreparedCorpus(
        chunks, embeddings, len({doc.source for doc in documents}),
        model.model_name, chunk_size, chunk_overlap,
    )


def save_prepared_corpus(corpus: PreparedCorpus, output: Path) -> None:
    """Export one atomic, pickle-free bundle; vector indexing is a later stage."""
    output = Path(output)
    if output.suffix.lower() != ".npz":
        raise ValueError("Prepared output must use the .npz extension")
    manifest = {
        "schema_version": 1,
        "document_count": corpus.document_count,
        "chunk_count": len(corpus.chunks),
        "embedding": {
            "model": corpus.model_name,
            "dimension": int(corpus.embeddings.shape[1]),
            "normalized": True,
            "dtype": "float32",
        },
        "chunking": {
            "splitter": "RecursiveCharacterTextSplitter",
            "unit": "model_tokens_including_special_tokens",
            "chunk_size": corpus.chunk_size,
            "chunk_overlap": corpus.chunk_overlap,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(
                stream,
                embeddings=corpus.embeddings,
                chunks_json=json.dumps([asdict(chunk) for chunk in corpus.chunks], ensure_ascii=False),
                manifest_json=json.dumps(manifest),
            )
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--batch-size", type=int, default=32)
    options = parser.parse_args(arguments)
    if options.output.suffix.lower() != ".npz":
        parser.error("--output must use the .npz extension")
    try:
        corpus = prepare_corpus(
            options.documents, model_name=options.model,
            chunk_size=options.chunk_size, chunk_overlap=options.chunk_overlap,
            batch_size=options.batch_size,
        )
        save_prepared_corpus(corpus, options.output)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Preparation failed: {error}\n")
    print(f"Loaded {corpus.document_count} documents; prepared {len(corpus.chunks)} chunks.")
    print(f"Embeddings: {corpus.embeddings.shape}; model: {corpus.model_name}")
    print(f"Prepared data: {options.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
