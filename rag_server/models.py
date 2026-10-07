"""Data passed between the RAG preparation stages."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDocument:
    """A text document or one PDF page; source is relative to the corpus root."""

    source: str
    text: str
    page: int | None = None


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    text: str
    source: str
    page: int | None
    chunk_index: int

