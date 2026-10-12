"""Cosine similarity retrieval with original chunk text and source references."""

from dataclasses import asdict, dataclass
import math
from pathlib import Path

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


class Retriever:
    """Load the persisted model identity and embed queries in the same space."""

    def __init__(self, directory: Path = DEFAULT_STORE, *, embedding_model: EmbeddingModel | None = None) -> None:
        self.collection = open_collection(directory)
        metadata = self.collection.metadata or {}
        self.model_name = str(metadata["model"])
        self.dimension = int(metadata["dimension"])
        if embedding_model is not None and embedding_model.model_name != self.model_name:
            raise ValueError("Query embedding model must match the indexed model")
        self._model = embedding_model

    def search(
        self, query: str, *, top_k: int = 5, source: str | None = None,
        min_similarity: float | None = None,
    ) -> list[SearchResult]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Query must not be empty")
        if type(top_k) is not int or not 1 <= top_k <= 20:
            raise ValueError("top_k must be an integer between 1 and 20")
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
            n_results=min(top_k, self.collection.count()),
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
        return matches

    def search_payload(
        self, query: str, top_k: int = 5, source: str | None = None,
        min_similarity: float | None = None,
    ) -> dict[str, object]:
        matches = self.search(query, top_k=top_k, source=source, min_similarity=min_similarity)
        return {
            "query": query, "embedding_model": self.model_name,
            "score_type": "cosine_similarity", "results": [asdict(match) for match in matches],
        }
