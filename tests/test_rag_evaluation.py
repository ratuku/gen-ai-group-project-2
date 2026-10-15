from dataclasses import dataclass

import pytest

from evaluations.rag_evaluation.run import verify_passage
from evaluations.rag_evaluation.score import citation_ids, retrieval_metrics


def test_retrieval_metrics_penalize_missing_or_late_direct_evidence() -> None:
    assert retrieval_metrics([1, 0, 2, 2, 0]) == {
        "precision_at_5": 0.4, "reciprocal_rank_at_5": 1 / 3,
        "direct_hit_at_1": 0.0, "direct_hit_at_5": 1.0,
    }
    assert retrieval_metrics([1, 1, 0, 0, 0])["reciprocal_rank_at_5"] == 0
    with pytest.raises(ValueError):
        retrieval_metrics([3, 0, 0, 0, 0])


def test_citations_require_exact_chunk_ids() -> None:
    chunk = "a" * 64
    assert citation_ids(f"A claim [{chunk}]. Not [a123] or [page 3].") == {chunk}
    assert citation_ids(f"Unicode brackets \u3010{chunk}\u3011") == {chunk}


def test_passage_verification_rejects_mutated_text_and_provenance() -> None:
    @dataclass
    class Chunk:
        text: str = "original"
        source: str = "Python.pdf"
        page: int = 2
        chunk_index: int = 0
    result = {"chunk_id": "id", "text": "original", "source": "Python.pdf", "page": 2, "chunk_index": 0}
    verify_passage(result, {"id": Chunk()})
    with pytest.raises(ValueError, match="differs"):
        verify_passage({**result, "page": 3}, {"id": Chunk()})
    with pytest.raises(ValueError, match="differs"):
        verify_passage({**result, "text": "invented"}, {"id": Chunk()})
