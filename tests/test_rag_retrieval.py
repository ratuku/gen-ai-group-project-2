from __future__ import annotations

from collections.abc import Sequence
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
            result = await client.call_tool("search_docs", {"query": query, "top_k": 1, "mode": "cosine"})
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


class PairScorer:
    """Replace model inference only, keeping the real retrieval/MCP path."""

    model_name = "test-pair-scorer"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        self.calls.append((query, list(texts)))
        return [8.0 if "Path.read_text" in text else -2.0 for text in texts]


@pytest.fixture
def ambiguous_store(tmp_path: Path) -> Path:
    chunks = [
        DocumentChunk("distractor", "Release notes: pathlib tools renamed.", "notes.txt", None, 0),
        DocumentChunk("answer", "Use pathlib.Path.read_text() to read a file as a string.", "Python.pdf", 9, 2),
        DocumentChunk("other", "Run async coroutines concurrently.", "async.txt", None, 0),
    ]
    vectors = np.array([[1, 0, 0, 0], [0.8, 0.6, 0, 0], [0, 1, 0, 0]], dtype=np.float32)
    prepared = tmp_path / "ambiguous.npz"
    save_prepared_corpus(PreparedCorpus(chunks, vectors, 3, TinyEncoder.model_name, 100, 10), prepared)
    store = tmp_path / "ambiguous-store"
    build_index(prepared, store)
    return store


def test_reranking_promotes_candidate_outside_baseline_top_k_and_preserves_evidence(ambiguous_store: Path) -> None:
    scorer = PairScorer()
    retriever = Retriever(ambiguous_store, embedding_model=TinyEncoder(), reranker=scorer)
    baseline = retriever.search("read a file", top_k=1)
    assert baseline[0].chunk_id == "distractor"
    assert baseline[0].rerank_score is None
    assert scorer.calls == []
    candidates = retriever.search("read a file", top_k=2)
    advanced = retriever.search("read a file", top_k=1, mode="rerank", candidate_k=2)
    assert advanced[0] == replace(candidates[1], rerank_score=8.0)
    assert (advanced[0].source, advanced[0].page, advanced[0].chunk_index) == ("Python.pdf", 9, 2)
    assert advanced[0].similarity == pytest.approx(0.8)
    assert scorer.calls == [("read a file", [f"Source: {hit.source}\n\n{hit.text}" for hit in candidates])]
    # A candidate never retrieved cannot be rescued by the second stage.
    assert retriever.search("read a file", top_k=1, mode="rerank", candidate_k=1)[0].chunk_id == "distractor"


def test_reranking_respects_filters_empty_results_and_small_corpus(ambiguous_store: Path) -> None:
    scorer = PairScorer()
    retriever = Retriever(ambiguous_store, embedding_model=TinyEncoder(), reranker=scorer)
    matches = retriever.search("file", mode="rerank", source="Python.pdf")
    assert [hit.chunk_id for hit in matches] == ["answer"]
    assert len(scorer.calls[0][1]) == 1
    assert retriever.search("file", mode="rerank", source="absent.txt") == []
    assert len(scorer.calls) == 1
    matches = retriever.search("file", mode="rerank", min_similarity=0.9)
    assert [hit.chunk_id for hit in matches] == ["distractor"]
    assert len(scorer.calls[-1][1]) == 1
    assert len(retriever.search("file", mode="rerank", top_k=20, candidate_k=100)) == 3


@pytest.mark.parametrize("candidate_k", [0, 1, 101, True, 2.5])
def test_invalid_candidate_pool(ambiguous_store: Path, candidate_k: int) -> None:
    retriever = Retriever(ambiguous_store, embedding_model=TinyEncoder(), reranker=PairScorer())
    with pytest.raises(ValueError, match="candidate_k"):
        retriever.search("file", top_k=2, candidate_k=candidate_k, mode="rerank")


@pytest.mark.parametrize("scores", [[1.0], [float("nan"), 0.0], [float("inf"), 0.0]])
def test_invalid_rerank_scores_fail_without_silent_fallback(ambiguous_store: Path, scores: list[float]) -> None:
    class InvalidScorer(PairScorer):
        def score(self, query: str, texts: Sequence[str]) -> list[float]:
            return scores
    retriever = Retriever(ambiguous_store, embedding_model=TinyEncoder(), reranker=InvalidScorer())
    with pytest.raises(ValueError, match="one finite rerank score"):
        retriever.search("file", top_k=1, candidate_k=2, mode="rerank")
    assert retriever.search("file", top_k=1, mode="cosine")[0].chunk_id == "distractor"


def test_rerank_ties_keep_cosine_order(ambiguous_store: Path) -> None:
    class TiedScorer(PairScorer):
        def score(self, query: str, texts: Sequence[str]) -> list[float]:
            return [-1.0] * len(texts)
    retriever = Retriever(ambiguous_store, embedding_model=TinyEncoder(), reranker=TiedScorer())
    assert [hit.chunk_id for hit in retriever.search("file", mode="rerank")] == [
        "distractor", "answer", "other",
    ]


@pytest.mark.asyncio
async def test_mcp_default_reranking_and_explicit_baseline(ambiguous_store: Path) -> None:
    scorer = PairScorer()
    async with Client(create_server(ambiguous_store, embedding_model=TinyEncoder(), reranker=scorer)) as client:
        tool = (await client.list_tools()).tools[0]
        assert tool.input_schema["properties"]["mode"]["default"] == "rerank"
        for mode, expected in (("cosine", "distractor"), ("rerank", "answer")):
            args: dict[str, object] = {"query": "read a file", "top_k": 1, "candidate_k": 2}
            if mode == "cosine":
                args["mode"] = mode
            response = await client.call_tool("search_docs", args)
            assert not response.is_error
            payload = response.structured_content
            assert payload is not None
            assert payload["mode"] == mode
            assert payload["ranking_score"] == ("similarity" if mode == "cosine" else "rerank_score")
            assert payload["reranker_model"] == (None if mode == "cosine" else scorer.model_name)
            assert payload["results"][0]["chunk_id"] == expected
        assert len(scorer.calls) == 1
        invalid_inputs: list[dict[str, object]] = [
            {"query": "file", "mode": "invalid"}, {"query": "file", "candidate_k": 0},
        ]
        for invalid_args in invalid_inputs:
            assert (await client.call_tool("search_docs", invalid_args)).is_error


@pytest.mark.asyncio
async def test_mcp_reranker_failure_is_actionable_and_baseline_still_works(ambiguous_store: Path) -> None:
    class BrokenScorer(PairScorer):
        def score(self, query: str, texts: Sequence[str]) -> list[float]:
            raise OSError("Model unavailable")
    async with Client(create_server(ambiguous_store, embedding_model=TinyEncoder(), reranker=BrokenScorer())) as client:
        result = await client.call_tool("search_docs", {"query": "file"})
        assert result.is_error
        assert "mode='cosine'" in str(result.content)
        result = await client.call_tool("search_docs", {"query": "file", "mode": "cosine"})
        assert not result.is_error


def test_cross_encoder_adapter_loads_once_and_scores_query_passage_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import SimpleNamespace
    from rag_server.retrieval.rerank import CrossEncoderReranker

    constructors: list[str] = []
    pairs_seen: list[list[tuple[str, str]]] = []
    class FakeCrossEncoder:
        def __init__(self, model_name: str, **kwargs: object) -> None:
            constructors.append(model_name)
            assert kwargs["trust_remote_code"] is False
        def predict(self, pairs: list[tuple[str, str]], **kwargs: object) -> list[float]:
            pairs_seen.append(pairs)
            assert kwargs["show_progress_bar"] is False
            return [2.0] * len(pairs)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(CrossEncoder=FakeCrossEncoder))
    reranker = CrossEncoderReranker("test-model")
    assert constructors == []
    assert reranker.score("question", []) == []
    assert constructors == []
    assert reranker.score("question", ["passage", "another"]) == [2.0, 2.0]
    assert reranker.score("next", ["last"]) == [2.0]
    assert constructors == ["test-model"]
    assert pairs_seen == [[("question", "passage"), ("question", "another")], [("next", "last")]]
