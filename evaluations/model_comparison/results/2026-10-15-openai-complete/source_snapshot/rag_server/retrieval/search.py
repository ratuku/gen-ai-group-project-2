"""Cosine similarity retrieval with original chunk text and source references."""

from dataclasses import asdict, dataclass, replace
import math
from pathlib import Path
from typing import Literal

from rag_server.retrieval.rerank import CrossEncoderReranker, DEFAULT_RERANKER, Reranker

from rag_server.embeddings.encoder import EmbeddingModel, SentenceTransformerEmbedder, embed_texts
from rag_server.storage.chroma import DEFAULT_STORE, open_collection


@dataclass(frozen=True)
class SearchResult:
    chunk_id: str
    text: str
    source: str
    page: int | None
    chunk_index: int
    similarity: float
    rerank_score: float | None = None


class Retriever:
    """Load the persisted model identity and embed queries in the same space."""

    def __init__(
        self, directory: Path = DEFAULT_STORE, *, embedding_model: EmbeddingModel | None = None,
        reranker: Reranker | None = None, reranker_model: str = DEFAULT_RERANKER,
    ) -> None:
        self.collection = open_collection(directory)
        metadata = self.collection.metadata or {}
        self.model_name = str(metadata["model"])
        self.dimension = int(metadata["dimension"])
        if embedding_model is not None and embedding_model.model_name != self.model_name:
            raise ValueError("Query embedding model must match the indexed model")
        self._model = embedding_model
        self._reranker = reranker if reranker is not None else CrossEncoderReranker(reranker_model)

    def search(
        self, query: str, *, top_k: int = 5, source: str | None = None,
        min_similarity: float | None = None,
        mode: Literal["cosine", "rerank"] = "cosine", candidate_k: int = 20,
    ) -> list[SearchResult]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Query must not be empty")
        if type(top_k) is not int or not 1 <= top_k <= 20:
            raise ValueError("top_k must be an integer between 1 and 20")
        if mode not in ("cosine", "rerank"):
            raise ValueError("mode must be cosine or rerank")
        if type(candidate_k) is not int or not top_k <= candidate_k <= 100:
            raise ValueError("candidate_k must be an integer between top_k and 100")
        if source is not None and (not isinstance(source, str) or not source.strip()):
            raise ValueError("source must be a non-empty relative source name")
        if min_similarity is not None and (not math.isfinite(min_similarity) or not -1 <= min_similarity <= 1):
            raise ValueError("min_similarity must be between -1 and 1")
        if self._model is None:
            self._model = SentenceTransformerEmbedder(self.model_name)
        vectors = embed_texts([query.strip()], self._model, batch_size=1)
        if vectors.shape[1] != self.dimension:
            raise ValueError("Query embedding dimension does not match the indexed vectors")
        result = self.collection.query(
            query_embeddings=vectors,
            n_results=min(candidate_k if mode == "rerank" else top_k, self.collection.count()),
            where={"source": source} if source is not None else None,
            include=["documents", "metadatas", "distances"],
        )
        documents, metadata_rows, distance_rows = result["documents"], result["metadatas"], result["distances"]
        if documents is None or metadata_rows is None or distance_rows is None:
            raise ValueError("Chroma returned incomplete search results")
        matches: list[SearchResult] = []
        for chunk_id, text, metadata, distance in zip(
            result["ids"][0], documents[0], metadata_rows[0], distance_rows[0], strict=True,
        ):
            if text is None or metadata is None or not math.isfinite(distance):
                raise ValueError("Stored chunk is missing text, metadata, or a valid distance")
            similarity = max(-1.0, min(1.0, 1.0 - distance))
            if min_similarity is not None and similarity < min_similarity:
                continue
            matches.append(SearchResult(
                chunk_id, text, str(metadata["source"]),
                int(metadata["page"]) if "page" in metadata else None,
                int(metadata["chunk_index"]), similarity,
            ))
        if mode == "rerank" and matches:
            try:
                # Filenames supply language context often absent from short code snippets.
                passages = [f"Source: {match.source}\n\n{match.text}" for match in matches]
                scores = list(self._reranker.score(query.strip(), passages))
                if len(scores) != len(matches) or any(not math.isfinite(score) for score in scores):
                    raise ValueError("Expected one finite rerank score per candidate")
                # Stable sorting preserves cosine order when reranker scores tie.
                matches = [replace(match, rerank_score=float(score))
                           for match, score in zip(matches, scores, strict=True)]
                matches.sort(key=lambda match: float(match.rerank_score or 0), reverse=True)
            except Exception as exc:
                raise ValueError(
                    f"Reranking failed with {self._reranker.model_name}. "
                    "Check the model/cache or explicitly retry with mode='cosine'. "
                    f"Details: {exc}"
                ) from exc
        return matches[:top_k]

    def search_payload(
        self, query: str, top_k: int = 5, source: str | None = None,
        min_similarity: float | None = None,
        mode: Literal["cosine", "rerank"] = "cosine", candidate_k: int = 20,
    ) -> dict[str, object]:
        matches = self.search(query, top_k=top_k, source=source, min_similarity=min_similarity,
                              mode=mode, candidate_k=candidate_k)
        return {
            "query": query, "embedding_model": self.model_name,
            "mode": mode, "candidate_k": candidate_k if mode == "rerank" else top_k,
            "reranker_model": self._reranker.model_name if mode == "rerank" else None,
            "ranking_score": "rerank_score" if mode == "rerank" else "similarity",
            "score_type": "cosine_similarity", "results": [asdict(match) for match in matches],
        }
