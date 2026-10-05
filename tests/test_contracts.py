from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence

import pytest

from coding_assistant.contracts import (
    AgentConfig,
    AgentEvent,
    AgentEventType,
    AgentLoop,
    AgentRequest,
    AgentResult,
    AgentStopReason,
    ConnectionStatus,
    DocumentChunk,
    ExecutionMode,
    MCPClient,
    MCPConnectionError,
    Message,
    MessageRole,
    ModelEvent,
    ModelEventType,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    RetrievedChunk,
    Retriever,
    ServerConfig,
    TerminalUI,
    ToolCall,
    ToolDefinition,
    ToolResult,
    VectorStore,
)
from coding_assistant.contracts.models import JSONValue


class FakeProvider:
    @property
    def name(self) -> str:
        return "fake"

    @property
    def supports_tools(self) -> bool:
        return True

    async def complete(self, request: ModelRequest) -> ModelResponse:
        del request
        return ModelResponse(Message(MessageRole.ASSISTANT, "done"))

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        del request
        response = ModelResponse(Message(MessageRole.ASSISTANT, "done"))
        yield ModelEvent(ModelEventType.TEXT_DELTA, text="do")
        yield ModelEvent(ModelEventType.TEXT_DELTA, text="ne")
        yield ModelEvent(ModelEventType.COMPLETED, response=response)


class FakeUI:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []
        self.errors: list[Exception] = []

    async def read_task(self) -> str:
        return "inspect the repository"

    async def render_event(self, event: AgentEvent) -> None:
        self.events.append(event)

    async def confirm_tool_call(self, call: ToolCall) -> bool:
        del call
        return True

    async def render_error(self, error: Exception) -> None:
        self.errors.append(error)


class FakeAgent:
    def __init__(self) -> None:
        self.cancelled = False

    async def run(
        self, request: AgentRequest, config: AgentConfig | None = None
    ) -> AsyncIterator[AgentEvent]:
        config = config or AgentConfig()
        call = ToolCall("call-1", "read_file", {"path": "README.md"}, "filesystem")
        yield AgentEvent(AgentEventType.STATUS, message="thinking")
        yield AgentEvent(AgentEventType.TEXT_DELTA, message="Inspecting")
        yield AgentEvent(AgentEventType.TOOL_REQUESTED, tool_call=call)
        if request.execution_mode is ExecutionMode.CONFIRM:
            yield AgentEvent(AgentEventType.CONFIRMATION_REQUESTED, tool_call=call)
        result = ToolResult(call.id, "contents")
        yield AgentEvent(AgentEventType.TOOL_RESULT, tool_result=result)
        stop_reason = (
            AgentStopReason.CANCELLED if self.cancelled else AgentStopReason.COMPLETED
        )
        final = AgentResult(
            stop_reason=stop_reason,
            iterations=min(1, config.max_iterations),
            final_message=Message(MessageRole.ASSISTANT, "done"),
        )
        yield AgentEvent(AgentEventType.COMPLETED, result=final)

    async def cancel(self) -> None:
        self.cancelled = True


class FakeMCPClient:
    def __init__(self) -> None:
        self.statuses: dict[str, ConnectionStatus] = {}

    async def connect(self, server: ServerConfig) -> None:
        self.statuses[server.name] = ConnectionStatus.CONNECTED

    async def disconnect(self, server_name: str) -> None:
        self.statuses[server_name] = ConnectionStatus.DISCONNECTED

    async def list_tools(self, server_name: str | None = None) -> Sequence[ToolDefinition]:
        name = server_name or "filesystem"
        return (ToolDefinition("read_file", "Read a file", {"type": "object"}, name),)

    async def call_tool(self, call: ToolCall) -> ToolResult:
        if call.name == "tool_failure":
            return ToolResult(call.id, "permission denied", is_error=True)
        if call.name == "transport_failure":
            raise MCPConnectionError("connection lost")
        return ToolResult(call.id, "ok")

    def connection_status(self, server_name: str) -> ConnectionStatus:
        return self.statuses.get(server_name, ConnectionStatus.DISCONNECTED)


class FakeVectorStore:
    async def upsert(
        self,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("unaligned inputs")

    async def query(
        self,
        embedding: Sequence[float],
        *,
        top_k: int,
        filters: Mapping[str, JSONValue] | None = None,
    ) -> Sequence[RetrievedChunk]:
        del embedding, top_k, filters
        return ()

    async def delete_document(self, document_id: str) -> int:
        del document_id
        return 0


class FakeRetriever:
    def __init__(self, result: RetrievedChunk) -> None:
        self.result = result

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, JSONValue] | None = None,
    ) -> Sequence[RetrievedChunk]:
        del query, filters
        return (self.result,)[:top_k]


async def collect_agent_events(
    agent: AgentLoop, request: AgentRequest
) -> list[AgentEvent]:
    return [event async for event in agent.run(request)]


def test_fakes_satisfy_runtime_protocols() -> None:
    chunk = DocumentChunk("c1", "d1", "text", 0, "guide.md")
    hit = RetrievedChunk(chunk, 0.9, "guide.md#c1")
    assert isinstance(FakeUI(), TerminalUI)
    assert isinstance(FakeProvider(), ModelProvider)
    assert isinstance(FakeAgent(), AgentLoop)
    assert isinstance(FakeMCPClient(), MCPClient)
    assert isinstance(FakeVectorStore(), VectorStore)
    assert isinstance(FakeRetriever(hit), Retriever)


@pytest.mark.asyncio
async def test_provider_stream_ends_with_completed_response() -> None:
    provider: ModelProvider = FakeProvider()
    events = [event async for event in provider.stream(ModelRequest(messages=()))]
    assert [event.type for event in events] == [
        ModelEventType.TEXT_DELTA,
        ModelEventType.TEXT_DELTA,
        ModelEventType.COMPLETED,
    ]
    assert events[-1].response is not None


@pytest.mark.asyncio
async def test_confirmation_mode_emits_confirmation_event() -> None:
    events = await collect_agent_events(
        FakeAgent(), AgentRequest("inspect", ExecutionMode.CONFIRM)
    )
    assert [event.type for event in events] == [
        AgentEventType.STATUS,
        AgentEventType.TEXT_DELTA,
        AgentEventType.TOOL_REQUESTED,
        AgentEventType.CONFIRMATION_REQUESTED,
        AgentEventType.TOOL_RESULT,
        AgentEventType.COMPLETED,
    ]


@pytest.mark.asyncio
async def test_auto_mode_skips_confirmation_event() -> None:
    events = await collect_agent_events(
        FakeAgent(), AgentRequest("inspect", ExecutionMode.AUTO)
    )
    assert AgentEventType.CONFIRMATION_REQUESTED not in {
        event.type for event in events
    }


@pytest.mark.asyncio
async def test_tool_failure_is_observation_but_transport_failure_raises() -> None:
    client: MCPClient = FakeMCPClient()
    tool_failure = await client.call_tool(ToolCall("1", "tool_failure"))
    assert tool_failure.is_error is True
    with pytest.raises(MCPConnectionError):
        await client.call_tool(ToolCall("2", "transport_failure"))


@pytest.mark.asyncio
async def test_agent_terminal_reasons_are_distinct() -> None:
    agent = FakeAgent()
    await agent.cancel()
    events = await collect_agent_events(agent, AgentRequest("inspect"))
    assert events[-1].result is not None
    assert events[-1].result.stop_reason is AgentStopReason.CANCELLED
    results = {
        reason: AgentResult(reason, iterations=1, error="failure" if reason is AgentStopReason.FAILED else None)
        for reason in AgentStopReason
    }
    assert set(results) == {
        AgentStopReason.COMPLETED,
        AgentStopReason.CANCELLED,
        AgentStopReason.FAILED,
        AgentStopReason.ITERATION_LIMIT,
    }


@pytest.mark.asyncio
async def test_retrieval_preserves_identity_score_and_citation() -> None:
    chunk = DocumentChunk(
        id="chunk-1",
        document_id="doc-1",
        content="retrieved content",
        index=3,
        source="docs/guide.md",
        metadata={"section": "tools"},
    )
    expected = RetrievedChunk(
        chunk=chunk,
        score=0.92,
        citation="docs/guide.md#chunk-1",
        metadata={"strategy": "reranked"},
    )
    retriever: Retriever = FakeRetriever(expected)
    results = await retriever.retrieve("tool calls")
    actual = results[0]
    assert actual.chunk.document_id == "doc-1"
    assert actual.chunk.id == "chunk-1"
    assert actual.chunk.content == "retrieved content"
    assert actual.chunk.metadata["section"] == "tools"
    assert actual.score == 0.92
    assert actual.citation == "docs/guide.md#chunk-1"
