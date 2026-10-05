"""Public component interfaces for independent implementations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Protocol, runtime_checkable

from .models import (
    AgentConfig,
    AgentEvent,
    AgentRequest,
    ConnectionStatus,
    Document,
    DocumentChunk,
    IndexReport,
    JSONValue,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    RetrievedChunk,
    ServerConfig,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


@runtime_checkable
class TerminalUI(Protocol):
    """Interactive terminal boundary used by the application controller."""

    async def read_task(self) -> str:
        """Read and return the next natural-language task."""

    async def render_event(self, event: AgentEvent) -> None:
        """Display one streamed agent event."""

    async def confirm_tool_call(self, call: ToolCall) -> bool:
        """Ask whether a proposed tool call may execute."""

    async def render_error(self, error: Exception) -> None:
        """Display a recoverable application error."""


@runtime_checkable
class ModelProvider(Protocol):
    """Model-agnostic completion and streaming boundary."""

    @property
    def name(self) -> str:
        """Return the stable provider identifier."""

    @property
    def supports_tools(self) -> bool:
        """Whether this provider/model combination accepts tool definitions."""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Return one complete model turn."""

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        """Stream one model turn, ending with a completed event."""


@runtime_checkable
class AgentLoop(Protocol):
    """Autonomous reason-act-observe loop defined by planning issue #1."""

    def run(
        self, request: AgentRequest, config: AgentConfig | None = None
    ) -> AsyncIterator[AgentEvent]:
        """Stream agent activity until exactly one terminal event is emitted."""

    async def cancel(self) -> None:
        """Request cancellation of the active run."""


# Issue #2 implements this client. Issues #3 and #4 supply the filesystem and
# external-resource server configurations/adapters without changing this boundary.
@runtime_checkable
class MCPClient(Protocol):
    """Dynamic multi-server MCP connection and tool-execution boundary."""

    async def connect(self, server: ServerConfig) -> None:
        """Connect to a configured server and make it available for discovery."""

    async def disconnect(self, server_name: str) -> None:
        """Close one server connection."""

    async def list_tools(self, server_name: str | None = None) -> Sequence[ToolDefinition]:
        """Discover tools from one server or all connected servers."""

    async def call_tool(self, call: ToolCall) -> ToolResult:
        """Execute a discovered tool and return its observable result."""

    def connection_status(self, server_name: str) -> ConnectionStatus:
        """Return the current lifecycle state of one server connection."""


# Issue #5 implements source loading, chunking, embedding, and indexing behind
# these contracts so the custom RAG server can be developed independently.
@runtime_checkable
class DocumentLoader(Protocol):
    """Loads supported sources into provider-independent documents."""

    def load(self, sources: Sequence[str]) -> AsyncIterator[Document]:
        """Stream documents loaded from the supplied source identifiers."""


@runtime_checkable
class Chunker(Protocol):
    """Splits documents while preserving identity and source metadata."""

    def split(self, document: Document) -> Sequence[DocumentChunk]:
        """Return stable ordered chunks for one document."""


@runtime_checkable
class Embedder(Protocol):
    """Produces vector representations for indexing and queries."""

    async def embed_documents(
        self, chunks: Sequence[DocumentChunk]
    ) -> Sequence[Sequence[float]]:
        """Embed chunks in input order."""

    async def embed_query(self, query: str) -> Sequence[float]:
        """Embed one retrieval query."""


# Issue #6 implements persistent vector storage and the retrieval tool. Advanced
# retrieval techniques belong behind Retriever rather than in callers.
@runtime_checkable
class VectorStore(Protocol):
    """Persistent vector index boundary."""

    async def upsert(
        self,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Insert or replace chunks and their aligned embeddings."""

    async def query(
        self,
        embedding: Sequence[float],
        *,
        top_k: int,
        filters: Mapping[str, JSONValue] | None = None,
    ) -> Sequence[RetrievedChunk]:
        """Return ranked hits for an embedding."""

    async def delete_document(self, document_id: str) -> int:
        """Delete all chunks for a document and return the deletion count."""


@runtime_checkable
class Retriever(Protocol):
    """Retrieval-strategy boundary, including advanced RAG implementations."""

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, JSONValue] | None = None,
    ) -> Sequence[RetrievedChunk]:
        """Return ranked, cited context for a natural-language query."""


@runtime_checkable
class RAGIndexer(Protocol):
    """One-time or incremental document-ingestion coordinator."""

    async def index(self, sources: Sequence[str], *, rebuild: bool = False) -> IndexReport:
        """Build or update the persistent RAG index."""
