from pathlib import Path
import json

import numpy as np
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from rag_server.chunking.splitter import split_documents
from rag_server.embeddings.encoder import embed_chunks
from rag_server.ingestion.loader import load_documents
from rag_server.models import DocumentChunk, SourceDocument
from rag_server.prepare import prepare_corpus, save_prepared_corpus
from rag_server import prepare


class FakeEmbedder:
    model_name = "test-only"
    max_tokens = 200

    def count_tokens(self, text: str) -> int:
        return len(text)

    def encode(self, texts: list[str], *, batch_size: int) -> object:
        return [[len(text), 1.0, 2.0] for text in texts]


def write_pdf(path: Path, *, blank: bool = False) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    if not blank:
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 10 200 Td (Use Python functions.) Tj ET")
        page[NameObject("/Contents")] = stream
        writer.add_blank_page(width=300, height=300)
    with path.open("wb") as output:
        writer.write(output)


def test_recursive_loading_and_pdf_page_metadata(tmp_path: Path) -> None:
    nested = tmp_path / "languages"
    nested.mkdir()
    (tmp_path / "guide.txt").write_text("A text document", encoding="utf-8")
    (nested / "guide.MD").write_text("# Python\nExamples", encoding="utf-8")
    (tmp_path / "ignored.json").write_text("{}", encoding="utf-8")
    write_pdf(nested / "python.pdf")
    with pytest.warns(UserWarning, match="skipped 1 pages"):
        docs = load_documents(tmp_path)
    assert [(doc.source, doc.page) for doc in docs] == [
        ("guide.txt", None), ("languages/guide.MD", None), ("languages/python.pdf", 1),
    ]
    assert "Use Python functions." in docs[-1].text


def test_scanned_or_blank_pdf_is_not_silently_dropped(tmp_path: Path) -> None:
    write_pdf(tmp_path / "scan.pdf", blank=True)
    with pytest.raises(ValueError, match="scan.pdf.*OCR"):
        load_documents(tmp_path)


def test_missing_empty_and_bad_documents(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        load_documents(tmp_path / "missing")
    with pytest.raises(ValueError, match="No supported"):
        load_documents(tmp_path)
    path = tmp_path / "empty.txt"
    path.write_text("   ", encoding="utf-8")
    with pytest.raises(ValueError, match="empty.txt.*empty"):
        load_documents(tmp_path)
    path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="empty.txt"):
        load_documents(tmp_path)


def test_chunk_overlap_bounds_ids_and_content_coverage() -> None:
    text = "abcdefghijklmnopqrstuvwxyz0123456789"
    docs = [SourceDocument("a.txt", text), SourceDocument("b.txt", text)]
    chunks = split_documents(docs, count_tokens=len, chunk_size=10, chunk_overlap=3)
    first = [chunk for chunk in chunks if chunk.source == "a.txt"]
    assert first[0].text[-3:] == first[1].text[:3]
    assert first[0].text + "".join(chunk.text[3:] for chunk in first[1:]) == text
    assert all(len(chunk.text) <= 10 for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert chunks == split_documents(docs, count_tokens=len, chunk_size=10, chunk_overlap=3)


@pytest.mark.parametrize("size,overlap", [(0, 0), (10, -1), (10, 10)])
def test_invalid_chunk_settings(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        split_documents([], count_tokens=len, chunk_size=size, chunk_overlap=overlap)


@pytest.mark.parametrize("result", [[], [[0, 0]], [[float("nan"), 1]], [[1, 2], [3, 4]], [1, 2]])
def test_invalid_embeddings_rejected(result: object) -> None:
    class InvalidEmbedder(FakeEmbedder):
        def encode(self, texts: list[str], *, batch_size: int) -> object:
            return result
    with pytest.raises(ValueError):
        embed_chunks([DocumentChunk("id", "text", "a.txt", None, 0)], InvalidEmbedder())


def test_end_to_end_alignment_and_safe_bundle(tmp_path: Path) -> None:
    source = tmp_path / "documents"
    source.mkdir()
    (source / "guide.txt").write_text("Learn Python. " * 30, encoding="utf-8")
    corpus = prepare_corpus(source, embedding_model=FakeEmbedder(), chunk_size=50, chunk_overlap=10)
    assert corpus.document_count == 1
    assert corpus.embeddings.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(corpus.embeddings, axis=1), 1, rtol=1e-6)
    for chunk, vector in zip(corpus.chunks, corpus.embeddings):
        expected = np.array([len(chunk.text), 1, 2], dtype=np.float32)
        np.testing.assert_allclose(vector, expected / np.linalg.norm(expected), rtol=1e-6)
    output = tmp_path / "prepared.npz"
    save_prepared_corpus(corpus, output)
    with np.load(output, allow_pickle=False) as bundle:
        records = json.loads(str(bundle["chunks_json"]))
        manifest = json.loads(str(bundle["manifest_json"]))
        np.testing.assert_array_equal(bundle["embeddings"], corpus.embeddings)
    assert records[0]["source"] == "guide.txt"
    assert len(records) == len(corpus.chunks)
    assert manifest["embedding"]["model"] == "test-only"


def test_preparation_refuses_model_truncation(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("A document", encoding="utf-8")
    with pytest.raises(ValueError, match="model limit"):
        prepare_corpus(tmp_path, embedding_model=FakeEmbedder(), chunk_size=201)


def test_utf8_bom_and_code_indentation_survive_loading(tmp_path: Path) -> None:
    text = "# Café\n\ndef hello():\n    return '你好'\n"
    (tmp_path / "guide.mdx").write_text(text, encoding="utf-8-sig")
    docs = load_documents(tmp_path)
    assert docs[0].text == text
    chunks = split_documents(docs, count_tokens=len, chunk_size=100, chunk_overlap=10)
    assert chunks[0].text == text


def test_encrypted_pdf_reports_filename(tmp_path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.encrypt("test-password")
    with (tmp_path / "locked.pdf").open("wb") as stream:
        writer.write(stream)
    with pytest.raises(ValueError, match="locked.pdf.*Password-protected"):
        load_documents(tmp_path)


def test_corrupt_pdf_reports_filename(tmp_path: Path) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"Not a PDF")
    with pytest.raises(ValueError, match="Could not load broken.pdf"):
        load_documents(tmp_path)


def test_same_text_on_different_pdf_pages_has_distinct_ids() -> None:
    text = "def greeting():\n    return 'hello'\n"
    documents = [SourceDocument("guide.pdf", text, page) for page in (2, 4)]
    chunks = split_documents(documents, count_tokens=len, chunk_size=100, chunk_overlap=10)
    assert [chunk.page for chunk in chunks] == [2, 4]
    assert chunks[0].chunk_id != chunks[1].chunk_id
    assert all(chunk.source == "guide.pdf" for chunk in chunks)


def test_oversized_chunk_is_rejected_before_encoding() -> None:
    class NeverEncode(FakeEmbedder):
        def encode(self, texts: list[str], *, batch_size: int) -> object:
            raise AssertionError("Oversized input must not reach the embedding model")
    chunk = DocumentChunk("id", "x" * 201, "guide.txt", None, 0)
    with pytest.raises(ValueError, match="token limit"):
        embed_chunks([chunk], NeverEncode())


def test_embedding_preserves_order_and_forwards_batch_size() -> None:
    class RecordingEmbedder(FakeEmbedder):
        def encode(self, texts: list[str], *, batch_size: int) -> object:
            assert texts == ["first", "second"]
            assert batch_size == 7
            return [[3.0, 4.0], [0.0, 2.0]]
    chunks = [DocumentChunk(str(i), text, "a.txt", None, i)
              for i, text in enumerate(["first", "second"])]
    vectors = embed_chunks(chunks, RecordingEmbedder(), batch_size=7)
    np.testing.assert_allclose(vectors, [[0.6, 0.8], [0.0, 1.0]], rtol=1e-6)


@pytest.mark.parametrize("batch_size", [0, -1])
def test_invalid_batch_size_never_loads_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, batch_size: int,
) -> None:
    def never_load(model_name: str) -> FakeEmbedder:
        raise AssertionError("Invalid arguments must fail before loading model weights")
    monkeypatch.setattr(prepare, "SentenceTransformerEmbedder", never_load)
    with pytest.raises(ValueError, match="batch size"):
        prepare_corpus(tmp_path, batch_size=batch_size)


@pytest.mark.parametrize("failure_point", ["serialization", "replace"])
def test_failed_save_preserves_previous_bundle_and_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_point: str,
) -> None:
    source = tmp_path / "documents"
    source.mkdir()
    (source / "a.txt").write_text("Original document", encoding="utf-8")
    corpus = prepare_corpus(source, embedding_model=FakeEmbedder())
    output = tmp_path / "artifacts" / "prepared.npz"
    save_prepared_corpus(corpus, output)
    original = output.read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("Simulated disk failure")

    if failure_point == "serialization":
        monkeypatch.setattr("rag_server.prepare.np.savez_compressed", fail)
    else:
        monkeypatch.setattr("rag_server.prepare.os.replace", fail)
    with pytest.raises(OSError, match="Simulated disk failure"):
        save_prepared_corpus(corpus, output)
    assert output.read_bytes() == original
    assert list(output.parent.iterdir()) == [output]


def test_cli_loads_splits_embeds_and_exports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "documents"
    source.mkdir()
    (source / "a.txt").write_text("Python functions. " * 20, encoding="utf-8")
    write_pdf(source / "b.pdf")
    selected_models: list[str] = []

    def fake_model(name: str) -> FakeEmbedder:
        selected_models.append(name)
        return FakeEmbedder()

    monkeypatch.setattr(prepare, "SentenceTransformerEmbedder", fake_model)
    output = tmp_path / "prepared.npz"
    with pytest.warns(UserWarning, match="skipped 1 pages"):
        result = prepare.main([
            "--documents", str(source), "--output", str(output),
            "--model", "chosen-model", "--chunk-size", "50",
            "--chunk-overlap", "10", "--batch-size", "2",
        ])
    assert result == 0
    assert selected_models == ["chosen-model"]
    with np.load(output, allow_pickle=False) as bundle:
        chunks = json.loads(str(bundle["chunks_json"]))
        manifest = json.loads(str(bundle["manifest_json"]))
        assert bundle["embeddings"].shape == (len(chunks), 3)
    assert manifest["document_count"] == 2
    assert manifest["chunk_count"] == len(chunks)
    assert {chunk["source"] for chunk in chunks} == {"a.txt", "b.pdf"}
    assert {chunk["page"] for chunk in chunks if chunk["source"] == "b.pdf"} == {1}
    assert "Loaded 2 documents" in capsys.readouterr().out


def test_cli_failed_preparation_preserves_existing_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "documents"
    source.mkdir()
    (source / "empty.txt").write_text("", encoding="utf-8")
    output = tmp_path / "prepared.npz"
    output.write_bytes(b"previous output")
    with pytest.raises(SystemExit) as error:
        prepare.main(["--documents", str(source), "--output", str(output)])
    assert error.value.code == 1
    assert output.read_bytes() == b"previous output"
    assert "Could not load empty.txt" in capsys.readouterr().err


def test_cli_rejects_bad_output_extension_before_loading_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def never_load(model_name: str) -> FakeEmbedder:
        raise AssertionError("Bad output paths must be rejected before model loading")
    monkeypatch.setattr(prepare, "SentenceTransformerEmbedder", never_load)
    output = tmp_path / "prepared.json"
    with pytest.raises(SystemExit) as error:
        prepare.main(["--documents", str(tmp_path), "--output", str(output)])
    assert error.value.code == 2
    assert not output.exists()
