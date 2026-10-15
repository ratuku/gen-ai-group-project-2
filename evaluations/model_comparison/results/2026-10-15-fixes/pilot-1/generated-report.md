# Model comparison results

Machine checks and tool traces; review explanations and retrieval grounding manually.

| Model | Task | Repeat | Pass | Checks | Calls | Tool errors | Seconds | Completion |
|---|---|---|---|---|---|---|---|---|
| openai/gpt-oss-20b | bugfix | 1 | False | False | 1 | 0 | 6.606 | error |
| openai/gpt-oss-120b | bugfix | 1 | True | True | 2 | 0 | 6.769 | answered |
| openai/gpt-oss-20b | feature | 1 | True | True | 2 | 0 | 17.483 | answered |
| openai/gpt-oss-120b | feature | 1 | True | True | 2 | 0 | 20.411 | answered |
| openai/gpt-oss-20b | refactor | 1 | False | True | 5 | 0 | 71.898 | error |
| openai/gpt-oss-120b | refactor | 1 | False | True | 2 | 0 | 6.278 | error |
| openai/gpt-oss-20b | documentation | 1 | False | False | 7 | 2 | 134.234 | error |
| openai/gpt-oss-120b | documentation | 1 | False | False | 8 | 0 | 93.681 | iteration_limit |

## Failure evidence

### openai/gpt-oss-20b / bugfix / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 5, in <module>\n    assert s['average']([2, 4, 6]) == 4\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError\n"
  },
  "errors": [
    "Agent stopped: Groq request failed: Failed to parse tool call arguments as JSON"
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "filesystem.read_text_file"
  ]
}
```

### openai/gpt-oss-20b / refactor / repeat 1

```json
{
  "checks": {
    "passed": true,
    "detail": ""
  },
  "errors": [
    "Agent stopped: Groq request failed: Groq context cannot fit the request budget. Use targeted file reads or fewer MCP tools; full history is retained."
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": true,
  "completion_reason": "error",
  "tool_sequence": [
    "filesystem.read_text_file",
    "filesystem.edit_file",
    "filesystem.read_text_file",
    "filesystem.read_text_file",
    "filesystem.edit_file"
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
    "Agent stopped: Groq request failed: Groq context cannot fit the request budget. Use targeted file reads or fewer MCP tools; full history is retained."
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": true,
  "completion_reason": "error",
  "tool_sequence": [
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
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\n    assert s['write_greeting'](p, 'Ada') == 12\n           ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\after-fixes-2026-10-15\\workspaces\\model-1\\documentation-1\\solution.py\", line 2, in write_greeting\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Agent stopped: Groq request failed: Failed to parse tool call arguments as JSON"
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": false,
  "completion_reason": "error",
  "tool_sequence": [
    "filesystem.read_text_file",
    "rag.search_docs",
    "deepwiki__ask_wiki_question<|channel|>commentary",
    "deepwiki.ask_wiki_question",
    "rag.search_docs",
    "deepwiki__ask_wiki_question<|channel|>commentary",
    "deepwiki.ask_wiki_question"
  ]
}
```

### openai/gpt-oss-120b / documentation / repeat 1

```json
{
  "checks": {
    "passed": false,
    "detail": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\n    assert s['write_greeting'](p, 'Ada') == 12\n           ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n  File \"${PROJECT_ROOT}\\evaluations\\model_comparison\\local\\after-fixes-2026-10-15\\workspaces\\model-2\\documentation-1\\solution.py\", line 2, in write_greeting\n    raise NotImplementedError\nNotImplementedError\n"
  },
  "errors": [
    "Stopped after 8 model iterations without a final response."
  ],
  "missing_required_tools": [],
  "read_existing_code": true,
  "edited_file": false,
  "completion_reason": "iteration_limit",
  "tool_sequence": [
    "rag.search_docs",
    "deepwiki.ask_wiki_question",
    "rag.search_docs",
    "deepwiki.ask_wiki_question",
    "filesystem.read_text_file",
    "rag.search_docs",
    "deepwiki.ask_wiki_question",
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
