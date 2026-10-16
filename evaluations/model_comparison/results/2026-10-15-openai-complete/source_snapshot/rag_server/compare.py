"""Compare cosine and reranked retrieval through the real stdio MCP server."""

import argparse
import asyncio
from collections.abc import Sequence
import json
import os
from pathlib import Path
import sys
import time

from mcp import Client, StdioServerParameters

from rag_server.retrieval.rerank import DEFAULT_RERANKER
from rag_server.storage.chroma import DEFAULT_STORE


async def compare(
    queries: Sequence[str], *, store: Path = DEFAULT_STORE, top_k: int = 5,
    candidate_k: int = 20, reranker_model: str = DEFAULT_RERANKER,
) -> list[dict[str, object]]:
    # The MCP SDK otherwise forwards only a minimal environment to subprocesses.
    cache_env = {key: os.environ[key] for key in (
        "HF_HOME", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_CACHE",
    ) if key in os.environ}
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "rag_server.server", "--store", str(store.resolve()),
              "--reranker-model", reranker_model],
        env=cache_env,
    )
    comparisons: list[dict[str, object]] = []
    async with Client(server, read_timeout_seconds=300) as client:
        for query in queries:
            row: dict[str, object] = {"query": query}
            for mode in ("cosine", "rerank"):
                start = time.perf_counter()
                result = await client.call_tool("search_docs", {
                    "query": query, "mode": mode, "top_k": top_k, "candidate_k": candidate_k,
                })
                if result.is_error or result.structured_content is None:
                    raise ValueError(f"{mode} retrieval failed: {result.content}")
                row[mode] = {**result.structured_content, "elapsed_seconds": time.perf_counter() - start}
            comparisons.append(row)
    return comparisons


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", required=True, help="Repeat for multiple questions")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER)
    options = parser.parse_args(arguments)
    try:
        rows = asyncio.run(compare(options.query, store=options.store, top_k=options.top_k,
                                   candidate_k=options.candidate_k, reranker_model=options.reranker_model))
    except Exception as exc:
        parser.exit(1, f"Comparison failed: {exc}\n")
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
