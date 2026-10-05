"""Framework-neutral data exchanged across coding-assistant components."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias
from collections.abc import Mapping

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
JSONMapping: TypeAlias = Mapping[str, JSONValue]


class MessageRole(str, Enum):
    """Roles supported by the provider-independent conversation model."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ExecutionMode(str, Enum):
    """Policy for executing tool calls proposed by a model."""

    CONFIRM = "confirm"
    AUTO = "auto"


class AgentStopReason(str, Enum):
    """Why an agent run reached a terminal state."""

    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    ITERATION_LIMIT = "iteration_limit"


class ModelEventType(str, Enum):
    """Kinds of events emitted by a streaming model provider."""

    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    COMPLETED = "completed"


class AgentEventType(str, Enum):
    """Kinds of events visible to the terminal UI during an agent run."""

    STATUS = "status"
    REASONING = "reasoning"
    TEXT_DELTA = "text_delta"
    TOOL_REQUESTED = "tool_requested"
    CONFIRMATION_REQUESTED = "confirmation_requested"
    TOOL_RESULT = "tool_result"
    COMPLETED = "completed"
    FAILED = "failed"


class ServerRole(str, Enum):
    """Required architectural roles for MCP servers."""

    FILESYSTEM = "filesystem"
    EXTERNAL_RESOURCE = "external_resource"
    CUSTOM_RAG = "custom_rag"


class ConnectionStatus(str, Enum):
    """Lifecycle states of an MCP server connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A provider-requested invocation of a dynamically discovered tool."""

    id: str
    name: str
    arguments: JSONMapping = field(default_factory=dict)
    server_name: str | None = None


@dataclass(frozen=True, slots=True)
class Message:
    """A provider-independent conversation message."""

    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """JSON-schema description of a tool exposed to a model."""

    name: str
    description: str
    input_schema: JSONMapping
    server_name: str


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Observable outcome of a tool execution, including normal tool failures."""

    call_id: str
    content: str
    is_error: bool = False
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Provider-reported token usage when available."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Input to a model provider."""

    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...] = ()
    model: str | None = None
    settings: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Complete provider response after one model turn."""

    message: Message
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str = "stop"
    usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass(frozen=True, slots=True)
class ModelEvent:
    """One item from a provider's streamed response."""

    type: ModelEventType
    text: str | None = None
    tool_call: ToolCall | None = None
    response: ModelResponse | None = None


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """Controls the safety and termination behavior of an agent run."""

    max_iterations: int = 20
    system_prompt: str | None = None
    tool_timeout_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class AgentRequest:
    """A user task and its starting conversation context."""

    task: str
    execution_mode: ExecutionMode = ExecutionMode.CONFIRM
    messages: tuple[Message, ...] = ()
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Terminal result of an agent run."""

    stop_reason: AgentStopReason
    iterations: int
    final_message: Message | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One UI-visible event emitted by the agent loop."""

    type: AgentEventType
    message: str | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    result: AgentResult | None = None


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Configuration for one stdio- or URL-based MCP server."""

    name: str
    role: ServerRole
    command: str | None = None
    args: tuple[str, ...] = ()
    url: str | None = None
    environment: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Document:
    """A source document before chunking."""

    id: str
    content: str
    source: str
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """A stable, indexable portion of a source document."""

    id: str
    document_id: str
    content: str
    index: int
    source: str
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A ranked retrieval hit with source attribution."""

    chunk: DocumentChunk
    score: float
    citation: str
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IndexReport:
    """Summary of one ingestion/indexing operation."""

    documents_indexed: int
    chunks_indexed: int
    documents_skipped: int = 0
    index_name: str | None = None
