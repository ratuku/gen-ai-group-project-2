from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from copy import deepcopy
import json
from typing import cast

from groq import APIConnectionError, APIStatusError, APITimeoutError, AsyncGroq
from groq.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
import httpx
import pytest

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.contracts import ModelProvider, Payload
from coding_assistant.providers.groq import DEFAULT_MODEL, GroqProvider, create_agent


class FakeGroqClient:
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
        self.keys: list[str] = []
        self.clients: list[FakeGroqClient] = []

    def __call__(self, api_key: str) -> FakeGroqClient:
        self.keys.append(api_key)
        turn = next(self.turns)
        client = (
            FakeGroqClient(error=turn)
            if isinstance(turn, Exception)
            else FakeGroqClient(turn)
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
    provider: GroqProvider,
    messages: Sequence[Payload],
    tools: Sequence[Payload],
) -> list[Payload]:
    return [event async for event in provider.stream(messages, tools)]


def text_chunk(content: str) -> Payload:
    return {
        "choices": [
            {"index": 0, "delta": {"role": "assistant", "content": content}}
        ]
    }


def tool_chunk(*calls: Payload) -> Payload:
    return {
        "choices": [
            {"index": 0, "delta": {"tool_calls": list(calls)}}
        ]
    }


def test_provider_validates_configuration_and_satisfies_contract() -> None:
    provider = GroqProvider(" openai/gpt-oss-20b ", api_key=" test-key ")
    assert isinstance(provider, ModelProvider)
    assert provider.model == "openai/gpt-oss-20b"
    assert not hasattr(provider, "api_key")
    with pytest.raises(ValueError, match="model"):
        GroqProvider(" ", api_key="key")
    with pytest.raises(ValueError, match="API key"):
        GroqProvider("model", api_key=" ")


@pytest.mark.asyncio
async def test_stream_translates_history_tools_text_and_fragmented_parallel_calls() -> None:
    chunks = (
        text_chunk("I will inspect it. "),
        tool_chunk(
            {
                "index": 0,
                "id": "call_readme",
                "type": "function",
                "function": {
                    "name": "filesystem.read_text_file",
                    "arguments": '{"path":"README',
                },
            },
            {
                "index": 1,
                "id": "call_config",
                "type": "function",
                "function": {
                    "name": "filesystem.read_text_file",
                    "arguments": '{"path":"pyproject',
                },
            },
        ),
        tool_chunk(
            {"index": 0, "function": {"arguments": '.md"}'}},
            {"index": 1, "function": {"arguments": '.toml"}'}},
        ),
    )
    factory = RecordingFactory((chunks,))
    provider = GroqProvider(
        "openai/gpt-oss-20b", api_key="secret", client_factory=factory
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
                    "id": "previous_call",
                    "name": "filesystem.read_text_file",
                    "arguments": {"path": "README.md"},
                }
            ],
        },
        {
            "role": "tool",
            "name": "filesystem.read_text_file",
            "tool_call_id": "previous_call",
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
            "id": "call_readme",
            "name": "filesystem.read_text_file",
            "arguments": {"path": "README.md"},
        },
        {
            "type": "tool_call",
            "id": "call_config",
            "name": "filesystem.read_text_file",
            "arguments": {"path": "pyproject.toml"},
        },
        {"type": "completed"},
    ]
    assert factory.keys == ["secret"]
    client = factory.clients[0]
    assert client.closed
    request = client.calls[0]
    assert request["model"] == "openai/gpt-oss-20b"
    assert request["stream"] is True
    native_messages = request["messages"]
    assert isinstance(native_messages, Sequence)
    assert native_messages[1] == {
        "role": "assistant",
        "content": "I will read it.",
        "tool_calls": [
            {
                "id": "previous_call",
                "type": "function",
                "function": {
                    "name": "filesystem.read_text_file",
                    "arguments": '{"path": "README.md"}',
                },
            }
        ],
    }
    assert isinstance(native_messages[2], Mapping)
    assert native_messages[2]["role"] == "tool"
    assert native_messages[2]["tool_call_id"] == "previous_call"
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
async def test_official_sdk_serializes_history_and_streamed_tool_fragments() -> None:
    request_payloads: list[Mapping[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert isinstance(payload, Mapping)
        request_payloads.append(payload)
        chunks = (
            {
                "id": "completion-id",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "openai/gpt-oss-20b",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "Checking. "},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "completion-id",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "openai/gpt-oss-20b",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_sdk",
                                    "type": "function",
                                    "function": {
                                        "name": "filesystem.read_text_file",
                                        "arguments": '{"path":"README.md"}',
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            },
        )
        body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
        body += "data: [DONE]\n\n"
        return httpx.Response(
            200,
            content=body.encode(),
            headers={"content-type": "text/event-stream"},
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    sdk = AsyncGroq(
        api_key="sdk-test-key",
        base_url="https://groq.test/openai/v1",
        http_client=http_client,
    )

    class SDKClient:
        async def chat(
            self,
            *,
            model: str,
            messages: Sequence[Mapping[str, object]],
            tools: Sequence[Mapping[str, object]],
            stream: bool,
        ) -> AsyncIterator[object]:
            assert stream
            response = await sdk.chat.completions.create(
                model=model,
                messages=cast(Iterable[ChatCompletionMessageParam], messages),
                tools=cast(Iterable[ChatCompletionToolParam], tools),
                stream=True,
            )
            return cast(AsyncIterator[object], response)

        async def close(self) -> None:
            await sdk.close()

    provider = GroqProvider(
        "openai/gpt-oss-20b",
        api_key="sdk-test-key",
        client_factory=lambda api_key: SDKClient(),
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
            "id": "call_sdk",
            "name": "filesystem.read_text_file",
            "arguments": {"path": "README.md"},
        },
        {"type": "completed"},
    ]
    assert len(request_payloads) == 1
    payload = request_payloads[0]
    assert payload["model"] == "openai/gpt-oss-20b"
    assert payload["stream"] is True
    native_messages = payload["messages"]
    assert isinstance(native_messages, Sequence)
    assert isinstance(native_messages[1], Mapping)
    assert native_messages[1]["tool_calls"][0]["id"] == "call_from_agent"
    assert isinstance(native_messages[2], Mapping)
    assert native_messages[2]["tool_call_id"] == "call_from_agent"
    assert json.loads(str(native_messages[2]["content"])) == result


@pytest.mark.parametrize(
    "chunks, message",
    [
        (({},), "choices"),
        (({"choices": [{"index": 1, "delta": {}}]},), "choice index"),
        (({"choices": [{"index": 0, "delta": {"content": 42}}]},), "content"),
        (
            (
                tool_chunk(
                    {
                        "index": 0,
                        "id": "call_bad",
                        "function": {"name": "broken", "arguments": "not-json"},
                    }
                ),
            ),
            "invalid JSON",
        ),
    ],
)
@pytest.mark.asyncio
async def test_malformed_native_responses_become_readable_errors(
    chunks: Sequence[object], message: str
) -> None:
    factory = RecordingFactory((chunks,))
    provider = GroqProvider("model", api_key="key", client_factory=factory)

    events = await collect(provider, ({"role": "user", "content": "Hello"},), ())

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "Invalid Groq response" in str(events[0]["content"])
    assert message in str(events[0]["content"])
    assert factory.clients[0].closed


@pytest.mark.asyncio
async def test_invalid_provider_input_fails_before_creating_client() -> None:
    factory = RecordingFactory(((),))
    provider = GroqProvider("model", api_key="key", client_factory=factory)

    events = await collect(
        provider,
        ({"role": "user", "content": "Hello"},),
        ({"name": "broken", "description": "Missing schema"},),
    )

    assert events[0]["type"] == "error"
    assert "input_schema" in str(events[0]["content"])
    assert not factory.clients


def status_error(status_code: int) -> APIStatusError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return APIStatusError("service error", response=response, body={})


@pytest.mark.parametrize(
    "error, expected",
    [
        (status_error(401), "GROQ_API_KEY"),
        (status_error(404), "GROQ_MODEL"),
        (status_error(429), "rate limit"),
        (status_error(500), "status 500"),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://api.groq.com")
            ),
            "Could not connect",
        ),
        (
            APITimeoutError(httpx.Request("POST", "https://api.groq.com")),
            "timed out",
        ),
    ],
)
@pytest.mark.asyncio
async def test_service_errors_are_actionable(error: Exception, expected: str) -> None:
    factory = RecordingFactory((error,))
    provider = GroqProvider("missing-model", api_key="key", client_factory=factory)

    events = await collect(provider, ({"role": "user", "content": "Hello"},), ())

    assert expected in str(events[0]["content"])
    assert factory.clients[0].closed


@pytest.mark.asyncio
async def test_cancellation_propagates_and_closes_client() -> None:
    started = asyncio.Event()

    class WaitingClient(FakeGroqClient):
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
                yield text_chunk("unreachable")

            return wait_forever()

    client = WaitingClient()
    provider = GroqProvider(
        "model", api_key="key", client_factory=lambda api_key: client
    )

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
async def test_agent_loop_executes_groq_tool_call_and_returns_final_answer() -> None:
    factory = RecordingFactory(
        (
            (
                tool_chunk(
                    {
                        "index": 0,
                        "id": "call_readme",
                        "type": "function",
                        "function": {
                            "name": "filesystem.read_text_file",
                            "arguments": '{"path":"README.md"}',
                        },
                    }
                ),
            ),
            (text_chunk("The README contains project documentation."),),
        )
    )
    provider = GroqProvider("model", api_key="key", client_factory=factory)
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
    assert [
        message["role"]
        for message in second_messages
        if isinstance(message, Mapping)
    ] == ["user", "assistant", "tool"]
    assert isinstance(second_messages[-1], Mapping)
    assert second_messages[-1]["tool_call_id"] == "call_readme"
    tool_result = json.loads(str(second_messages[-1]["content"]))
    assert tool_result["is_error"] is False
    assert tool_result["content"][0]["text"] == "Project documentation"
    assert all(client.closed for client in factory.clients)


def test_environment_factory_builds_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        create_agent(FakeMCPClient())

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    agent = create_agent(FakeMCPClient())
    assert isinstance(agent, BasicAgentLoop)
    assert isinstance(agent.provider, GroqProvider)
    assert agent.provider.model == DEFAULT_MODEL

    monkeypatch.setenv("GROQ_MODEL", "custom-model")
    custom = create_agent(FakeMCPClient())
    assert isinstance(custom.provider, GroqProvider)
    assert custom.provider.model == "custom-model"

    monkeypatch.setenv("GROQ_MODEL", " ")
    with pytest.raises(ValueError, match="GROQ_MODEL"):
        create_agent(FakeMCPClient())
