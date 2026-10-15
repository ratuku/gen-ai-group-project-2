# Model comparison results

Machine checks and tool traces; review explanations and retrieval grounding manually.

| Model | Task | Repeat | Pass | Checks | Calls | Tool errors | Seconds | Completion |
|---|---|---|---|---|---|---|---|---|
| openai/gpt-oss-20b | bugfix | 1 | False | False | 3 | 2 | 14.445 | error |
| openai/gpt-oss-120b | bugfix | 1 | False | False | 0 | 0 | 4.107 | error |
| openai/gpt-oss-20b | feature | 1 | True | True | 6 | 3 | 131.73 | answered |
| openai/gpt-oss-120b | feature | 1 | False | False | 8 | 8 | 94.941 | iteration_limit |
| openai/gpt-oss-20b | refactor | 1 | False | False | 8 | 8 | 100.788 | iteration_limit |
| openai/gpt-oss-120b | refactor | 1 | False | True | 5 | 1 | 114.01 | error |
| openai/gpt-oss-20b | documentation | 1 | False | False | 1 | 0 | 4.521 | error |
| openai/gpt-oss-120b | documentation | 1 | False | False | 5 | 1 | 181.24 | missing |
| openai/gpt-oss-120b | bugfix | 2 | False | False | 8 | 8 | 79.232 | iteration_limit |
| openai/gpt-oss-20b | bugfix | 2 | False | False | 4 | 3 | 33.172 | error |
| openai/gpt-oss-120b | feature | 2 | False | False | 8 | 8 | 42.016 | iteration_limit |
| openai/gpt-oss-20b | feature | 2 | True | True | 2 | 0 | 15.235 | answered |
| openai/gpt-oss-120b | refactor | 2 | False | True | 7 | 2 | 139.395 | error |
| openai/gpt-oss-20b | refactor | 2 | False | False | 6 | 4 | 70.53 | error |
| openai/gpt-oss-120b | documentation | 2 | False | False | 6 | 6 | 51.995 | error |
| openai/gpt-oss-20b | documentation | 2 | False | False | 8 | 3 | 155.747 | iteration_limit |
| openai/gpt-oss-20b | bugfix | 3 | True | True | 3 | 0 | 48.798 | answered |
| openai/gpt-oss-120b | bugfix | 3 | True | True | 4 | 2 | 9.425 | answered |
| openai/gpt-oss-20b | feature | 3 | True | True | 3 | 1 | 57.685 | answered |
| openai/gpt-oss-120b | feature | 3 | False | False | 8 | 8 | 48.879 | iteration_limit |
| openai/gpt-oss-20b | refactor | 3 | False | False | 5 | 2 | 56.018 | error |
| openai/gpt-oss-120b | refactor | 3 | False | False | 5 | 4 | 17.028 | error |
| openai/gpt-oss-20b | documentation | 3 | False | False | 2 | 0 | 6.141 | error |
| openai/gpt-oss-120b | documentation | 3 | False | False | 1 | 1 | 14.891 | error |

## Failure evidence

### openai/gpt-oss-20b / bugfix / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 5, in <module>\n    assert s['average']([2, 4, 6]) == 4\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError\n"
  },
  "errors": [
    "Agent stopped: Groq request failed: Tool call validation failed: tool call validation failed: parameters for tool filesystem.read_text_file did not match schema: errors: [`/head`: expected number, but got null, `/tail`: expected number, but got null]"
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "list_directory",
    "list_directory",
    "filesystem.list_directory"
  ]
}
```

### openai/gpt-oss-120b / bugfix / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 5, in <module>\n    assert s['average']([2, 4, 6]) == 4\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError\n"
  },
  "errors": [
    "Agent stopped: Model returned neither a final response nor tool calls"
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
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 5, in <module>\n    assert s['unique_words']('Hello, HELLO world!') == ['hello', 'world']\n           ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\full-run-2026-10-15\\workspaces\\model-2\\feature-1\\solution.py\", line 2, in unique_words\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Stopped after 8 model iterations without a final response."
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "iteration_limit",
  "tool_sequence": [
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory"
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
    "Stopped after 8 model iterations without a final response."
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "iteration_limit",
  "tool_sequence": [
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory"
  ]
}
```

### openai/gpt-oss-120b / refactor / repeat 1

```json
{
  "checks": {
    "passed": true,
    "detail": ""
  },
  "errors": [
    "Agent stopped: Groq request failed with status 413: Error code: 413 - {'error': {'message': 'Request too large for model `openai/gpt-oss-120b` in organization `[ORGANIZATION]` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Requested 8542, please reduce your message size and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": true,
  "completion_reason": "error",
  "tool_sequence": [
    "read_text_file",
    "filesystem.read_text_file",
    "filesystem.edit_file",
    "filesystem.read_text_file",
    "filesystem.edit_file"
  ]
}
```

### openai/gpt-oss-20b / documentation / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\n    assert s['write_greeting'](p, 'Ada') == 12\n           ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\full-run-2026-10-15\\workspaces\\model-1\\documentation-1\\solution.py\", line 2, in write_greeting\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Agent stopped: Groq request failed: Tool call validation failed: tool call validation failed: parameters for tool filesystem.read_text_file did not match schema: errors: [`/head`: expected number, but got null, `/tail`: expected number, but got null]"
  ],
  "missing_required_tools": [
    "rag.search_docs",
    "deepwiki."
  ],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "filesystem.list_directory"
  ]
}
```

### openai/gpt-oss-120b / documentation / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\n    assert s['write_greeting'](p, 'Ada') == 12\n           ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\full-run-2026-10-15\\workspaces\\model-2\\documentation-1\\solution.py\", line 2, in write_greeting\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Task exceeded 180 seconds"
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": false,
  "completion_reason": "missing",
  "tool_sequence": [
    "rag.search_docs",
    "deepwiki.ask_wiki_question",
    "list_directory_with_sizes",
    "filesystem.list_directory_with_sizes",
    "filesystem.read_text_file"
  ]
}
```

### openai/gpt-oss-120b / bugfix / repeat 2

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 5, in <module>\n    assert s['average']([2, 4, 6]) == 4\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError\n"
  },
  "errors": [
    "Stopped after 8 model iterations without a final response."
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "iteration_limit",
  "tool_sequence": [
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory"
  ]
}
```

### openai/gpt-oss-20b / bugfix / repeat 2

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 5, in <module>\n    assert s['average']([2, 4, 6]) == 4\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError\n"
  },
  "errors": [
    "Agent stopped: Groq request failed: Parsing failed. The model generated output that could not be parsed. Please adjust your prompt. See 'failed_generation' for more details."
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "list_directory",
    "list_directory",
    "filesystem.list_directory",
    "read_text_file"
  ]
}
```

### openai/gpt-oss-120b / feature / repeat 2

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 5, in <module>\n    assert s['unique_words']('Hello, HELLO world!') == ['hello', 'world']\n           ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\full-run-2026-10-15\\workspaces\\model-2\\feature-2\\solution.py\", line 2, in unique_words\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Stopped after 8 model iterations without a final response."
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "iteration_limit",
  "tool_sequence": [
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory"
  ]
}
```

### openai/gpt-oss-120b / refactor / repeat 2

```json
{
  "checks": {
    "passed": true,
    "detail": ""
  },
  "errors": [
    "Agent stopped: Groq request failed with status 413: Error code: 413 - {'error': {'message': 'Request too large for model `openai/gpt-oss-120b` in organization `[ORGANIZATION]` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Requested 9010, please reduce your message size and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": true,
  "completion_reason": "error",
  "tool_sequence": [
    "read_text_file",
    "read_text_file",
    "filesystem.read_text_file",
    "filesystem.edit_file",
    "filesystem.read_text_file",
    "filesystem.read_text_file",
    "filesystem.edit_file"
  ]
}
```

### openai/gpt-oss-20b / refactor / repeat 2

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 14, in <module>\n    assert len([n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Lambda))]) >= 2, 'shared helper missing'\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: shared helper missing\n"
  },
  "errors": [
    "Agent stopped: Groq request failed: Failed to parse tool call arguments as JSON"
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "list_directory",
    "filesystem.list_directory",
    "read_text_file",
    "filesystem.read_text_file",
    "filesystem.list_directory",
    "filesystem.read_text_file"
  ]
}
```

### openai/gpt-oss-120b / documentation / repeat 2

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\n    assert s['write_greeting'](p, 'Ada') == 12\n           ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\full-run-2026-10-15\\workspaces\\model-2\\documentation-2\\solution.py\", line 2, in write_greeting\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Agent stopped: Groq rate limit reached. Wait for the limit to reset and try again. Details: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `[ORGANIZATION]` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Used 4178, Requested 4447. Please try again in 4.6875s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
  ],
  "missing_required_tools": [
    "rag.search_docs",
    "deepwiki."
  ],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory_with_sizes",
    "list_directory_with_sizes"
  ]
}
```

### openai/gpt-oss-20b / documentation / repeat 2

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\n    assert s['write_greeting'](p, 'Ada') == 12\n           ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\full-run-2026-10-15\\workspaces\\model-1\\documentation-2\\solution.py\", line 2, in write_greeting\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Stopped after 8 model iterations without a final response."
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": false,
  "completion_reason": "iteration_limit",
  "tool_sequence": [
    "list_directory",
    "list_directory",
    "filesystem.list_directory",
    "read_text_file",
    "filesystem.read_text_file",
    "rag.search_docs",
    "deepwiki.ask_wiki_question",
    "filesystem.read_text_file"
  ]
}
```

### openai/gpt-oss-120b / feature / repeat 3

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 5, in <module>\n    assert s['unique_words']('Hello, HELLO world!') == ['hello', 'world']\n           ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\full-run-2026-10-15\\workspaces\\model-2\\feature-3\\solution.py\", line 2, in unique_words\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Stopped after 8 model iterations without a final response."
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "iteration_limit",
  "tool_sequence": [
    "list_directory_with_sizes",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory",
    "list_directory"
  ]
}
```

### openai/gpt-oss-20b / refactor / repeat 3

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 14, in <module>\n    assert len([n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Lambda))]) >= 2, 'shared helper missing'\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: shared helper missing\n"
  },
  "errors": [
    "Agent stopped: Groq request failed: Failed to parse tool call arguments as JSON"
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "list_directory_with_sizes",
    "filesystem.list_directory_with_sizes",
    "read_text_file",
    "filesystem.read_text_file",
    "filesystem.read_text_file"
  ]
}
```

### openai/gpt-oss-120b / refactor / repeat 3

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 14, in <module>\n    assert len([n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Lambda))]) >= 2, 'shared helper missing'\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: shared helper missing\n"
  },
  "errors": [
    "Agent stopped: Groq request failed: Tool call validation failed: tool call validation failed: attempted to call tool 'filesystem.list_directory<|channel|>commentary' which was not in request.tools"
  ],
  "missing_required_tools": [],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "list_allowed_directories",
    "list_allowed_directories",
    "list_allowed_directories",
    "list_allowed_directories",
    "filesystem.list_allowed_directories"
  ]
}
```

### openai/gpt-oss-20b / documentation / repeat 3

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\n    assert s['write_greeting'](p, 'Ada') == 12\n           ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\full-run-2026-10-15\\workspaces\\model-1\\documentation-3\\solution.py\", line 2, in write_greeting\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Agent stopped: Groq request failed: Tool call validation failed: tool call validation failed: attempted to call tool 'rag.search_docs<|channel|>commentary' which was not in request.tools"
  ],
  "missing_required_tools": [
    "rag.search_docs",
    "deepwiki."
  ],
  "read_existing_code": true,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "filesystem.list_directory",
    "filesystem.read_text_file"
  ]
}
```

### openai/gpt-oss-120b / documentation / repeat 3

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\n    assert s['write_greeting'](p, 'Ada') == 12\n           ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\full-run-2026-10-15\\workspaces\\model-2\\documentation-3\\solution.py\", line 2, in write_greeting\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Agent stopped: Groq rate limit reached. Wait for the limit to reset and try again. Details: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `[ORGANIZATION]` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Used 5128, Requested 3277. Please try again in 3.0375s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
  ],
  "missing_required_tools": [
    "rag.search_docs",
    "deepwiki."
  ],
  "read_existing_code": false,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "read_text_file"
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
