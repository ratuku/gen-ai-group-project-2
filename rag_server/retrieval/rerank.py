"""Local cross-encoder scoring for the second stage of retrieval."""

from collections.abc import Sequence
from typing import Any, Protocol

DEFAULT_RERANKER = "cross-encoder/ms-marco-MiniLM-L6-v2"


class Reranker(Protocol):
    model_name: str

    def score(self, query: str, texts: Sequence[str]) -> Sequence[float]: ...


class CrossEncoderReranker:
    """Load on first use; score question/passage pairs without a generative LLM."""

    def __init__(self, model_name: str = DEFAULT_RERANKER) -> None:
        if not model_name.strip():
            raise ValueError("Reranker model name must not be empty")
        self.model_name = model_name
        self._model: Any = None

    def score(self, query: str, texts: Sequence[str]) -> Sequence[float]:
        if not texts:
            return []
        if self._model is None:
            from sentence_transformers import CrossEncoder
            from torch.nn import Identity

            self._model = CrossEncoder(
                self.model_name, trust_remote_code=False, activation_fn=Identity(),
            )
        # Long pairs are truncated by the model tokenizer to its context limit.
        scores = self._model.predict(
            [(query, text) for text in texts], batch_size=16,
            show_progress_bar=False, convert_to_numpy=True,
        )
        return [float(score) for score in scores]
