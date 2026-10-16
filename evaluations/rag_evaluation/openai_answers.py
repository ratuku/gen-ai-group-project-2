"""Generate a complete OpenAI answer experiment on frozen paired retrieval.

Reuses exact retained passage bytes and retrieval judgments, never prior answers.
Run with python -m evaluations.rag_evaluation.openai_answers --output NEW_DIR.
"""

import argparse
import asyncio
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path

from .run import ROOT, digest, generate, write_json


async def run(options: argparse.Namespace) -> None:
    source = options.source.resolve()
    judgments = json.loads((source / "judgments.json").read_text(encoding="utf-8"))
    for name in ("retrieval.json", "queries.json"):
        if digest(source / name) != judgments["evidence_sha256"][name]:
            raise ValueError("Frozen retrieval evidence changed")
    options.output.mkdir(parents=True, exist_ok=False)
    for name in ("retrieval.json", "queries.json"):
        (options.output / name).write_bytes((source / name).read_bytes())
    metadata = {
        "schema_version": 1, "started_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "openai", "model": options.model, "source": source.relative_to(ROOT).as_posix(),
        "source_metadata_sha256": digest(source / "metadata.json"),
        "retrieval_sha256": digest(source / "retrieval.json"),
        "queries_sha256": digest(source / "queries.json"), "openai_sdk": version("openai"),
        "generation": {"temperature": "SDK default", "max_completion_tokens": 4096,
                       "max_attempts": 3, "store": False, "reasoning_effort": "not sent for GPT-4.1"},
        "method": "All 20 answers generated anew using frozen paired contexts and original evidence-only prompt; alternating mode order. Original Groq answers are not reused. Retrieval/timings are historical, not remeasured.",
        "source_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in (
            Path(__file__), Path(__file__).with_name("run.py"),
            ROOT / "src/coding_assistant/providers/openai.py",
            ROOT / "src/coding_assistant/providers/groq.py",
            ROOT / "src/coding_assistant/providers/groq_context.py")},
    }
    write_json(options.output / "metadata.json", metadata)
    write_json(options.output / "state.json", {"retrieval": "reused_frozen", "answers": "pending"})
    rows = json.loads((source / "retrieval.json").read_text(encoding="utf-8"))
    options.provider = "openai"
    await generate(options, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "evaluations/rag_evaluation/results/2026-10-15")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4.1-mini-2025-04-14")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
