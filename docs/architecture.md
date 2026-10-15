# Architecture and module boundaries

This document describes the final implementation. The original planning diagram
is preserved in [the original PDF](../init-architecture.drawio2.pdf), first committed
in `d105843` before the implementation. The updated component diagram appears on
page 6 of [the submission report](../PROJECT_REPORT.pdf). See
[state and sequence diagrams](diagrams.md) for full execution flows.

## Repository structure

```text
project-root/
|-- src/coding_assistant/
|   |-- cli/          # terminal input, output, and streaming display
|   |-- agent/        # reason-act-observe coordination
|   |-- providers/    # Ollama and cloud-provider adapters
|   |-- mcp/          # MCP client, discovery, and tool invocation
|   |-- execution/    # tool discovery, schema validation, and dispatch
|   |-- config/       # application configuration code
|   `-- contracts/    # shared streaming Protocols
|-- rag_server/
|   |-- ingestion/
|   |-- chunking/
|   |-- embeddings/
|   |-- retrieval/
|   `-- storage/
|-- evaluations/
|   |-- model_comparison/
|   `-- rag_evaluation/
|-- config/mcp.json   # runtime MCP server configuration
`-- tests/
```

## Runtime boundaries

```text
User
  |
  v
Coding assistant process ---- MCP ----> Filesystem MCP server
  |                    |---- MCP ----> External-resource MCP server
  |                    |---- MCP ----> Custom RAG MCP server
  |                    `---- MCP ----> Python-check MCP server
  v
Ollama or cloud model provider
```

The coding assistant owns the CLI, agent loop, provider adapters, MCP client, and
execution policy. The custom RAG MCP server is a separate process that owns its own
ingestion, chunking, embedding, retrieval, and storage internals. The filesystem and
external-resource servers are third-party processes consumed only through MCP; they do
not share the custom RAG server's internal interfaces or data models.

`src/coding_assistant/config` contains code that loads and validates application
settings. Top-level `config` contains deployment/runtime files such as `mcp.json`.

## Task lifecycle

1. The CLI passes a natural-language task to `AgentLoop.run`.
2. The tool dispatcher asks `MCPClient.list_tools` for normalized definitions and
   compiles their argument-schema validators.
3. The agent passes conversation messages and tools to `ModelProvider.stream`.
4. The provider emits a filesystem tool request.
5. The dispatcher validates the exact tool name and arguments, calls
   `MCPClient.call_tool`, and the agent feeds the normalized result back to the
   provider.
6. The provider emits a final response and the agent streams it to the CLI.

The concrete implementations are `BasicAgentLoop`, `GroqProvider` / `OllamaProvider`,
`ToolDispatcher`, `PolicyMCPClient`, and the multi-server `MCPClient`. Agent history
contains complete tool results, while the Groq adapter bounds the request view
and pacing. Python writes trigger a policy-controlled read and syntax validation;
behavioral correctness is measured by the separate evaluation harness.

## RAG lifecycle and design changes

Preparation loads four documents, splits 200-token chunks with up to 30-token
overlap, and embeds them with `sentence-transformers/all-MiniLM-L6-v2`. Indexing
stores the vectors and original source metadata in a persistent Chroma snapshot.
The runtime server reuses that index; it never rebuilds it for each question.
Queries embed in the same space. Cosine search returns 20 candidates, the local
cross-encoder reranks them, and the best five original passages return to the
agent. Explicit `mode="cosine"` preserves the baseline. The RAG server returns
evidence, while the selected main LLM writes the answer.

The planning diagram's generic retrieval branches became this concrete pipeline.
Provider adapters, execution checks, transport boundaries, and recovery are now
explicit. These changes let us change models without duplicating the agent,
validate tools before execution, and improve passage ordering while reusing vectors.
The report explains the changes alongside the preserved original diagram.

## Python command execution

`checks.run_python_check` is a fourth, local stdio MCP server. The three required
servers retain their existing roles. This additional tool runs trusted `.py`
scripts or pytest files/directories using the active interpreter, without a shell.
The target must resolve inside the workspace; durations are 1-60 seconds and
returned output is limited to 16,000 bytes. Credential-like environment variables
are omitted. Normal tool confirmation/auto policy applies. Executed code has the
user's permissions, so the workspace restriction is not an operating-system sandbox.
It supports actual execution after an edit, separately from automatic syntax parsing.

## Current limits

The shipped filesystem server reads, searches, and edits files. Python commands
run through the separate checks server; arbitrary shell syntax is not supported.
Automatic Python syntax validation parses saved text without executing it.
The historical evaluation harness ran its own behavioral checks separately.
Provider outages, quotas, wrong code, and weak source coverage can still prevent
a task from completing. Neither a diagram nor passing regression tests establishes
that every autonomous coding task succeeds.
