"""Read and validate the step-1 artifact without loading an embedding model."""

import json
from pathlib import Path, PurePosixPath

import numpy as np

from rag_server.models import DocumentChunk
from rag_server.prepare import PreparedCorpus


def load_prepared_corpus(path: Path) -> PreparedCorpus:
    try:
        with np.load(path, allow_pickle=False) as bundle:
            vectors = np.asarray(bundle["embeddings"], dtype=np.float32)
            records = json.loads(str(bundle["chunks_json"]))
            manifest = json.loads(str(bundle["manifest_json"]))
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            raise ValueError("Unsupported prepared-corpus schema")
        if not isinstance(records, list) or not records:
            raise ValueError("Prepared corpus must contain chunks")
        embedding = manifest["embedding"]
        if not isinstance(embedding, dict):
            raise ValueError("Missing embedding metadata")
        model = embedding.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Missing embedding model name")
        if (vectors.ndim != 2 or vectors.shape[0] != len(records)
                or vectors.shape[1] < 1 or vectors.shape[1] != embedding.get("dimension")
                or len(records) != manifest.get("chunk_count")):
            raise ValueError("Embedding dimensions/count do not match chunk metadata")
        if not np.isfinite(vectors).all():
            raise ValueError("Embeddings contain non-finite values")
        if embedding.get("normalized") is not True or not np.allclose(
            np.linalg.norm(vectors.astype(np.float64), axis=1), 1, atol=1e-5,
        ):
            raise ValueError("Expected nonzero, normalized embeddings from step 1")
        chunks: list[DocumentChunk] = []
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Chunk must be an object")
            for field in ("chunk_id", "text", "source"):
                if not isinstance(record.get(field), str) or not record[field].strip():
                    raise ValueError(f"Chunk requires {field}")
            source = PurePosixPath(record["source"])
            if source.is_absolute() or ".." in source.parts:
                raise ValueError("Source must be relative to the documents directory")
            index, page = record.get("chunk_index"), record.get("page")
            if type(index) is not int or index < 0:
                raise ValueError("Chunk index must be a non-negative integer")
            if page is not None and (type(page) is not int or page < 1):
                raise ValueError("PDF page must be a positive integer")
            chunks.append(DocumentChunk(record["chunk_id"], record["text"], record["source"], page, index))
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise ValueError("Duplicate chunk IDs")
        document_count = len({chunk.source for chunk in chunks})
        if document_count != manifest.get("document_count"):
            raise ValueError("Document count does not match source references")
        chunking = manifest["chunking"]
        size, overlap = chunking["chunk_size"], chunking["chunk_overlap"]
        if type(size) is not int or type(overlap) is not int or not 0 <= overlap < size:
            raise ValueError("Invalid chunking metadata")
        return PreparedCorpus(chunks, vectors, document_count, model, size, overlap)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f"Invalid prepared corpus {path}: {error}") from error
