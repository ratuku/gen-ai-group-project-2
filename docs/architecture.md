# Architecture and module boundaries

This document records the initial structure needed to build and validate one small
end-to-end flow. The three interfaces in `coding_assistant.contracts` are provisional;
stronger data models will be extracted from working implementations.

## Repository structure

```text
project-root/
|-- src/coding_assistant/
|   |-- cli/          # terminal input, output, and streaming display
|   |-- agent/        # reason-act-observe coordination
|   |-- providers/    # Ollama and cloud-provider adapters
|   |-- mcp/          # MCP client, discovery, and tool invocation
|   |-- execution/    # confirmation and automatic execution policy
|   |-- config/       # application configuration code
|   `-- contracts/    # three provisional vertical-slice Protocols
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
  |                    `---- MCP ----> Custom RAG MCP server
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

## First vertical slice

1. The CLI passes a natural-language task to `AgentLoop.run`.
2. The agent asks `MCPClient.list_tools` for normalized tool definitions.
3. The agent passes conversation messages and tools to `ModelProvider.stream`.
4. The provider emits a filesystem tool request.
5. The agent calls `MCPClient.call_tool` and feeds the normalized result back to the
   provider.
6. The provider emits a final response and the agent streams it to the CLI.

This slice validates the three component boundaries before the project commits to
message classes, event hierarchies, error taxonomies, or RAG-internal contracts.
