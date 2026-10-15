# Partial retest results - quota-paused batch

Supporting test record. The single submission report is [PROJECT_REPORT.pdf](../../../../PROJECT_REPORT.pdf).

Machine checks and tool traces; review explanations and retrieval grounding manually.

Overall completion: **2/3 attempted task/model slots**; **2/8 planned slots**.

All-attempt completion: **2/3**. Retries remain below and in results.json; they are never erased.

| Latest outcome | Slots |
|---|---:|
| passed | 2 |
| coding_failure | 0 |
| assistant_failure | 0 |
| provider_blocked | 1 |

Provider-blocked attempts remain unsuccessful in the overall completion count. An incomplete
saved implementation is not proof of a model logic error; inspect checks and terminal cause together.

| Model | Task | Repeat | Attempt | Outcome | Pass | Checks | Calls | Tool errors | Seconds | Completion |
|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-oss-20b | bugfix | 1 | 1 | passed | True | True | 3 | 0 | 124.289 | answered |
| openai/gpt-oss-120b | bugfix | 1 | 1 | passed | True | True | 3 | 0 | 124.284 | answered |
| openai/gpt-oss-20b | feature | 1 | 1 | provider_blocked | False | False | 0 | 0 | 3.507 | error |

## Failure evidence

### openai/gpt-oss-20b / feature / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 5, in <module>\n    assert s['unique_words']('Hello, HELLO world!') == ['hello', 'world']\n           ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\free-tier-validation-live\\workspaces\\model-1\\feature-1-attempt-1\\solution.py\", line 2, in unique_words\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Agent stopped: Groq daily allowance reached. Completed tool edits are retained. Retry after the allowance resets. Details: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `[ORGANIZATION]` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198383, Requested 2007. Please try again in 2m48.48s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": []
}
```

## Interpretation and limits

Compare pass counts, tool sequences, recoveries, edits, and final explanations in results.json.
Task success requires correctness checks, a successful filesystem read and edit, required
integration calls, and a normal agent completion. Tool errors may be recovered from.
A successful retrieval call does not establish relevance or correct source grounding.
Small synthetic tasks do not establish general coding quality. Refactor checks verify
behavior and helper presence; inspect the final source to assess design quality.
Elapsed time includes discovery, pacing, retries, and tool work; excludes grading; it is not token throughput.
Explicit quota waits are excluded from the active task deadline. Service-side changes can affect results.
No token cost, local-provider comparison, or advanced-RAG benefit is measured here.
Filesystem-only runs omit external and custom-RAG integration; see metadata.json for scope.
