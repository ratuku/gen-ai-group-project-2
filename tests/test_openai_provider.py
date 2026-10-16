from __future__ import annotations

import json
from typing import Any

import httpx
from openai import AsyncOpenAI, BadRequestError, RateLimitError
import pytest

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.providers.openai import DEFAULT_MODEL, OpenAIProvider, _SDKOpenAIClient, create_agent
from test_groq_provider import FakeMCPClient, FakeGroqClient, text_chunk, tool_chunk


@pytest.mark.asyncio
async def test_complete_fragmented_calls_resolve_aliases_and_strip_optional_nulls() -> None:
    fake = FakeGroqClient((tool_chunk({"index": 0, "id": "call_1", "type": "function",
        "function": {"name": "filesystem__read_text_file", "arguments": '{"path":"cart.py",'}}),
        tool_chunk({"index": 0, "function": {"arguments": '"head":null}'}})))
    tools = [{"name": "filesystem.read_text_file", "input_schema": {"type": "object",
        "properties": {"path": {"type": "string"}, "head": {"type": "number"}}, "required": ["path"]}}]
    provider = OpenAIProvider(DEFAULT_MODEL, api_key="secret", client_factory=lambda _: fake)
    events = [event async for event in provider.stream([{"role": "user", "content": "Read cart.py"}], tools)]
    assert events == [{"type": "tool_call", "id": "call_1", "name": "filesystem.read_text_file",
                       "arguments": {"path": "cart.py"}}, {"type": "completed"}]
    assert fake.closed


@pytest.mark.asyncio
async def test_bad_json_and_unknown_tools_never_escape_as_executable_calls() -> None:
    for name, arguments in (("filesystem__read_text_file", "{"), ("unknown", "{}")):
        fake = FakeGroqClient((tool_chunk({"index": 0, "id": "bad", "type": "function",
            "function": {"name": name, "arguments": arguments}}),))
        provider = OpenAIProvider(DEFAULT_MODEL, api_key="secret", client_factory=lambda _: fake)
        events = [event async for event in provider.stream([{"role": "user", "content": "Read"}],
                    await FakeMCPClient().list_tools())]
        assert [event["type"] for event in events] == ["error"]
        assert fake.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("quota, expected_requests", [(True, 1), (False, 3)])
async def test_quota_stops_immediately_and_rate_limit_retries_are_bounded(quota: bool, expected_requests: int) -> None:
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
                              headers={"retry-after": "0.1"})
    error = RateLimitError("limited", response=response,
                          body={"code": "insufficient_quota" if quota else "rate_limit_exceeded"})
    fake = FakeGroqClient(error=error)
    waits: list[float] = []
    async def sleep(delay: float) -> None:
        waits.append(delay)
    provider = OpenAIProvider(DEFAULT_MODEL, api_key="secret", client_factory=lambda _: fake, sleep=sleep)
    events = [event async for event in provider.stream([{"role": "user", "content": "Hello"}], [])]
    assert len(fake.calls) == expected_requests
    assert len(waits) == expected_requests - 1
    assert events[-1]["error_code"] == ("provider_quota" if quota else "provider_rate_limit")
    assert fake.closed


@pytest.mark.asyncio
async def test_real_sdk_serializes_openai_request_without_groq_options() -> None:
    bodies: list[dict[str, Any]] = []
    def handle(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=(
            'data: {"id":"test","object":"chat.completion.chunk","created":0,"model":"test",'
            '"choices":[{"index":0,"delta":{"content":"Connected"},"finish_reason":null}]}\n\n'
            'data: [DONE]\n\n'))
    wrapper = _SDKOpenAIClient("test-key")
    await wrapper.close()
    wrapper._client = AsyncOpenAI(api_key="test-key", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    provider = OpenAIProvider(DEFAULT_MODEL, api_key="secret", client_factory=lambda _: wrapper)
    events = [event async for event in provider.stream([{"role": "user", "content": "Hello"}],
                await FakeMCPClient().list_tools())]
    assert events[-1] == {"type": "completed"}
    assert events[0] == {"type": "text", "content": "Connected"}
    assert bodies[0]["model"] == DEFAULT_MODEL
    assert bodies[0]["reasoning_effort"] == "none"
    assert bodies[0]["parallel_tool_calls"] is False
    assert bodies[0]["store"] is False
    assert "disable_tool_validation" not in bodies[0]


@pytest.mark.asyncio
async def test_bad_request_reports_api_reason_without_credentials_or_retry() -> None:
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
    fake = FakeGroqClient(error=BadRequestError("invalid", response=response, body={"error": {
        "message": "Invalid reasoning_effort with tools. Credential: private-test-key sk-proj-secret"}}))
    provider = OpenAIProvider(DEFAULT_MODEL, api_key="private-test-key", client_factory=lambda _: fake)
    events = [event async for event in provider.stream([{"role": "user", "content": "Hi"}], [])]
    assert len(fake.calls) == 1
    assert events[0]["type"] == "error"
    content = str(events[0]["content"])
    assert "Invalid reasoning_effort with tools" in content
    assert "private-test-key" not in content
    assert "sk-proj-secret" not in content
    assert fake.closed


@pytest.mark.asyncio
async def test_agent_executes_tool_and_returns_final_answer() -> None:
    clients = iter((FakeGroqClient((tool_chunk({"index": 0, "id": "read", "type": "function",
        "function": {"name": "filesystem__read_text_file", "arguments": '{"path":"README.md"}'}}),)),
        FakeGroqClient((text_chunk("Read the README."),))))
    mcp = FakeMCPClient()
    agent = BasicAgentLoop(OpenAIProvider(DEFAULT_MODEL, api_key="test", client_factory=lambda _: next(clients)), mcp)
    events = [event async for event in agent.run("Read README.md")]
    assert mcp.calls == [("filesystem.read_text_file", {"path": "README.md"})]
    assert events[-1]["reason"] == "answered"


def test_factory_uses_environment_and_rejects_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coding_assistant.providers.openai._configured_key", lambda: "")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_agent(FakeMCPClient())
    monkeypatch.setattr("coding_assistant.providers.openai._configured_key", lambda: "test")
    monkeypatch.setenv("OPENAI_MODEL", " ")
    with pytest.raises(ValueError, match="OPENAI_MODEL"):
        create_agent(FakeMCPClient())
    monkeypatch.delenv("OPENAI_MODEL")
    provider = create_agent(FakeMCPClient()).provider
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == DEFAULT_MODEL
