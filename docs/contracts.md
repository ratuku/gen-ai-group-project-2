# Component contracts

The `coding_assistant.contracts` package is the stable boundary between independently
implemented components. Contracts contain no LangChain, MCP SDK, model-vendor, or
vector-database types. Adapters translate those framework types at the boundary.

All potentially blocking I/O is asynchronous. A method documented as a stream returns
an `AsyncIterator`; errors raised before or during iteration follow the same contract.

## Ticket ownership

| Ticket | Implementation responsibility | Contracts to implement |
| --- | --- | --- |
| #1 - Set Up Method Signatures | Shared types, errors, interfaces, and documentation | This package |
| #2 - Build MCP client | Multi-server lifecycle, discovery, routing, and invocation | `MCPClient` |
| #3 - Integrate filesystem MCP | Configure and connect the official filesystem server | `ServerConfig` with `FILESYSTEM`; consume `MCPClient` |
| #4 - Connect external resource MCP | Configure and connect the selected external server | `ServerConfig` with `EXTERNAL_RESOURCE`; consume `MCPClient` |
| #5 - Build ingestion/chunking/embedding pipeline | Load, split, embed, and persist documentation | `DocumentLoader`, `Chunker`, `Embedder`, `RAGIndexer` |
| #6 - Create vector DB + retrieval tool | Store vectors, retrieve cited context, and expose retrieval through custom MCP | `VectorStore`, `Retriever` |

Downstream tickets implement these contracts; they should not add vendor-specific types
to the shared package. If a signature must change, update this document and coordinate
the change before merging dependent work.

## Terminal UI

| Method | Inputs | Output / streaming | Error behavior |
| --- | --- | --- | --- |
| `read_task` | None | Awaited task text | Raises `ConfigurationError` for unusable input; EOF/cancellation may propagate. |
| `render_event` | `AgentEvent` | Awaited `None` | Terminal rendering errors propagate to the application controller. |
| `confirm_tool_call` | `ToolCall` | Awaited approval boolean | Input/cancellation errors propagate; it is not called in `AUTO` mode. |
| `render_error` | `Exception` | Awaited `None` | Rendering errors propagate. |

## Model provider

| Member | Inputs | Output / streaming | Error behavior |
| --- | --- | --- | --- |
| `name` | None | Stable provider name | Must not perform I/O. |
| `supports_tools` | None | Capability boolean | Must not perform I/O. |
| `complete` | `ModelRequest` | Awaited `ModelResponse` | Raises `ConfigurationError` for invalid requests and `ProviderError` for provider failures. |
| `stream` | `ModelRequest` | `ModelEvent` stream ending in one `COMPLETED` event | Raises the same errors as `complete`; partial output may have been emitted. |

Providers may target Ollama or any cloud provider. Tool calls are normalized into
`ToolCall`, so callers never depend on provider-specific message objects.

## Agent loop

| Method | Inputs | Output / streaming | Error behavior |
| --- | --- | --- | --- |
| `run` | `AgentRequest`, optional `AgentConfig` | `AgentEvent` stream ending in one `COMPLETED` or `FAILED` event containing `AgentResult` | Expected terminal conditions use `AgentStopReason`; unexpected setup errors may raise before the first event. |
| `cancel` | None | Awaited `None` | Idempotent; an active run terminates with `CANCELLED`. |

The loop emits `STATUS` or `REASONING`, `TEXT_DELTA`, `TOOL_REQUESTED`, optionally
`CONFIRMATION_REQUESTED`, `TOOL_RESULT`, and finally one terminal event. Reaching
`max_iterations` is a normal terminal result with `ITERATION_LIMIT`, not an exception.

## MCP client

| Method | Inputs | Output / streaming | Error behavior |
| --- | --- | --- | --- |
| `connect` | `ServerConfig` | Awaited `None` | Raises `ConfigurationError` or `MCPConnectionError`. |
| `disconnect` | Server name | Awaited `None` | Safe for an already disconnected server; protocol failures raise `MCPConnectionError`. |
| `list_tools` | Optional server name | Awaited tool sequence | Raises `MCPConnectionError` or `MCPDiscoveryError`. |
| `call_tool` | `ToolCall` | Awaited `ToolResult` | A tool-level failure returns `is_error=True`; transport/protocol failures raise an `MCPError` subtype. |
| `connection_status` | Server name | `ConnectionStatus` | Unknown names raise `ConfigurationError`; no I/O is performed. |

At least one configured server must fill each required role:

```python
from coding_assistant.contracts import ServerConfig, ServerRole

servers = (
    ServerConfig(
        name="filesystem",
        role=ServerRole.FILESYSTEM,
        command="npx",
        args=("-y", "@modelcontextprotocol/server-filesystem", "."),
    ),
    ServerConfig(
        name="external-docs",
        role=ServerRole.EXTERNAL_RESOURCE,
        command="external-server-command",
    ),
    ServerConfig(
        name="project-rag",
        role=ServerRole.CUSTOM_RAG,
        command="python",
        args=("-m", "project_rag_server"),
    ),
)
```

The names and commands are examples; server selection belongs to a later ticket.

## Retrieval and indexing

| Protocol / method | Inputs | Output / streaming | Error behavior |
| --- | --- | --- | --- |
| `DocumentLoader.load` | Source identifiers | `Document` stream | Raises `ConfigurationError` or `RetrievalError`. |
| `Chunker.split` | `Document` | Ordered chunk sequence | Raises `ConfigurationError` for invalid documents and `RetrievalError` for processing failures. |
| `Embedder.embed_documents` | Chunk sequence | Awaited aligned vector sequence | Raises `RetrievalError`; result length must equal input length. |
| `Embedder.embed_query` | Query text | Awaited vector | Raises `ConfigurationError` or `RetrievalError`. |
| `VectorStore.upsert` | Chunks and aligned vectors | Awaited `None` | Raises `ConfigurationError` for mismatched lengths and `RetrievalError` for storage failures. |
| `VectorStore.query` | Vector, `top_k`, optional filters | Awaited ranked hits | Raises `ConfigurationError` or `RetrievalError`. |
| `VectorStore.delete_document` | Document ID | Awaited deletion count | Raises `RetrievalError`. |
| `Retriever.retrieve` | Query, `top_k`, optional filters | Awaited ranked, cited hits | Raises `ConfigurationError` or `RetrievalError`. |
| `RAGIndexer.index` | Sources and `rebuild` flag | Awaited `IndexReport` | Raises `ConfigurationError` or `RetrievalError`; `rebuild=False` supports persistent incremental indexing. |

An advanced RAG implementation conforms to `Retriever`. This keeps reranking, query
expansion, parent-document retrieval, and other strategies replaceable without changing
the agent or MCP server contract.

## End-to-end interaction

1. The terminal UI creates an `AgentRequest` from the user's task.
2. The agent calls `MCPClient.list_tools()` and sends normalized definitions in a
   streamed `ModelRequest`.
3. A provider `TOOL_CALL` becomes an agent `TOOL_REQUESTED` event.
4. In `CONFIRM` mode, the agent emits `CONFIRMATION_REQUESTED` and awaits
   `TerminalUI.confirm_tool_call`; in `AUTO` mode it proceeds directly.
5. The MCP client routes the call to the named server and returns `ToolResult`.
6. The agent emits `TOOL_RESULT`, appends the observation to the conversation, and
   requests the next model turn.
7. The cycle repeats until the agent emits a terminal event containing `AgentResult`.

Session persistence, undo, image input, concrete provider adapters, concrete MCP
transports, and selection of the advanced RAG technique are intentionally deferred.
