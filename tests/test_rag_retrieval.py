from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.api.models.Collection import Collection
from mcp import Client
import numpy as np
import pytest

from rag_server.embeddings.encoder import embed_chunks
from rag_server.models import DocumentChunk
from rag_server.prepare import PreparedCorpus, save_prepared_corpus
from rag_server.retrieval.search import Retriever
from rag_server.server import create_server
from rag_server.storage.bundle import load_prepared_corpus
from rag_server.storage.chroma import build_index, open_collection


class TinyEncoder:
    """Deterministic embeddings only; tests still use real Chroma and MCP."""

    model_name = "test-topics-v1"
    max_tokens = 200

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def encode(self, texts: list[str], *, batch_size: int) -> object:
        vectors = []
        for text in texts:
            text = text.lower()
            scores = [float(any(word in text for word in topic)) for topic in (
                ("pathlib", "path", "file"), ("async", "coroutine", "concurrent"),
                ("cache", "caching", "lru"),
            )]
            vectors.append(scores + [float(not any(scores))])
        return vectors


@pytest.fixture
def corpus() -> PreparedCorpus:
    chunks = [
        DocumentChunk("path-1", "Use pathlib.Path to work with filesystem paths.", "python/pathlib.txt", None, 0),
        DocumentChunk("async-1", "Use asyncio.gather to run coroutines concurrently.", "languages/Python.pdf", 12, 3),
        DocumentChunk("cache-1", "The functools.lru_cache decorator caches function results.", "python/functools.txt", None, 0),
    ]
    return PreparedCorpus(chunks, embed_chunks(chunks, TinyEncoder()), 3, TinyEncoder.model_name, 100, 10)


@pytest.fixture
def prepared(tmp_path: Path, corpus: PreparedCorpus) -> Path:
    path = tmp_path / "prepared.npz"
    save_prepared_corpus(corpus, path)
    return path


def test_persistence_exact_vectors_metadata_and_repeatable_import(
    tmp_path: Path, prepared: Path, corpus: PreparedCorpus,
) -> None:
    directory = tmp_path / "chroma"
    first = build_index(prepared, directory)
    second = build_index(prepared, directory)
    assert first == second
    collection = open_collection(directory)
    assert collection.count() == 3
    stored = collection.get(ids=["async-1"], include=["embeddings", "documents", "metadatas"])
    assert stored["documents"] == [corpus.chunks[1].text]
    assert stored["metadatas"] == [{"source": "languages/Python.pdf", "page": 12, "chunk_index": 3}]
    assert stored["embeddings"] is not None
    np.testing.assert_allclose(stored["embeddings"][0], corpus.embeddings[1])
    # Another client opens the same on-disk collection without rebuilding it.
    client = chromadb.PersistentClient(path=str(directory), settings=Settings(anonymized_telemetry=False))
    assert len(client.list_collections()) == 1


@pytest.mark.parametrize("query,expected", [
    ("How do I work with paths?", "path-1"),
    ("How do I run concurrent coroutines?", "async-1"),
    ("How can I cache results?", "cache-1"),
])
def test_similarity_ranking(tmp_path: Path, prepared: Path, query: str, expected: str) -> None:
    directory = tmp_path / "chroma"
    build_index(prepared, directory)
    matches = Retriever(directory, embedding_model=TinyEncoder()).search(query, top_k=3)
    assert matches[0].chunk_id == expected
    assert matches[0].similarity == pytest.approx(1.0)
    assert [hit.similarity for hit in matches] == sorted((hit.similarity for hit in matches), reverse=True)


def test_filter_threshold_and_traceable_full_snippets(tmp_path: Path, prepared: Path) -> None:
    directory = tmp_path / "chroma"
    build_index(prepared, directory)
    retriever = Retriever(directory, embedding_model=TinyEncoder())
    matches = retriever.search("coroutines", source="languages/Python.pdf", top_k=20)
    assert len(matches) == 1
    assert matches[0].page == 12
    assert matches[0].chunk_index == 3
    assert matches[0].text == "Use asyncio.gather to run coroutines concurrently."
    assert retriever.search("coroutines", source="missing.txt") == []
    assert retriever.search("unrelated gardening", min_similarity=0.9) == []


def test_new_snapshot_removes_stale_chunks_from_search(tmp_path: Path, prepared: Path, corpus: PreparedCorpus) -> None:
    directory = tmp_path / "chroma"
    first = build_index(prepared, directory)
    updated = replace(corpus, chunks=corpus.chunks[:1], embeddings=corpus.embeddings[:1], document_count=1)
    save_prepared_corpus(updated, prepared)
    second = build_index(prepared, directory)
    assert first["collection"] != second["collection"]
    assert open_collection(directory).count() == 1
    assert Retriever(directory, embedding_model=TinyEncoder()).search("coroutines", source="languages/Python.pdf") == []


def test_failed_build_keeps_previous_snapshot(
    tmp_path: Path, prepared: Path, corpus: PreparedCorpus, monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "chroma"
    first = build_index(prepared, directory)
    updated = replace(corpus, chunks=corpus.chunks[:1], embeddings=corpus.embeddings[:1], document_count=1)
    save_prepared_corpus(updated, prepared)
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Simulated database failure")
    monkeypatch.setattr(Collection, "add", fail)
    with pytest.raises(RuntimeError, match="database failure"):
        build_index(prepared, directory)
    assert open_collection(directory).name == first["collection"]
    assert open_collection(directory).count() == 3


@pytest.mark.parametrize("problem", ["count", "dimension", "nan", "zero", "duplicate_id", "page", "source", "model"])
def test_corrupt_bundle_rejected_before_database_write(tmp_path: Path, prepared: Path, problem: str) -> None:
    with np.load(prepared, allow_pickle=False) as bundle:
        vectors = bundle["embeddings"].copy()
        records = json.loads(str(bundle["chunks_json"]))
        manifest = json.loads(str(bundle["manifest_json"]))
    if problem == "count":
        vectors = vectors[:1]
    elif problem == "dimension":
        manifest["embedding"]["dimension"] = 99
    elif problem == "nan":
        vectors[0, 0] = float("nan")
    elif problem == "zero":
        vectors[0] = 0
    elif problem == "duplicate_id":
        records[1]["chunk_id"] = records[0]["chunk_id"]
    elif problem == "page":
        records[1]["page"] = -1
    elif problem == "source":
        records[0]["source"] = "../outside.txt"
    else:
        manifest["embedding"]["model"] = ""
    np.savez_compressed(prepared, embeddings=vectors, chunks_json=json.dumps(records), manifest_json=json.dumps(manifest))
    with pytest.raises(ValueError, match="Invalid prepared corpus"):
        build_index(prepared, tmp_path / "chroma")
    assert not (tmp_path / "chroma").exists()


def test_model_and_query_validation(tmp_path: Path, prepared: Path) -> None:
    directory = tmp_path / "chroma"
    build_index(prepared, directory)
    wrong = TinyEncoder()
    wrong.model_name = "different-model"
    with pytest.raises(ValueError, match="model must match"):
        Retriever(directory, embedding_model=wrong)
    retriever = Retriever(directory, embedding_model=TinyEncoder())
    for top_k in (0, 21):
        with pytest.raises(ValueError, match="top_k"):
            retriever.search("paths", top_k=top_k)
    with pytest.raises(ValueError, match="empty"):
        retriever.search(" ")
    with pytest.raises(ValueError, match="token limit"):
        retriever.search("paths " * 201)
    with pytest.raises(ValueError, match="min_similarity"):
        retriever.search("paths", min_similarity=float("nan"))
    class WrongDimension(TinyEncoder):
        def encode(self, texts: list[str], *, batch_size: int) -> object:
            return [[1.0, 0.0]]
    with pytest.raises(ValueError, match="dimension"):
        Retriever(directory, embedding_model=WrongDimension()).search("paths")


@pytest.mark.asyncio
async def test_real_mcp_retrieval_returns_relevant_traceable_results(tmp_path: Path, prepared: Path) -> None:
    directory = tmp_path / "chroma"
    build_index(prepared, directory)
    server = create_server(directory, embedding_model=TinyEncoder())
    async with Client(server) as client:
        listing = await client.list_tools()
        assert [tool.name for tool in listing.tools] == ["search_docs"]
        for query, expected in (("paths", "path-1"), ("coroutines", "async-1"), ("cache", "cache-1")):
            result = await client.call_tool("search_docs", {"query": query, "top_k": 1})
            assert not result.is_error
            assert result.structured_content is not None
            payload = result.structured_content
            matches = payload["results"]
            assert matches[0]["chunk_id"] == expected
            original = next(chunk for chunk in load_prepared_corpus(prepared).chunks if chunk.chunk_id == expected)
            assert matches[0]["text"] == original.text
            assert matches[0]["source"] == original.source
            assert matches[0]["page"] == original.page
        invalid = await client.call_tool("search_docs", {"query": "", "top_k": 1})
        assert invalid.is_error
        no_hits = await client.call_tool("search_docs", {"query": "gardening", "min_similarity": 0.9})
        assert no_hits.structured_content is not None
        assert no_hits.structured_content["results"] == []


@pytest.mark.asyncio
async def test_missing_index_allows_discovery_but_returns_actionable_tool_error(tmp_path: Path) -> None:
    async with Client(create_server(tmp_path / "missing", embedding_model=TinyEncoder())) as client:
        assert len((await client.list_tools()).tools) == 1
        result = await client.call_tool("search_docs", {"query": "paths"})
        assert result.is_error
        assert "rag_server.index" in str(result.content)
