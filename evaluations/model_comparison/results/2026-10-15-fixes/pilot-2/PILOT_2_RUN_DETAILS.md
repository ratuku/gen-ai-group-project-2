# Pilot 2 run details - 8 attempts

Supporting test record. The single submission report is [PROJECT_REPORT.pdf](../../../../../PROJECT_REPORT.pdf).

Machine checks and tool traces; review explanations and retrieval grounding manually.

| Model | Task | Repeat | Pass | Checks | Calls | Tool errors | Seconds | Completion |
|---|---|---|---|---|---|---|---|---|
| openai/gpt-oss-20b | bugfix | 1 | False | False | 2 | 0 | 5.822 | answered |
| openai/gpt-oss-120b | bugfix | 1 | True | True | 2 | 0 | 5.817 | answered |
| openai/gpt-oss-20b | feature | 1 | False | False | 0 | 0 | 14.418 | error |
| openai/gpt-oss-120b | feature | 1 | False | False | 3 | 0 | 22.014 | answered |
| openai/gpt-oss-20b | refactor | 1 | False | False | 0 | 0 | 4.454 | error |
| openai/gpt-oss-120b | refactor | 1 | True | True | 2 | 0 | 55.644 | answered |
| openai/gpt-oss-20b | documentation | 1 | False | False | 3 | 0 | 39.299 | error |
| openai/gpt-oss-120b | documentation | 1 | False | False | 1 | 0 | 16.786 | error |

## Failure evidence

### openai/gpt-oss-20b / bugfix / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 4, in <module>\n    s = runpy.run_path('${PROJECT_ROOT}\\\\evaluations\\\\model_comparison\\\\local\\\\after-fixes-final-2026-10-15\\\\workspaces\\\\model-1\\\\bugfix-1\\\\solution.py')\n  File \"<frozen runpy>\", line 293, in run_path\n  File \"<frozen runpy>\", line 266, in _get_code_from_file\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\after-fixes-final-2026-10-15\\workspaces\\model-1\\bugfix-1\\solution.py\", line 2\n    \"\"\"Return the arithmetic mean of a non\\u2011empty sequence of numbers.\n    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nIndentationError: expected an indented block after function definition on line 1\n"
  },
  "errors": [],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": true,
  "completion_reason": "answered",
  "tool_sequence": [
    "filesystem.read_text_file",
    "filesystem.edit_file"
  ]
}
```

### openai/gpt-oss-20b / feature / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 5, in <module>\n    assert s['unique_words']('Hello, HELLO world!') == ['hello', 'world']\n           ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\after-fixes-final-2026-10-15\\workspaces\\model-1\\feature-1\\solution.py\", line 2, in unique_words\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Agent stopped: Groq rate limit reached. Wait for the limit to reset and try again. Details: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `[ORGANIZATION]` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Used 5902, Requested 2382. Please try again in 2.13s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": []
}
```

### openai/gpt-oss-120b / feature / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 10, in <module>\n    assert s['unique_words']('café \\u212a \\u0130 hello') == ['caf', 'hello']\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError\n"
  },
  "errors": [],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": true,
  "completion_reason": "answered",
  "tool_sequence": [
    "filesystem.read_text_file",
    "filesystem.list_directory",
    "filesystem.edit_file"
  ]
}
```

### openai/gpt-oss-20b / refactor / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 14, in <module>\n    assert len([n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Lambda))]) >= 2, 'shared helper missing'\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: shared helper missing\n"
  },
  "errors": [
    "Agent stopped: Groq rate limit reached. Wait for the limit to reset and try again. Details: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `[ORGANIZATION]` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Used 6598, Requested 2175. Please try again in 5.7975s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": []
}
```

### openai/gpt-oss-20b / documentation / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\n    assert s['write_greeting'](p, 'Ada') == 12\n           ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\after-fixes-final-2026-10-15\\workspaces\\model-1\\documentation-1\\solution.py\", line 2, in write_greeting\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Agent stopped: Groq rate limit reached. Wait for the limit to reset and try again. Details: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `[ORGANIZATION]` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198797, Requested 3448. Please try again in 16m9.84s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "filesystem.read_text_file",
    "rag.search_docs",
    "deepwiki.ask_wiki_question"
  ]
}
```

### openai/gpt-oss-120b / documentation / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\n    assert s['write_greeting'](p, 'Ada') == 12\n           ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\after-fixes-final-2026-10-15\\workspaces\\model-2\\documentation-1\\solution.py\", line 2, in write_greeting\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Agent stopped: Groq rate limit reached. Wait for the limit to reset and try again. Details: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `[ORGANIZATION]` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 199491, Requested 2902. Please try again in 17m13.776s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
  ],
  "missing_required_tools": [
    "deepwiki."
  ],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "rag.search_docs"
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
Elapsed time includes discovery and tool work, excludes grading, and is not token throughput.
SDK default sampling, reasoning settings, and service-side changes can affect results.
No token cost, local-provider comparison, or advanced-RAG benefit is measured here.
Filesystem-only runs omit external and custom-RAG integration; see metadata.json for scope.
