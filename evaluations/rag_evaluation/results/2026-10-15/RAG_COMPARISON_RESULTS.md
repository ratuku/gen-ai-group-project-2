# Measured RAG comparison - 15 October 2026

Supporting test record. Submit [PROJECT_REPORT.pdf](../../../../PROJECT_REPORT.pdf)
as the written report. [Method and reproduction](../../README.md) describe the
fixed query set, retained source hashes, and single-assessor judgment limitations.

## Results

Retrieval completed for all ten fixed questions. The eight intended answerable
questions form the relevance denominator. The two coverage/negative probes are
reported separately. Groq generation completed **five paired questions (10 of
20 planned answers)** before `provider_daily_limit`. The failed eleventh request
and final blocked state are retained; the nine later slots were unattempted.

| Metric | Cosine | Cross-encoder reranking |
|---|---:|---:|
| Direct evidence at rank 1 | 2/8 (25%) | 4/8 (50%) |
| At least one direct passage in top five | 5/8 | 8/8 |
| Precision@5, directly supporting passages | 25% | 35% |
| Mean reciprocal rank@5 | 0.400 | 0.688 |
| Correct reference facts, completed answer pairs | 8/10 | 10/10 |
| Fully grounded answers, completed pairs | 2/5 | 4/5 |
| Answers whose cited IDs exist in supplied context | 5/5 | 5/5 |
| Median warm retrieval time, ten questions | 0.021 s | 0.430 s |

All 100 final returned passages and 200 recorded cosine candidates matched their
prepared-bundle text and provenance exactly. The unscored model warmup took about
the duration recorded in `metadata.json`; it is excluded from warm timings.

## Per-question evidence

Grades are 2 = direct support, 1 = related background, 0 = irrelevant/wrong language.
These top-five grades are judgments of the final retrieved chunks, not automatically
computed keyword scores. Full chunk IDs and reasons are in `judgments.json`.

| Fixed question | Cosine grades | Reranked grades | Observation |
|---|---|---|---|
| Register a FastMCP tool | 1,1,1,0,1 | 1,2,2,1,1 | A complete server/decorator example enters the final context at rank 2 |
| Start with stdio | 1,1,1,0,1 | 1,1,2,1,0 | Concrete CLI startup/default-stdio instructions enter at rank 3 |
| Python break | 0,2,0,2,1 | 2,0,0,2,0 | Python definition moves ahead of JavaScript discussion |
| Python continue versus break | 2,0,2,0,1 | 2,0,0,0,0 | First result stays useful, but another Python definition drops out |
| JavaScript let versus const | 2,2,2,2,1 | 2,2,2,1,1 | Both have core facts; reranking loses one useful passage |
| JavaScript == versus === | 1,2,1,1,0 | 1,0,2,2,1 | More direct evidence overall, but an irrelevant variables passage reaches rank 2 |
| Java inheritance/interface keywords | 1,1,1,1,1 | 2,1,1,2,1 | implements examples improve; full extends syntax is still weakly supported |
| Java finally | 0,1,0,0,2 | 0,1,2,1,1 | Java cleanup discussion rises, but the first passage is wrong-language JavaScript |
| Path.write_text coverage probe | 0,0,0,0,0 | 0,0,0,0,0 | Neither mode finds the required write API and return-count semantics |
| Apollo 11 menu negative control | 0,0,0,0,0 | 0,0,0,0,0 | Both return unrelated nearest neighbors; retrieval alone does not abstain |

## Answer quality and grounding

For FastMCP registration, cosine context led the model to invent
`@tool(server_file=..., server_name=...)` by mixing module-discovery configuration
with tool registration. Its cited IDs were real, but did not support that code.
Reranked context supplied the complete `FastMCP` / `@mcp.tool` greeting example,
and the answer reproduced the supported approach. This is a concrete benefit of
more useful evidence in a controlled, same-model comparison.

For stdio, both answers described a valid general startup approach, but the
baseline also claimed `fastmcp run` generates a launch command, which its passages
did not support. The reranked answer used the exact documented
`fastmcp run my_server.py:mcp` example and default transport.

Python break/continue answers were correct and supported under both conditions.
For let/const, both answers included the two reference facts, but added unsupported
or misleading claims about hoisting, initialization, or const immutability. Those
answers did not receive full-grounding credit. Correct core facts and valid
citations therefore did not automatically count as fully grounded answers.

The generation limit arrived before equality, Java, coverage-probe, or negative-control
answers. Their answer correctness and abstention behavior are **untested**.

## Benefits, limitations, and next steps

Reranking improved directly useful context on this small set, at additional local
inference cost. It did not consistently improve the first result or avoid
language confusion, and cannot recover documentation missing from the candidate
pool/corpus. No change to source filtering or corpus coverage was made during this
experiment, which keeps the comparison controlled and preserves those failures.

The figures are a Codex-assessed diagnostic, with no independent/blinded second
rater, one generation per condition, and a quota-selected partial answer subset.
They do not establish statistical significance, general model superiority, or
improved autonomous coding pass rates. Add targeted API documentation, use source
filters where the requested language is known, repeat paired answers after the free
allowance resets, and have team members review/re-rate the retained evidence.

## Evidence files

`queries.json` preserves pre-run cases and reference facts. `retrieval.json`
contains ranked original snippets/scores, candidate IDs, and warm timing.
`answers.json` contains generated text, prompt hashes, and the failed request.
`judgments.json` gives explicit grades/reasons, reference-fact and claim-support
decisions, and hashes of the judged evidence. `metrics.json` is reproducible from
those records. `metadata.json` identifies models, corpus, package versions, and
executed source hashes. `state.json` records completed retrieval and blocked
generation. Credentials and account identifiers are not retained.
