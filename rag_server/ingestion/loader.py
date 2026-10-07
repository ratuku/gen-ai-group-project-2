"""Load text and PDF documents recursively without changing the originals."""

from pathlib import Path
import warnings

from pypdf import PdfReader

from rag_server.models import SourceDocument

SUPPORTED_EXTENSIONS = {".txt", ".md", ".mdx", ".pdf"}


def load_documents(directory: Path) -> list[SourceDocument]:
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError(f"Document directory does not exist: {directory}")
    paths = sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not paths:
        raise ValueError(f"No supported documents found in: {directory}")
    documents: list[SourceDocument] = []
    for path in paths:
        source = path.relative_to(directory).as_posix()
        try:
            if path.suffix.lower() == ".pdf":
                with path.open("rb") as stream:
                    reader = PdfReader(stream)
                    if reader.is_encrypted and not reader.decrypt(""):
                        raise ValueError("Password-protected PDF is not supported")
                    pages = [
                        SourceDocument(source, page.extract_text() or "", number)
                        for number, page in enumerate(reader.pages, start=1)
                    ]
                nonempty = [page for page in pages if page.text.strip()]
                if not nonempty:
                    raise ValueError("PDF has no extractable text; OCR is required")
                empty_count = len(pages) - len(nonempty)
                if empty_count:
                    warnings.warn(
                        f"{source}: skipped {empty_count} pages without text "
                        "(blank or scanned pages; scanned content needs OCR).",
                        stacklevel=2,
                    )
                documents.extend(nonempty)
            else:
                text = path.read_text(encoding="utf-8-sig")
                if not text.strip():
                    raise ValueError("Document is empty")
                documents.append(SourceDocument(source, text))
        except Exception as error:
            raise ValueError(f"Could not load {source}: {error}") from error
    return documents

