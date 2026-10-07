"""Token-budgeted splitting with paragraph and line boundaries preferred."""

from collections.abc import Callable, Sequence
from hashlib import sha256

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_server.models import DocumentChunk, SourceDocument

DEFAULT_CHUNK_SIZE = 200
DEFAULT_CHUNK_OVERLAP = 30


def split_documents(
    documents: Sequence[SourceDocument],
    *,
    count_tokens: Callable[[str], int],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    if chunk_size < 1 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("Require chunk_size > 0 and 0 <= chunk_overlap < chunk_size")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=count_tokens,
        separators=["\n\n", "\n", " ", ""],
        keep_separator=True,
        strip_whitespace=False,
    )
    chunks: list[DocumentChunk] = []
    for document in documents:
        for index, text in enumerate(splitter.split_text(document.text)):
            if not text.strip():
                continue
            if count_tokens(text) > chunk_size:
                raise ValueError(f"Chunk exceeds token budget: {document.source}")
            identity = f"{document.source}\0{document.page}\0{index}\0{text}"
            chunks.append(DocumentChunk(
                chunk_id=sha256(identity.encode("utf-8")).hexdigest(),
                text=text,
                source=document.source,
                page=document.page,
                chunk_index=index,
            ))
    if not chunks:
        raise ValueError("Document splitting did not produce any chunks")
    return chunks

