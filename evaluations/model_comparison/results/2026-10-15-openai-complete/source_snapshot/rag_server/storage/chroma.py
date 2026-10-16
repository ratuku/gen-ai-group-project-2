"""Persist prepared vectors in Chroma and publish complete corpus snapshots."""

import hashlib
import json
import os
from pathlib import Path
import tempfile

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Metadata
from chromadb.config import Settings
from chromadb.errors import NotFoundError

from rag_server.storage.bundle import load_prepared_corpus

DEFAULT_STORE = Path(__file__).resolve().parents[1] / "artifacts" / "chroma"


def build_index(prepared: Path, directory: Path = DEFAULT_STORE) -> dict[str, object]:
    """Import precomputed vectors; unchanged artifacts reuse the same collection.

    Build a new collection before atomically changing active.json. A failed import
    cannot expose a partial corpus or remove the previous searchable snapshot.
    Run one builder at a time; old snapshots are retained for existing readers.
    """
    prepared, directory = Path(prepared), Path(directory)
    corpus = load_prepared_corpus(prepared)
    digest = hashlib.sha256(prepared.read_bytes()).hexdigest()
    name = f"rag-{digest[:32]}"
    client = chromadb.PersistentClient(path=str(directory), settings=Settings(anonymized_telemetry=False))
    try:
        collection = client.get_collection(name, embedding_function=None)
    except NotFoundError:
        collection = client.create_collection(
            name, embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"schema_version": 1, "model": corpus.model_name,
                      "dimension": int(corpus.embeddings.shape[1]),
                      "chunk_count": len(corpus.chunks), "document_count": corpus.document_count,
                      "bundle_sha256": digest, "ready": False},
        )
        try:
            batch_size = min(1000, client.get_max_batch_size())
            for start in range(0, len(corpus.chunks), batch_size):
                chunks = corpus.chunks[start:start + batch_size]
                metadatas: list[Metadata] = []
                for chunk in chunks:
                    metadata: Metadata = {"source": chunk.source, "chunk_index": chunk.chunk_index}
                    if chunk.page is not None:
                        metadata["page"] = chunk.page
                    metadatas.append(metadata)
                collection.add(
                    ids=[chunk.chunk_id for chunk in chunks],
                    embeddings=corpus.embeddings[start:start + batch_size],
                    documents=[chunk.text for chunk in chunks], metadatas=metadatas,
                )
            collection.modify(metadata={**(collection.metadata or {}), "ready": True})
        except BaseException:
            client.delete_collection(name)
            raise
    if not (collection.metadata or {}).get("ready") or collection.count() != len(corpus.chunks):
        raise ValueError("Stored snapshot is incomplete; use a fresh --store directory to rebuild")
    pointer: dict[str, object] = {"schema_version": 1, "collection": name}
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, encoding="utf-8", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(pointer, stream)
        os.replace(temporary, directory / "active.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"collection": name, "chunk_count": collection.count(), "model": corpus.model_name}


def open_collection(directory: Path = DEFAULT_STORE) -> Collection:
    """Open only a published, complete snapshot; never create an empty search DB."""
    directory = Path(directory)
    try:
        pointer = json.loads((directory / "active.json").read_text(encoding="utf-8"))
        if pointer.get("schema_version") != 1 or not isinstance(pointer.get("collection"), str):
            raise ValueError("Invalid active snapshot metadata")
        client = chromadb.PersistentClient(path=str(directory), settings=Settings(anonymized_telemetry=False))
        collection = client.get_collection(pointer["collection"], embedding_function=None)
        metadata = collection.metadata or {}
        if metadata.get("schema_version") != 1 or metadata.get("ready") is not True:
            raise ValueError("Snapshot is not ready")
        if collection.count() < 1 or collection.count() != metadata.get("chunk_count"):
            raise ValueError("Snapshot chunk count is inconsistent")
        if not isinstance(metadata.get("model"), str) or not metadata["model"]:
            raise ValueError("Snapshot embedding model is missing")
        if not isinstance(metadata.get("dimension"), int) or metadata["dimension"] < 1:
            raise ValueError("Snapshot embedding dimension is invalid")
        return collection
    except (OSError, ValueError, KeyError, TypeError, AttributeError, NotFoundError) as error:
        raise ValueError(
            f"RAG index is missing or invalid at {directory}. "
            "Run python -m rag_server.index first. "
            f"Details: {error}"
        ) from error
