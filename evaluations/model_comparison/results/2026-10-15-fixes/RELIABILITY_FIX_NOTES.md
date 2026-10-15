# Reliability fix notes and diagnostic results

Supporting test record. The single submission report is [PROJECT_REPORT.pdf](../../../../PROJECT_REPORT.pdf).

Subsequent changes add [free-tier pacing, resumable batches, and saved-code syntax
validation](../../FREE_TIER_TESTING_NOTES.md). The evidence below describes the earlier
implementation and pilots; their scores and source hashes remain unchanged.

The reported infrastructure failures now have implemented recovery paths and
regression tests. **228 tests pass; strict type checking passes for 56 files.**
Two diagnostic live batches exposed additional cases during implementation.
Both models then reached the account's 200,000-token daily allowance. The final
policy, including the last retry and Windows-edit fixes, has not received a
complete live retest. These records do not establish that the assistant now
completes every coding task reliably.

## Implemented changes

| Problem | Change | Verification |
|---|---|---|
| Missing server prefixes and invalid tool names | Flat API aliases map to the exact discovered MCP names; unique short names resolve only within that snapshot; unknown/ambiguous names regenerate before execution | Alias, collision, ambiguity, and malformed control-marker tests; zero dispatched tool errors in the second live pilot |
| Optional numeric arguments supplied as null | Omit null only for optional fields whose schema forbids null; preserve required, nullable, and unknown fields for validation | Regression test for `head`/`tail`-style fields and required/nullable values |
| Malformed JSON or empty responses abort a task | Bounded regeneration with corrective feedback, including parsing errors delivered inside HTTP 200 event streams | Real SDK event-stream error fixture, empty/malformed batch tests, and live recovery status events |
| Partial invalid batches might expose calls before validation | Finish and check the entire batch before emitting executable calls | Invalid second-call test verifies that the first call never executes |
| Full results duplicated and history exceeds quota | Compact model-facing envelopes; bounded excerpts; preserve call/result groups; summarize completed interactions and oversized edits while retaining full local history | Payload budget, deduplication, grouping, large-edit summary, and history-immutability tests; 120B completed a refactor in pilot 2 |
| Short rate limits stop otherwise recoverable runs | Follow numeric retry guidance for waits up to 60 seconds; visible, cancellable statuses; up to five attempts per model turn | Real live waits recovered; mixed parse-error/rate-limit regression; cancellation test |
| 413 and 429 handled alike | Shrink context after 413; wait for short 429s; stop promptly and clearly on daily/long limits | Error-policy tests and real daily-limit responses |
| RAG starts under Python without its dependencies | `${pythonExecutable}` expands to the running assistant's interpreter in MCP commands | Configuration tests; both live pilots connected the default RAG server successfully |
| Windows fuzzy edits damage Python indentation | Normalize CRLF and lone CR in Python edit text before sending the edit | Exact live failure pattern replayed through the real filesystem MCP server; resulting source compiles and matches the intended text |

Groq remote tool-presence validation is disabled so responses can be repaired
locally. Original tool names and schemas still pass through the dispatcher and
the configured confirmation/auto policy. Unknown names are never guessed across
ambiguous servers. Recovery never automatically replays executed MCP operations,
and a stream is not replayed after text has already been shown.

The final policy uses temperature 0, low GPT-OSS reasoning, a 2,048-token output
limit, an approximate 18,000-byte model-facing payload budget, and at most five
API attempts per model turn. The byte budget is not an exact token counter;
413 recovery and explicit failure remain necessary. See [final policy and source hashes](final-policy.json)
and [provider documentation](../../../../docs/groq-provider.md).

## Live diagnostic evidence

Both pilots used the original four tasks, both original model IDs, fresh source
files, all three MCP servers, the same correctness checks, eight agent iterations,
and a 180-second task deadline. These were intermediate implementations, not
repetitions of the final code. All attempted runs are retained.

| Diagnostic batch | End-to-end passes | Code checks passed | Dispatched tool errors | Main findings |
|---|---:|---:|---:|---|
| Pilot 1: 14,000-byte budget, three attempts | 3/8 | 5/8 | 2 | Both models completed the feature task; rate waits recovered; large completed edits still crowded context; SDK stream errors needed a separate recovery path |
| Pilot 2: larger budget, stream repair, completed-edit summaries | 2/8 | 2/8 | 0 | 120B completed bug fix and refactor; remaining failures included retry exhaustion, daily caps, a Windows indentation issue, and incorrect generated ASCII handling |

The pilots changed prompts and generation settings from the baseline, and had
different account load and fewer repetitions. Their scores do not provide a fair
general model ranking or a clean before/after reliability estimate.

Pilot 2's six failures were investigated individually:

- **20B bug fix:** the proposed replacement had valid indentation, but `oldText`
  ended in a lone carriage return. The filesystem server took its fuzzy-match
  path and removed indentation from the first docstring line. The final
  normalization fix prevents that exact mismatch; the real-server regression
  checks the saved source, not just the proposed arguments.
- **20B feature and refactor:** a parsing failure followed by short rate limits
  exhausted the earlier shared three-attempt allowance. The final policy permits
  up to five attempts; a mixed parse/429 test now exercises this sequence.
- **120B feature:** the saved code failed the ASCII/Unicode boundary check even
  though tool calls succeeded. This is a remaining model-generated logic error,
  not evidence of a tool-routing fix failure. Correctness tests and code review
  are still required.
- **Both documentation tasks:** Groq rejected further requests under the daily
  200,000-token allowance. Error responses requested waits of approximately
  16 and 17 minutes. These limits were reported; no further live calls were made.

The second pilot had zero unknown-tool or MCP invocation errors. No request in
that pilot terminated with HTTP 413 or the earlier local context-budget error.
That is useful evidence for the specific infrastructure changes, but several
runs still failed and the final policy remains incompletely verified live.

## Retained evidence and remaining validation

[Pilot 1 traces](pilot-1/results.json) and [metadata](pilot-1/metadata.json), and
[Pilot 2 traces](pilot-2/results.json) and [metadata](pilot-2/metadata.json), include
prompts, tool arguments/results, recovery statuses, event timestamps, errors,
completion reasons, and correctness outcomes. Each directory includes generated
per-run tables, dependencies, final source, and a source manifest. Local paths
and account identifiers are redacted; adjacent text chunks are coalesced.

After export, all 16 saved sources reproduced their recorded check results and
matched their hashes. Pilot 2 metadata records the exact production source hashes
used for that batch. [Final policy hashes](final-policy.json) identify subsequent
changes that have unit/integration coverage but have not completed a live batch.
The [original 24-run baseline](../2026-10-15/BASELINE_MODEL_RESULTS.md) remains available.

Once the account allowance permits, rerun all four tasks with both models on the
final code, using a fresh output directory. Review generated code and source
grounding as well as automated passes. A clean result is still needed before
claiming that the original live failures are all resolved in deployment.
The implementation cannot raise Groq's allowance or guarantee correct model
reasoning. Existing project tests should run after generated edits.
