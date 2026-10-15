"""Recompute metrics from retained results and explicit manual judgments."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from statistics import mean, median
from typing import Any


def citation_ids(text: str) -> set[str]:
    return set(re.findall(r"[\[\u3010]([0-9a-f]{64})[\]\u3011]", text))


def retrieval_metrics(grades: list[int]) -> dict[str, float]:
    if len(grades) != 5 or any(type(g) is not int or g not in (0, 1, 2) for g in grades):
        raise ValueError("Each ranking needs five grades in {0,1,2}")
    first = next((i for i, g in enumerate(grades, 1) if g == 2), None)
    return {"precision_at_5": sum(g == 2 for g in grades) / 5,
            "reciprocal_rank_at_5": 1 / first if first else 0,
            "direct_hit_at_1": float(grades[0] == 2),
            "direct_hit_at_5": float(first is not None)}


def score(directory: Path) -> dict[str, Any]:
    def load(name: str) -> Any:
        return json.loads((directory / name).read_text(encoding="utf-8"))
    rows, queries, judgments = load("retrieval.json"), load("queries.json")["cases"], load("judgments.json")
    answers = load("answers.json") if (directory / "answers.json").exists() else []
    answer_map = {(a["id"], a["mode"]): a for a in answers}
    cases = {q["id"]: q for q in queries}
    if {r["id"] for r in rows} != set(cases):
        raise ValueError("Retrieved cases do not match fixed questions")
    for name, expected in judgments["evidence_sha256"].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Judgments refer to different evidence: {name}")
    output: dict[str, Any] = {"per_query": [], "aggregate": {}, "controls": []}
    for row in rows:
        case = cases[row["id"]]
        result: dict[str, Any] = {"id": row["id"], "query": row["query"]}
        rated = judgments["retrieval"][row["id"]]
        for mode in ("cosine", "rerank"):
            matches = row[mode]["results"]
            grades = [rated[m["chunk_id"]]["grade"] for m in matches]
            current: dict[str, Any] = {"grades": grades, **retrieval_metrics(grades),
                                       "elapsed_seconds": row[mode]["elapsed_seconds"]}
            answer = answer_map.get((row["id"], mode))
            if answer and answer["text"] and not answer["errors"]:
                review = judgments["answers"][row["id"]][mode]
                if len(review["facts_correct"]) != len(case["facts"]):
                    raise ValueError("Answer fact judgments do not match the reference rubric")
                cited = citation_ids(answer["text"])
                valid = {m["chunk_id"] for m in matches}
                current["answer"] = {
                    "facts_correct": sum(review["facts_correct"]), "facts_possible": len(case["facts"]),
                    "all_citations_valid": cited <= valid,
                    "citations_present": bool(cited), "abstained": review["abstained"],
                    "fully_grounded": bool(review["all_claims_supported"] and cited <= valid
                                            and (cited or review["abstained"])),
                    "review": review["reason"],
                }
            result[mode] = current
        (output["per_query"] if case["answerable"] is True else output["controls"]).append(result)
    for mode in ("cosine", "rerank"):
        scored = [r[mode] for r in output["per_query"]]
        generated = [r[mode]["answer"] for r in output["per_query"] if "answer" in r[mode]]
        output["aggregate"][mode] = {
            "answerable_queries": len(scored),
            **{key: mean(r[key] for r in scored) for key in
               ("precision_at_5", "reciprocal_rank_at_5", "direct_hit_at_1", "direct_hit_at_5")},
            "median_retrieval_seconds": median(r[mode]["elapsed_seconds"] for r in rows),
            "generated_answers": len(generated),
            "correct_reference_facts": sum(a["facts_correct"] for a in generated),
            "possible_reference_facts": sum(a["facts_possible"] for a in generated),
            "fully_grounded_answers": sum(a["fully_grounded"] for a in generated),
            "answers_with_valid_citations": sum(a["all_citations_valid"] for a in generated),
        }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    options = parser.parse_args()
    result = score(options.directory)
    (options.directory / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["aggregate"], indent=2))


if __name__ == "__main__":
    main()
