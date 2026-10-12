from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from copy import deepcopy

import pytest

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.contracts import MCPClient, Payload
from coding_assistant.execution import PolicyMCPClient, ToolDispatcher


class FakeMCPClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Payload]] = []

    async def list_tools(self) -> Sequence[Payload]:
        return (
            {
                "name": "filesystem.write_file",
                "description": "Write a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        )

    async def call_tool(self, name: str, arguments: Payload) -> Payload:
        self.calls.append((name, deepcopy(arguments)))
        return {
            "type": "tool_result",
            "name": name,
            "is_error": False,
            "content": [{"type": "text", "text": "File written"}],
        }


@pytest.mark.asyncio
async def test_auto_mode_executes_without_approval() -> None:
    client = FakeMCPClient()
    policy_client = PolicyMCPClient(client, mode="auto")
    arguments: Payload = {"path": "hello.txt", "content": "hello"}

    result = await policy_client.call_tool("filesystem.write_file", arguments)

    assert result["is_error"] is False
    assert client.calls == [("filesystem.write_file", arguments)]


@pytest.mark.asyncio
async def test_confirmation_mode_executes_an_approved_action() -> None:
    approvals: list[tuple[str, Payload]] = []

    async def approve(name: str, arguments: Payload) -> bool:
        approvals.append((name, deepcopy(arguments)))
        return True

    client = FakeMCPClient()
    policy_client = PolicyMCPClient(client, mode="confirm", approve=approve)
    arguments: Payload = {"path": "hello.txt", "content": "hello"}

    result = await policy_client.call_tool("filesystem.write_file", arguments)

    assert result["is_error"] is False
    assert approvals == [("filesystem.write_file", arguments)]
    assert client.calls == [("filesystem.write_file", arguments)]


@pytest.mark.asyncio
async def test_confirmation_mode_rejects_without_calling_mcp() -> None:
    async def reject(name: str, arguments: Payload) -> bool:
        assert name == "filesystem.write_file"
        assert arguments == {"path": "hello.txt", "content": "hello"}
        return False

    client = FakeMCPClient()
    policy_client = PolicyMCPClient(client, mode="confirm", approve=reject)

    result = await policy_client.call_tool(
        "filesystem.write_file", {"path": "hello.txt", "content": "hello"}
    )

    assert result["is_error"] is True
    assert result["error_code"] == "tool_rejected"
    assert "was not executed" in str(result["content"])
    assert client.calls == []


def test_confirmation_mode_requires_callback() -> None:
    with pytest.raises(ValueError, match="approval callback"):
        PolicyMCPClient(FakeMCPClient(), mode="confirm")


def test_invalid_execution_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="'confirm' or 'auto'"):
        PolicyMCPClient(FakeMCPClient(), mode="invalid")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_invalid_arguments_are_blocked_before_confirmation() -> None:
    approval_requested = False

    async def approve(name: str, arguments: Payload) -> bool:
        nonlocal approval_requested
        del name, arguments
        approval_requested = True
        return True

    client = FakeMCPClient()
    dispatcher = ToolDispatcher(
        PolicyMCPClient(client, mode="confirm", approve=approve)
    )
    await dispatcher.discover()

    result = await dispatcher.execute(
        "filesystem.write_file", {"path": "missing-content.txt"}
    )

    assert result["error_code"] == "invalid_arguments"
    assert approval_requested is False
    assert client.calls == []


@pytest.mark.asyncio
async def test_rejection_is_returned_to_model_history_for_a_clean_final_answer() -> None:
    class RejectionAwareProvider:
        def __init__(self) -> None:
            self.requests: list[tuple[Payload, ...]] = []

        async def stream(
            self, messages: Sequence[Payload], tools: Sequence[Payload]
        ) -> AsyncIterator[Payload]:
            del tools
            self.requests.append(tuple(deepcopy(messages)))
            tool_messages = [message for message in messages if message.get("role") == "tool"]
            if not tool_messages:
                yield {
                    "type": "tool_call",
                    "id": "write_call",
                    "name": "filesystem.write_file",
                    "arguments": {"path": "hello.txt", "content": "hello"},
                }
            else:
                result = tool_messages[-1]["content"]
                assert isinstance(result, Mapping)
                assert result["error_code"] == "tool_rejected"
                yield {"type": "text", "content": "The requested write was rejected."}
            yield {"type": "completed"}

    async def reject(name: str, arguments: Payload) -> bool:
        del name, arguments
        return False

    raw_client = FakeMCPClient()
    provider = RejectionAwareProvider()
    agent = BasicAgentLoop(
        provider, PolicyMCPClient(raw_client, mode="confirm", approve=reject)
    )

    events = [event async for event in agent.run("Write hello.txt")]

    assert raw_client.calls == []
    result = next(event for event in events if event["type"] == "tool_result")
    assert result["error_code"] == "tool_rejected"
    assert events[-1]["reason"] == "answered"
    assert "rejected" in str(provider.requests[1][-1]["content"])
