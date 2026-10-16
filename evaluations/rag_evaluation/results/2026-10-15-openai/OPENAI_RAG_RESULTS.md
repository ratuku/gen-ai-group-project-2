# Complete OpenAI paired-answer follow-up

All 20 answers completed with `gpt-4.1-mini-2025-04-14` on October 15, 2026.
Each of ten fixed questions received a fresh cosine-context answer and a fresh
reranked-context answer. No Groq answers were reused or mixed into a pair.

The exact frozen retrieval.json and queries.json were hash-verified and copied
from ../2026-10-15/. Passage-level relevance grades are reused by chunk ID because
the passages are byte-identical. Retrieval and its timings were not rerun.
The original evidence-only prompt, alternating mode order, and top-five contexts
were retained. The existing OpenAI adapter uses SDK-default temperature, 4,096
completion tokens, bounded retries, and store=false. These settings differ from
the original Groq answer generation. Executed collector/provider source snapshots,
metadata, every answer, explicit new judgments, and metrics are preserved.

| Eight answerable questions | Cosine | Rerank |
|---|---:|---:|
| Correct reference facts | 12/16 | 13/16 |
| Fully grounded answers | 4/8 | 6/8 |
| Answers with valid citation identities | 6/8 | 7/8 |

The two controls are separate: both modes appropriately abstained on missing
Path.write_text coverage and on the unrelated Apollo lunch menu (2/2 each).
Retrieval relevance remains the frozen experiment's 25% versus 35% precision@5
and 0.400 versus 0.688 MRR@5. The generated answers do not measure autonomous coding.

## What the full answer set shows

Reranking supplied a complete FastMCP tool example and a runnable stdio command.
The tool answer still abbreviated all three citation IDs, so correct reference
facts did not imply valid grounding. Cosine copied one malformed stdio ID and
invented `[55]` as a citation in its finally answer. The scorer now accepts grouped
full IDs and detects abbreviated, malformed and numeric citation labels.

Cosine answered Java inheritance using correct keywords absent from its contexts;
reranking over-abstained despite an explicit implements-clause passage. This
separates prior model knowledge from evidence-only compliance. Both modes omitted
the explicit post-loop continuation fact in their break answers. Reranking's
finally answer can be supported by its Java passages despite a wrong-language
top result. Cosine's blanket var-global-scope statement follows an oversimplified
source but is still misleading, so its extra claims are not credited as fully
grounded. Every decision has a rationale in judgments.json.

## Review limits

Codex manually reviewed all 20 answers against supplied passages. This is a single
assessor with no blinding or independent validation. The follow-up requires the
after-loop reference fact to appear explicitly; the earlier review accepted an
implication. Do not use the old and new fact totals as a controlled model ranking.
The sample is small, authored, uses one generation per context, and inherits
corpus limitations. Controls are not included in the eight-question denominator.

To recompute without network calls:

```powershell
.\.venv\Scripts\python.exe -m evaluations.rag_evaluation.score evaluations/rag_evaluation/results/2026-10-15-openai
```

To regenerate with an existing OPENAI_API_KEY in the environment, use
`python -m evaluations.rag_evaluation.openai_answers --output NEW_DIRECTORY`.
New answers require fresh answer judgments and evidence hashes; old answer
judgments must not be copied. The original Groq evidence remains unchanged.
