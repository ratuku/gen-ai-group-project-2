# Coding task test results

Supporting test record; PROJECT_REPORT.pdf at the repository root is the submission report. Review explanations and grounding manually.

Overall completion: **7/8 attempted task/model slots**; **7/8 planned slots**.

All-attempt completion: **7/8**. Retries remain below and in results.json; they are never erased.

| Latest outcome | Slots |
|---|---:|
| passed | 7 |
| coding_failure | 1 |
| assistant_failure | 0 |
| provider_blocked | 0 |

Provider-blocked attempts remain unsuccessful in the overall completion count. An incomplete
saved implementation is not proof of a model logic error; inspect checks and terminal cause together.

| Model | Task | Repeat | Attempt | Outcome | Pass | Checks | Calls | Tool errors | Seconds | Completion |
|---|---|---|---|---|---|---|---|---|---|---|
| gpt-4.1-mini-2025-04-14 | bugfix | 1 | 1 | passed | True | True | 3 | 0 | 9.562 | answered |
| gpt-4.1-2025-04-14 | bugfix | 1 | 1 | passed | True | True | 3 | 0 | 9.011 | answered |
| gpt-4.1-mini-2025-04-14 | feature | 1 | 1 | coding_failure | False | False | 3 | 0 | 9.914 | answered |
| gpt-4.1-2025-04-14 | feature | 1 | 1 | passed | True | True | 3 | 0 | 8.832 | answered |
| gpt-4.1-mini-2025-04-14 | refactor | 1 | 1 | passed | True | True | 3 | 0 | 10.376 | answered |
| gpt-4.1-2025-04-14 | refactor | 1 | 1 | passed | True | True | 3 | 0 | 9.683 | answered |
| gpt-4.1-mini-2025-04-14 | documentation | 1 | 1 | passed | True | True | 7 | 2 | 27.852 | answered |
| gpt-4.1-2025-04-14 | documentation | 1 | 1 | passed | True | True | 5 | 0 | 37.104 | answered |

## Failure evidence

### gpt-4.1-mini-2025-04-14 / feature / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 10, in <module>\n    assert s['unique_words']('café K İ hello') == ['caf', 'hello']\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError\n"
  },
  "errors": [],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": true,
  "completion_reason": "answered",
  "tool_sequence": [
    "filesystem.read_text_file",
    "filesystem.write_file",
    "filesystem.read_text_file"
  ]
}
```

## Interpretation and limits

Compare pass counts, tool sequences, recoveries, edits, and final explanations in results.json.
Task success requires correctness checks, a successful filesystem read and edit, required
integration calls, and a normal agent completion. Tool errors may be recovered from.
A successful retrieval call does not establish relevance or correct source grounding.
Small synthetic tasks do not establish general coding quality. Refactor checks verify
behavior and helper presence; inspect the final source to assess design quality.
Elapsed time includes discovery, retries, and tool work; excludes grading; it is not token throughput.
Explicit quota waits are excluded from the active task deadline. Service-side changes can affect results.
No token cost, local-provider comparison, or advanced-RAG benefit is measured here.
Filesystem-only runs omit external and custom-RAG integration; see metadata.json for scope.
