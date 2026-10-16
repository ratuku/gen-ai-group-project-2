"""Custom RAG MCP server: search prepared documentation over stdio."""

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from rag_server.embeddings.encoder import EmbeddingModel
from rag_server.retrieval.search import Retriever
from rag_server.retrieval.rerank import DEFAULT_RERANKER, Reranker
from rag_server.storage.chroma import DEFAULT_STORE


def create_server(
    directory: Path = DEFAULT_STORE, *, embedding_model: EmbeddingModel | None = None,
    reranker: Reranker | None = None, reranker_model: str = DEFAULT_RERANKER,
) -> MCPServer[Any]:
    server: MCPServer[Any] = MCPServer("custom-rag")
    retriever: Retriever | None = None
    lock = asyncio.Lock()

    @server.tool()
    async def search_docs(
        query: str, top_k: int = 5, source: str | None = None,
        min_similarity: float | None = None,
        mode: Literal["cosine", "rerank"] = "rerank", candidate_k: int = 20,
    ) -> dict[str, object]:
        """Search programming documentation by meaning. Return original snippets,
        source filenames, PDF page numbers, chunk IDs and cosine similarity scores.
        top_k is 1-20; source optionally filters by exact relative filename.
        min_similarity optionally excludes weak matches (-1 to 1, not confidence).
        Default mode='rerank' scores question/snippet pairs with a local cross-encoder;
        mode='cosine' preserves the original vector-search baseline without reranking.
        candidate_k (top_k to 100, default 20) controls the reranking candidate pool.
        similarity always means cosine; rerank_score is a separate relevance score.
        Neither score is confidence. Cite source and page in answers. No matches means no supporting evidence.
        """
        def search() -> dict[str, object]:
            nonlocal retriever
            if retriever is None:
                retriever = Retriever(directory, embedding_model=embedding_model,
                                      reranker=reranker, reranker_model=reranker_model)
            return retriever.search_payload(query, top_k, source, min_similarity, mode, candidate_k)

        # Lazy loading keeps tool discovery available before an index is built.
        # Serialize inference and move it off the MCP event loop.
        async with lock:
            try:
                return await asyncio.to_thread(search)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc

    return server


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER)
    options = parser.parse_args(arguments)
    create_server(options.store, reranker_model=options.reranker_model).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
