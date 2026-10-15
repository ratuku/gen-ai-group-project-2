# RAG evaluation: cosine baseline versus cross-encoder reranking

This is supporting evaluation evidence. The single submission report is
[PROJECT_REPORT.pdf](../../PROJECT_REPORT.pdf), with the RAG findings on page 3.
See [the measured results](results/2026-10-15/RAG_COMPARISON_RESULTS.md) for the
per-question outcomes, examples, benefits, and limitations.

## Experiment

[queries.json](queries.json) fixes ten questions and reference facts before retrieval:
two questions per source document (FastMCP, Python, JavaScript, Java), one exact-API
coverage probe, and an unrelated negative control. The eight intended answerable
questions form the relevance denominator; the two probes are reported separately.
The references specify expected facts, rather than selecting successful queries
after seeing retrieval. Equivalent correct answers are accepted during review.

Both modes use the production RAG MCP server over stdio, the same 10,473-chunk
Chroma snapshot, five final passages, and no source filter or minimum score.
Reranking scores 20 cosine candidates with `cross-encoder/ms-marco-MiniLM-L6-v2`.
The baseline returns its first five cosine matches. All final passages and retained
candidate passages are checked against the prepared bundle for exact text, ID,
source, page, and chunk index. Mode order alternates by question; an unscored query
warms the embedding model and reranker before timing. One timing per condition
is a diagnostic, not a controlled latency benchmark.

Optional answers use the **same production Groq 20B adapter**, temperature zero,
SDK-default reasoning for text-only requests, and an identical evidence-only prompt. Only retrieved context
changes between paired conditions. This controlled answer step does not exercise
autonomous tool selection or file editing. The run retained five complete pairs;
the daily allowance blocked the eleventh generation, so ten of twenty planned
answers completed. Untested answers and control abstention are not counted as
successes or failures. No paid access was used.

## Reproduce

From the project root, follow the root README to install RAG dependencies and build
the ignored index. Then run a new output directory (existing results are never replaced):

```powershell
.\.venv\Scripts\python.exe -m evaluations.rag_evaluation.run `
  --output .\rag_server\artifacts\rag-evaluation-new
```

This runs real local models and retrieval, without Groq or an API key. If model
weights are cached, `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` keep inference
offline. To repeat answer generation, load `GROQ_API_KEY` into the shell as shown
in the root README, then add `--with-answers`. Requests are paced by the production
adapter and the answer batch stops at its first provider error. The final
`state.json` distinguishes complete retrieval, blocked answers, and missing keys;
check it even when the process exits normally. Do not run multiple cloud batches
against the same allowance concurrently.

The retained run's metadata records Python/package versions, corpus and bundle
hashes, collection identity, executed RAG/evaluator source hashes, generation
policy, and prompt instructions. Individual answers include prompt hashes.
Model aliases and approximate-neighbor libraries can change results; exact score
or generation replay is not guaranteed by a model name alone.

The retained collector originally labeled reasoning as "low" in metadata, but
the production text-only adapter does not send that option. The metadata includes
an explicit correction to SDK-default reasoning and retains an audit snapshot of
the executed collector. This corrects the settings description without changing
any requests, answers, or judgments.

## Judgments and metrics

`judgments.json` records **Codex's single-assessor review**, not independent human
annotation or a blinded assessment. Review these judgments before presenting the
findings as your team's analysis. Each final chunk has a stable ID, grade, and
reason. The same chunk receives the same grade in both modes for a question:

| Grade | Meaning |
|---|---|
| 2 | Directly supports at least one reference fact in the requested language/API |
| 1 | Related background, without that direct support |
| 0 | Irrelevant or wrong programming language/API |

Precision@5 counts grade-2 passages divided by five. MRR@5 is the mean reciprocal
rank of the first grade-2 passage (zero if absent). Hit@1 and hit@5 measure whether
direct evidence appears at those ranks. There are no exhaustive corpus judgments,
so we do not claim corpus recall or a general relevance score.

Answer review separately scores each reference fact for semantic correctness and
checks all substantive claims/code instructions against the supplied passages.
Fully grounded answers need full claim support and valid citations (or an appropriate
abstention). Citation identity is also checked mechanically; a valid chunk ID alone
does not prove the cited passage supports the statement. Unicode citation brackets
are accepted. The five completed pairs have ten reference facts per condition.

Recompute the committed metrics without models or network access:

```powershell
.\.venv\Scripts\python.exe -m evaluations.rag_evaluation.score `
  .\evaluations\rag_evaluation\results\2026-10-15
```

The scorer checks the evidence hashes before applying the recorded judgments.
For a fresh experiment, review its new passages/answers and create corresponding
judgments; do not reuse labels by rank or silently copy the old judgments.

## Limitations

This is a small, authored diagnostic with one assessor and one generated answer
per condition. The generated subset ended at the quota boundary and does not
cover Java, equality, or negative-control answers. It is not an independently
labeled benchmark, a statistical model ranking, or proof of higher coding pass
rates. Wrong-language matches, missing API documentation, model knowledge beyond
the context, misleading extra claims, and additional reranker latency remain
visible in the retained evidence. Better corpus coverage, explicit source filters,
more repeated questions, and independent blinded judgments are future work.
