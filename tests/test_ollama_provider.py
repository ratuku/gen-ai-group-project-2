from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from copy import deepcopy

import pytest
import httpx
from ollama import AsyncClient, ChatResponse, ResponseError

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.contracts import ModelProvider, Payload
from coding_assistant.providers.ollama import OllamaProvider, create_agent


class FakeOllamaClient:
    def __init__(
        self,
        chunks: Sequence[object] = (),
        *,
        error: Exception | None = None,
    ) -> None:
        self.chunks = tuple(chunks)
        self.error = error
        self.calls: list[dict[str, object]] = []
        self.closed = False

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, object]],
        tools: Sequence[Mapping[str, object]],
        stream: bool,
    ) -> AsyncIterator[object]:
        self.calls.append(
            {
                "model": model,
                "messages": deepcopy(messages),
                "tools": deepcopy(tools),
                "stream": stream,
            }
        )
        if self.error is not None:
            raise self.error

        async def generate() -> AsyncIterator[object]:
            for chunk in self.chunks:
                yield chunk

        return generate()

    async def close(self) -> None:
        self.closed = True


class RecordingFactory:
    def __init__(self, turns: Sequence[Sequence[object] | Exception]) -> None:
        self.turns = iter(turns)
        self.hosts: list[str | None] = []
        self.clients: list[FakeOllamaClient] = []

    def __call__(self, host: str | None) -> FakeOllamaClient:
        self.hosts.append(host)
        turn = next(self.turns)
        client = (
            FakeOllamaClient(error=turn)
            if isinstance(turn, Exception)
            else FakeOllamaClient(turn)
        )
        self.clients.append(client)
        return client


class FakeMCPClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Payload]] = []

    async def list_tools(self) -> Sequence[Payload]:
        return (
            {
                "name": "filesystem.read_text_file",
                "description": "Read a UTF-8 text file",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        )

    async def call_tool(self, name: str, arguments: Payload) -> Payload:
        self.calls.append((name, deepcopy(arguments)))
        return {
            "type": "tool_result",
            "name": name,
            "server": "filesystem",
            "is_error": False,
            "content": [{"type": "text", "text": "Project documentation"}],
        }


async def collect(
    provider: OllamaProvider,
    messages: Sequence[Payload],
    tools: Sequence[Payload],
) -> list[Payload]:
    return [event async for event in provider.stream(messages, tools)]


def test_provider_validates_configuration_and_satisfies_contract() -> None:
    provider = OllamaProvider(" qwen3 ", host=" http://localhost:11434 ")
    assert isinstance(provider, ModelProvider)
    assert provider.model == "qwen3"
    assert provider.host == "http://localhost:11434"
    with pytest.raises(ValueError, match="model"):
        OllamaProvider("  ")
    with pytest.raises(ValueError, match="host"):
        OllamaProvider("qwen3", host=" ")


@pytest.mark.asyncio
async def test_stream_translates_history_tools_text_and_parallel_calls() -> None:
    chunks = (
        ChatResponse(message={"role": "assistant", "content": "I will inspect it. "}),
        ChatResponse(
            message={
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "filesystem.read_text_file",
                            "arguments": {"path": "README.md"},
                        }
                    },
                    {
                        "function": {
                            "name": "filesystem.read_text_file",
                            "arguments": {"path": "pyproject.toml"},
                        }
                    },
                ],
            }
        ),
    )
    factory = RecordingFactory((chunks,))
    provider = OllamaProvider(
        "qwen3", host="http://ollama.test", client_factory=factory
    )
    previous_result: Payload = {
        "is_error": False,
        "server": "filesystem",
        "content": [{"type": "text", "text": "README contents"}],
    }
    messages: tuple[Payload, ...] = (
        {"role": "user", "content": "Read the README"},
        {
            "role": "assistant",
            "content": "I will read it.",
            "tool_calls": [
                {
                    "id": "agent_only_id",
                    "name": "filesystem.read_text_file",
                    "arguments": {"path": "README.md"},
                }
            ],
        },
        {
            "role": "tool",
            "name": "filesystem.read_text_file",
            "tool_call_id": "agent_only_id",
            "content": previous_result,
        },
    )
    tools: tuple[Payload, ...] = (
        {
            "name": "filesystem.read_text_file",
            "description": "Read a UTF-8 text file",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    )

    events = await collect(provider, messages, tools)

    assert events == [
        {"type": "text", "content": "I will inspect it. "},
        {
            "type": "tool_call",
            "name": "filesystem.read_text_file",
            "arguments": {"path": "README.md"},
        },
        {
            "type": "tool_call",
            "name": "filesystem.read_text_file",
            "arguments": {"path": "pyproject.toml"},
        },
        {"type": "completed"},
    ]
    assert factory.hosts == ["http://ollama.test"]
    client = factory.clients[0]
    assert client.closed
    request = client.calls[0]
    assert request["model"] == "qwen3"
    assert request["stream"] is True
    native_messages = request["messages"]
    assert isinstance(native_messages, Sequence)
    assert native_messages[1] == {
        "role": "assistant",
        "content": "I will read it.",
        "tool_calls": [
            {
                "function": {
                    "name": "filesystem.read_text_file",
                    "arguments": {"path": "README.md"},
                }
            }
        ],
    }
    assert isinstance(native_messages[2], Mapping)
    assert native_messages[2]["role"] == "tool"
    assert native_messages[2]["tool_name"] == "filesystem.read_text_file"
    assert json.loads(str(native_messages[2]["content"])) == previous_result
    assert request["tools"] == (
        {
            "type": "function",
            "function": {
                "name": "filesystem.read_text_file",
                "description": "Read a UTF-8 text file",
                "parameters": tools[0]["input_schema"],
            },
        },
    )


@pytest.mark.asyncio
async def test_official_sdk_serializes_translated_history_and_streamed_tool_call() -> None:
    request_payloads: list[Mapping[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert isinstance(payload, Mapping)
        request_payloads.append(payload)
        streamed = "\n".join(
            (
                json.dumps(
                    {
                        "model": "qwen3",
                        "message": {"role": "assistant", "content": "Checking. "},
                        "done": False,
                    }
                ),
                json.dumps(
                    {
                        "model": "qwen3",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "filesystem.read_text_file",
                                        "arguments": {"path": "README.md"},
                                    }
                                }
                            ],
                        },
                        "done": True,
                        "done_reason": "stop",
                    }
                ),
            )
        )
        return httpx.Response(
            200,
            content=(streamed + "\n").encode(),
            headers={"content-type": "application/x-ndjson"},
        )

    sdk_client = AsyncClient(
        host="http://ollama.test", transport=httpx.MockTransport(handle)
    )
    provider = OllamaProvider(
        "qwen3",
        client_factory=lambda host: sdk_client,
    )
    result: Payload = {
        "is_error": False,
        "content": [{"type": "text", "text": "README contents"}],
    }
    messages: tuple[Payload, ...] = (
        {"role": "user", "content": "Read the README"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_from_agent",
                    "name": "filesystem.read_text_file",
                    "arguments": {"path": "README.md"},
                }
            ],
        },
        {
            "role": "tool",
            "name": "filesystem.read_text_file",
            "tool_call_id": "call_from_agent",
            "content": result,
        },
    )
    tools: tuple[Payload, ...] = (
        {
            "name": "filesystem.read_text_file",
            "description": "Read a UTF-8 text file",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    )

    events = await collect(provider, messages, tools)

    assert events == [
        {"type": "text", "content": "Checking. "},
        {
            "type": "tool_call",
            "name": "filesystem.read_text_file",
            "arguments": {"path": "README.md"},
        },
        {"type": "completed"},
    ]
    assert len(request_payloads) == 1
    payload = request_payloads[0]
    assert payload["model"] == "qwen3"
    assert payload["stream"] is True
    assert payload["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "filesystem.read_text_file",
                "description": "Read a UTF-8 text file",
                "parameters": tools[0]["input_schema"],
            },
        }
    ]
    native_messages = payload["messages"]
    assert isinstance(native_messages, Sequence)
    assert isinstance(native_messages[1], Mapping)
    assert "id" not in str(native_messages[1]["tool_calls"])
    assert isinstance(native_messages[2], Mapping)
    assert native_messages[2]["tool_name"] == "filesystem.read_text_file"
    assert json.loads(str(native_messages[2]["content"])) == result


@pytest.mark.parametrize(
    "chunk",
    [
        {},
        {"message": {"content": 42}},
        {"message": {"content": "", "tool_calls": "not-an-array"}},
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "filesystem.read_text_file", "arguments": "{}"}}
                ],
            }
        },
    ],
)
@pytest.mark.asyncio
async def test_malformed_native_responses_become_readable_errors(chunk: object) -> None:
    factory = RecordingFactory(((chunk,),))
    provider = OllamaProvider("qwen3", client_factory=factory)

    events = await collect(provider, ({"role": "user", "content": "Hello"},), ())

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "Invalid Ollama response" in str(events[0]["content"])
    assert factory.clients[0].closed


@pytest.mark.asyncio
async def test_invalid_provider_input_fails_before_creating_client() -> None:
    factory = RecordingFactory(((),))
    provider = OllamaProvider("qwen3", client_factory=factory)

    events = await collect(
        provider,
        ({"role": "user", "content": "Hello"},),
        ({"name": "broken", "description": "Missing schema"},),
    )

    assert events[0]["type"] == "error"
    assert "input_schema" in str(events[0]["content"])
    assert not factory.clients


@pytest.mark.asyncio
async def test_connection_and_missing_model_errors_are_actionable() -> None:
    disconnected = RecordingFactory((ConnectionError("connection refused"),))
    unavailable = RecordingFactory((ResponseError("model not found", 404),))

    connection_events = await collect(
        OllamaProvider("qwen3", client_factory=disconnected),
        ({"role": "user", "content": "Hello"},),
        (),
    )
    model_events = await collect(
        OllamaProvider("missing-model", client_factory=unavailable),
        ({"role": "user", "content": "Hello"},),
        (),
    )

    assert "Start Ollama" in str(connection_events[0]["content"])
    assert "ollama pull missing-model" in str(model_events[0]["content"])
    assert disconnected.clients[0].closed
    assert unavailable.clients[0].closed


@pytest.mark.asyncio
async def test_cancellation_propagates_and_closes_client() -> None:
    started = asyncio.Event()

    class WaitingClient(FakeOllamaClient):
        async def chat(
            self,
            *,
            model: str,
            messages: Sequence[Mapping[str, object]],
            tools: Sequence[Mapping[str, object]],
            stream: bool,
        ) -> AsyncIterator[object]:
            del model, messages, tools, stream

            async def wait_forever() -> AsyncIterator[object]:
                started.set()
                await asyncio.Event().wait()
                yield {"message": {"content": "unreachable"}}

            return wait_forever()

    client = WaitingClient()
    provider = OllamaProvider("qwen3", client_factory=lambda host: client)

    async def consume() -> None:
        async for _ in provider.stream(
            ({"role": "user", "content": "Wait"},), ()
        ):
            pass

    running = asyncio.create_task(consume())
    await started.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert client.closed


@pytest.mark.asyncio
async def test_agent_loop_executes_ollama_tool_call_and_returns_final_answer() -> None:
    factory = RecordingFactory(
        (
            (
                ChatResponse(
                    message={
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "filesystem.read_text_file",
                                    "arguments": {"path": "README.md"},
                                }
                            }
                        ],
                    }
                ),
            ),
            (
                ChatResponse(
                    message={
                        "role": "assistant",
                        "content": "The README contains project documentation.",
                    }
                ),
            ),
        )
    )
    provider = OllamaProvider("qwen3", client_factory=factory)
    mcp_client = FakeMCPClient()
    agent = BasicAgentLoop(provider, mcp_client)

    events = [
        event
        async for event in agent.run(
            "Read README.md and summarize it using the filesystem tool"
        )
    ]

    assert mcp_client.calls == [
        ("filesystem.read_text_file", {"path": "README.md"})
    ]
    assert [event["type"] for event in events] == [
        "status",
        "tool_call",
        "tool_result",
        "status",
        "text",
        "completed",
    ]
    assert events[-1] == {
        "type": "completed",
        "reason": "answered",
        "iterations": 2,
    }
    second_request = factory.clients[1].calls[0]
    second_messages = second_request["messages"]
    assert isinstance(second_messages, Sequence)
    assert [message["role"] for message in second_messages if isinstance(message, Mapping)] == [
        "user",
        "assistant",
        "tool",
    ]
    assert isinstance(second_messages[-1], Mapping)
    assert second_messages[-1]["tool_name"] == "filesystem.read_text_file"
    tool_result = json.loads(str(second_messages[-1]["content"]))
    assert tool_result["is_error"] is False
    assert tool_result["content"][0]["text"] == "Project documentation"
    assert all(client.closed for client in factory.clients)


def test_environment_factory_builds_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    with pytest.raises(ValueError, match="OLLAMA_MODEL"):
        create_agent(FakeMCPClient())

    monkeypatch.setenv("OLLAMA_MODEL", "qwen3")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    agent = create_agent(FakeMCPClient())
    assert isinstance(agent, BasicAgentLoop)
    assert isinstance(agent.provider, OllamaProvider)
    assert agent.provider.model == "qwen3"
    assert agent.provider.host == "http://localhost:11434"
