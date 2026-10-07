"""Local semantic embeddings."""

from collections.abc import Sequence
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray

from rag_server.models import DocumentChunk

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingModel(Protocol):
    model_name: str
    max_tokens: int

    def count_tokens(self, text: str) -> int: ...

    def encode(self, texts: list[str], *, batch_size: int) -> object: ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, trust_remote_code=False)
        self.max_tokens = int(self._model.max_seq_length)

    def count_tokens(self, text: str) -> int:
        # Include special tokens because they consume the encoder's context budget.
        return len(self._model.tokenizer.encode(text, truncation=False, verbose=False))

    def encode(self, texts: list[str], *, batch_size: int) -> object:
        return self._model.encode(
            texts, batch_size=batch_size, convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=True,
        )


def embed_chunks(
    chunks: Sequence[DocumentChunk], model: EmbeddingModel, *, batch_size: int = 32,
) -> NDArray[np.float32]:
    if not chunks or batch_size < 1:
        raise ValueError("Non-empty chunks and a positive batch size are required")
    if any(model.count_tokens(chunk.text) > model.max_tokens for chunk in chunks):
        raise ValueError("A chunk exceeds the embedding model's token limit")
    vectors = np.asarray(
        model.encode([chunk.text for chunk in chunks], batch_size=batch_size),
        dtype=np.float32,
    )
    if vectors.ndim != 2 or vectors.shape[0] != len(chunks) or vectors.shape[1] < 1:
        raise ValueError("Expected one non-empty embedding vector per chunk")
    if not np.isfinite(vectors).all():
        raise ValueError("Embedding vectors must contain only finite values")
    norms = np.linalg.norm(vectors.astype(np.float64), axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("Embedding vectors must not be zero vectors")
    return cast(NDArray[np.float32], np.ascontiguousarray(vectors / norms, dtype=np.float32))

