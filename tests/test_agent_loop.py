from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from copy import deepcopy
from pathlib import Path

import pytest

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.config import ServerConfig
from coding_assistant.contracts import AgentLoop, Payload
from coding_assistant.mcp import MCPClient as ConcreteMCPClient


class FakeMCPClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Payload]] = []

    async def list_tools(self) -> Sequence[Payload]:
        path_schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        }
        return [
            {"name": "filesystem.list_directory", "input_schema": path_schema},
            {"name": "filesystem.read_text_file", "input_schema": path_schema},
        ]

    async def call_tool(self, name: str, arguments: Payload) -> Payload:
        self.calls.append((name, arguments))
        text = "README.md" if name.endswith("list_directory") else "A Python coding assistant."
        return {"type": "tool_result", "name": name, "is_error": False,
                "content": [{"type": "text", "text": text}]}


class ScriptedProvider:
    def __init__(self, turns: list[list[Payload]]) -> None:
        self.turns = iter(turns)
        self.requests: list[tuple[Sequence[Payload], Sequence[Payload]]] = []

    async def stream(self, messages: Sequence[Payload], tools: Sequence[Payload]) -> AsyncIterator[Payload]:
        self.requests.append((deepcopy(messages), deepcopy(tools)))
        for event in next(self.turns):
            yield event


def tool(name: str, **arguments: object) -> Payload:
    return {"type": "tool_call", "name": name, "arguments": arguments}


@pytest.mark.asyncio
async def test_multistep_request_includes_results_in_model_context() -> None:
    provider = ScriptedProvider([
        [tool("filesystem.list_directory", path="."), {"type": "completed"}],
        [tool("filesystem.read_text_file", path="README.md"), {"type": "completed"}],
        [{"type": "text", "content": "This repository is "},
         {"type": "text", "content": "a Python coding assistant."}, {"type": "completed"}],
    ])
    client = FakeMCPClient()
    agent = BasicAgentLoop(provider, client)
    assert isinstance(agent, AgentLoop)
    events = [event async for event in agent.run("Find the README and explain the project")]
    assert len(provider.requests) == 3
    assert len(client.calls) == 2
    assert provider.requests[0][0][-1]["role"] == "user"
    assert provider.requests[1][0][-1]["role"] == "tool"
    assert "README.md" in str(provider.requests[1][0][-1]["content"])
    assert "A Python coding assistant." in str(provider.requests[2][0][-1]["content"])
    assert len(provider.requests[2][1]) == 2
    assert events[-1] == {"type": "completed", "reason": "answered", "iterations": 3}
    assert agent.messages[-1] == {"role": "assistant", "content": "This repository is a Python coding assistant."}
    for messages, _ in provider.requests[1:]:
        tool_messages = [message for message in messages if message["role"] == "tool"]
        assistant_calls = [message["tool_calls"] for message in messages if "tool_calls" in message]
        assert len(tool_messages) == len(assistant_calls)
        assert all(message.get("tool_call_id") for message in tool_messages)


@pytest.mark.asyncio
async def test_conversation_persists_across_tasks_and_snapshots_are_isolated() -> None:
    provider = ScriptedProvider([
        [{"type": "text", "content": "First answer"}],
        [{"type": "text", "content": "Follow-up answer"}],
    ])
    agent = BasicAgentLoop(provider, FakeMCPClient())
    _ = [event async for event in agent.run("First task")]
    snapshot = agent.messages
    assert isinstance(snapshot[0], dict)
    snapshot[0]["content"] = "Mutated outside the agent"
    _ = [event async for event in agent.run("Follow up")]
    assert [message["content"] for message in provider.requests[1][0]] == [
        "First task", "First answer", "Follow up",
    ]


@pytest.mark.asyncio
async def test_iteration_limit_stops_repeated_tool_requests() -> None:
    provider = ScriptedProvider([[tool("filesystem.list_directory", path=".")]] * 4)
    client = FakeMCPClient()
    events = [event async for event in BasicAgentLoop(provider, client, max_iterations=2).run("Loop")]
    assert len(provider.requests) == len(client.calls) == 2
    assert events[-1]["reason"] == "iteration_limit"
    assert events[-2]["type"] == "error"
    assert "Stopped after 2" in str(events[-2]["content"])


@pytest.mark.asyncio
async def test_multiple_calls_in_one_turn_all_reach_context() -> None:
    provider = ScriptedProvider([
        [tool("filesystem.list_directory", path="."), tool("filesystem.read_text_file", path="README.md")],
        [{"type": "text", "content": "Both results received"}],
    ])
    agent = BasicAgentLoop(provider, FakeMCPClient())
    _ = [event async for event in agent.run("Two tools")]
    messages = provider.requests[1][0]
    assert [message["role"] for message in messages] == ["user", "assistant", "tool", "tool"]
    assert messages[2]["tool_call_id"] != messages[3]["tool_call_id"]


@pytest.mark.parametrize("raises", [True, False])
@pytest.mark.asyncio
async def test_tool_failure_is_available_to_model(raises: bool) -> None:
    class FailingClient(FakeMCPClient):
        async def call_tool(self, name: str, arguments: Payload) -> Payload:
            if raises:
                raise RuntimeError("permission denied")
            return {"is_error": True, "content": "permission denied"}
    provider = ScriptedProvider([
        [tool("filesystem.read_text_file", path="README.md")],
        [{"type": "text", "content": "I could not read the file: permission denied."}],
    ])
    events = [event async for event in BasicAgentLoop(provider, FailingClient()).run("Read file")]
    assert "permission denied" in str(provider.requests[1][0][-1]["content"])
    result = next(event for event in events if event["type"] == "tool_result")
    assert result["is_error"] is True
    if raises:
        assert result["error_code"] == "tool_invocation_failed"
    else:
        assert "error_code" not in result
    assert events[-1]["reason"] == "answered"


@pytest.mark.parametrize(
    ("requested_tool", "arguments", "error_code"),
    [
        ("filesystem.not_discovered", {"path": "."}, "unknown_tool"),
        ("filesystem.read_text_file", {"path": 42}, "invalid_arguments"),
    ],
)
@pytest.mark.asyncio
async def test_rejected_tool_request_is_available_to_model(
    requested_tool: str, arguments: Payload, error_code: str,
) -> None:
    provider = ScriptedProvider([
        [{"type": "tool_call", "id": "rejected_call", "name": requested_tool,
          "arguments": arguments}],
        [{"type": "text", "content": f"The tool failed with {error_code}."}],
    ])
    client = FakeMCPClient()

    events = [event async for event in BasicAgentLoop(provider, client).run("Use a tool")]

    assert not client.calls
    result = next(event for event in events if event["type"] == "tool_result")
    assert result["tool_call_id"] == "rejected_call"
    assert result["name"] == requested_tool
    assert result["is_error"] is True
    assert result["error_code"] == error_code
    tool_message = provider.requests[1][0][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "rejected_call"
    assert isinstance(tool_message["content"], Mapping)
    assert tool_message["content"]["error_code"] == error_code
    assert events[-1]["reason"] == "answered"


@pytest.mark.parametrize("turn", [[], [{"type": "completed"}],
    [{"type": "tool_call", "name": "filesystem.read_text_file", "arguments": "bad"}],
    [{"type": "error", "content": "Model unavailable"}]])
@pytest.mark.asyncio
async def test_bad_model_response_is_a_readable_failure(turn: list[Payload]) -> None:
    client = FakeMCPClient()
    events = [event async for event in BasicAgentLoop(ScriptedProvider([turn]), client).run("Task")]
    assert events[-2]["type"] == "error"
    assert events[-1]["reason"] == "error"
    assert not client.calls


@pytest.mark.asyncio
async def test_provider_exception_and_later_task_recovery() -> None:
    class BrokenOnce:
        calls = 0
        async def stream(self, messages: Sequence[Payload], tools: Sequence[Payload]) -> AsyncIterator[Payload]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("Model offline")
            yield {"type": "text", "content": "Back online"}
    agent = BasicAgentLoop(BrokenOnce(), FakeMCPClient())
    first = [event async for event in agent.run("First")]
    second = [event async for event in agent.run("Retry")]
    assert "Model offline" in str(first[-2]["content"])
    assert second[-1]["reason"] == "answered"


@pytest.mark.parametrize("limit", [0, -1, True])
def test_invalid_iteration_limit(limit: int) -> None:
    with pytest.raises(ValueError):
        BasicAgentLoop(ScriptedProvider([]), FakeMCPClient(), max_iterations=limit)


@pytest.mark.asyncio
async def test_model_uses_result_from_real_stdio_echo_tool() -> None:
    class EchoResultProvider:
        def __init__(self) -> None:
            self.requests: list[tuple[Sequence[Payload], Sequence[Payload]]] = []

        async def stream(
            self, messages: Sequence[Payload], tools: Sequence[Payload],
        ) -> AsyncIterator[Payload]:
            self.requests.append((deepcopy(messages), deepcopy(tools)))
            if len(self.requests) == 1:
                yield {
                    "type": "tool_call",
                    "id": "echo_call",
                    "name": "fixture.echo",
                    "arguments": {"value": "hello MCP"},
                }
                yield {"type": "completed"}
                return

            result = messages[-1].get("content")
            if not isinstance(result, Mapping):
                raise AssertionError("Expected the tool result in model context")
            structured = result.get("structured_content")
            if not isinstance(structured, Mapping):
                raise AssertionError("Expected structured MCP content")
            value = structured.get("result")
            if not isinstance(value, str):
                raise AssertionError("Expected a string echo result")
            yield {"type": "text", "content": f"Echo returned: {value}"}
            yield {"type": "completed"}

    server_script = Path(__file__).parent / "fixtures" / "echo_mcp_server.py"
    client = ConcreteMCPClient((ServerConfig(
        name="fixture", command=sys.executable, args=(str(server_script),),
    ),))
    provider = EchoResultProvider()

    async with client:
        agent = BasicAgentLoop(provider, client)
        events = [event async for event in agent.run("Echo hello MCP")]

    assert provider.requests[0][1][0]["name"] == "fixture.echo"
    assert "hello MCP" in str(provider.requests[1][0][-1]["content"])
    assert [event["type"] for event in events
            if event["type"] not in {"status", "completed"}] == [
        "tool_call", "tool_result", "text",
    ]
    assert agent.messages[-1] == {
        "role": "assistant", "content": "Echo returned: hello MCP",
    }
    assert events[-1] == {"type": "completed", "reason": "answered", "iterations": 2}


@pytest.mark.asyncio
async def test_cancelled_tool_call_leaves_coherent_history() -> None:
    started = asyncio.Event()
    class WaitingClient(FakeMCPClient):
        async def call_tool(self, name: str, arguments: Payload) -> Payload:
            started.set()
            await asyncio.Event().wait()
            return {}
    provider = ScriptedProvider([[tool("filesystem.list_directory", path=".")],
                                 [{"type": "text", "content": "Retry accepted"}]])
    agent = BasicAgentLoop(provider, WaitingClient())
    async def consume() -> None:
        async for event in agent.run("Wait"):
            pass
    running = asyncio.create_task(consume())
    await started.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert agent.messages[-1]["role"] == "tool"
    assert "interrupted" in str(agent.messages[-1]["content"])
    events = [event async for event in agent.run("Next task")]
    assert events[-1]["reason"] == "answered"
