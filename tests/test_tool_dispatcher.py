from __future__ import annotations

# mypy: disable-error-code=untyped-decorator

import asyncio
from collections.abc import Sequence

import pytest

from coding_assistant.contracts import Payload
from coding_assistant.execution import ToolDispatcher


class FakeMCPClient:
    def __init__(self, tools: Sequence[Payload] | None = None) -> None:
        self.tools = list(tools or [_tool_definition("server.echo")])
        self.calls: list[tuple[str, Payload]] = []
        self.result: Payload = {
            "type": "tool_result",
            "name": "server.echo",
            "is_error": False,
            "content": [{"type": "text", "text": "echoed"}],
        }
        self.failure: Exception | None = None

    async def list_tools(self) -> Sequence[Payload]:
        return self.tools

    async def call_tool(self, name: str, arguments: Payload) -> Payload:
        self.calls.append((name, arguments))
        if self.failure is not None:
            raise self.failure
        return self.result


def _tool_definition(
    name: str,
    schema: object = None,
) -> Payload:
    input_schema = schema if schema is not None else {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    return {"name": name, "input_schema": input_schema}


@pytest.mark.asyncio
async def test_discovers_and_dispatches_valid_arguments_exactly() -> None:
    client = FakeMCPClient()
    dispatcher = ToolDispatcher(client)

    tools = await dispatcher.discover()
    arguments = {"value": "hello"}
    result = await dispatcher.execute("server.echo", arguments)

    assert tools == tuple(client.tools)
    assert result is client.result
    assert client.calls == [("server.echo", arguments)]
    assert client.calls[0][1] is arguments


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({}, "required property"),
        ({"value": 7}, "not of type 'string'"),
        ({"value": "ok", "extra": True}, "Additional properties"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_arguments_are_reported_without_calling_mcp(
    arguments: Payload,
    message: str,
) -> None:
    client = FakeMCPClient()
    dispatcher = ToolDispatcher(client)
    await dispatcher.discover()

    result = await dispatcher.execute("server.echo", arguments)

    assert result["type"] == "tool_result"
    assert result["name"] == "server.echo"
    assert result["is_error"] is True
    assert result["error_code"] == "invalid_arguments"
    assert message in str(result["content"])
    assert client.calls == []


@pytest.mark.asyncio
async def test_unknown_and_escaped_names_use_exact_registry_lookup() -> None:
    escaped_name = "a.b%2Ec"
    client = FakeMCPClient([_tool_definition(escaped_name)])
    dispatcher = ToolDispatcher(client)
    await dispatcher.discover()

    unknown = await dispatcher.execute("a.b.c", {"value": "wrong name"})
    success = await dispatcher.execute(escaped_name, {"value": "exact name"})

    assert unknown["error_code"] == "unknown_tool"
    assert escaped_name in str(unknown["content"])
    assert success is client.result
    assert client.calls == [(escaped_name, {"value": "exact name"})]


@pytest.mark.parametrize(
    ("tools", "message"),
    [
        ([{"input_schema": {"type": "object"}}], "non-empty string name"),
        ([{"name": "server.echo"}], "object input_schema"),
        ([{"name": "server.echo", "input_schema": "bad"}], "object input_schema"),
        (
            [_tool_definition("server.echo", {"type": "not-a-json-schema-type"})],
            "invalid input_schema",
        ),
        (
            [_tool_definition("server.echo"), _tool_definition("server.echo")],
            "duplicate tool name",
        ),
    ],
)
@pytest.mark.asyncio
async def test_discovery_rejects_malformed_or_duplicate_definitions(
    tools: Sequence[Payload],
    message: str,
) -> None:
    dispatcher = ToolDispatcher(FakeMCPClient(tools))

    with pytest.raises(ValueError, match=message):
        await dispatcher.discover()


@pytest.mark.asyncio
async def test_failed_discovery_does_not_partially_replace_registry() -> None:
    client = FakeMCPClient([_tool_definition("old.echo")])
    dispatcher = ToolDispatcher(client)
    await dispatcher.discover()
    client.tools = [
        _tool_definition("new.echo"),
        _tool_definition("broken.echo", {"type": "invalid"}),
    ]

    with pytest.raises(ValueError, match="broken.echo"):
        await dispatcher.discover()
    old_result = await dispatcher.execute("old.echo", {"value": "still valid"})
    new_result = await dispatcher.execute("new.echo", {"value": "not registered"})

    assert old_result is client.result
    assert new_result["error_code"] == "unknown_tool"
    assert client.calls == [("old.echo", {"value": "still valid"})]


@pytest.mark.asyncio
async def test_invocation_exception_becomes_readable_failure_without_retry() -> None:
    client = FakeMCPClient()
    client.failure = RuntimeError("server stopped responding")
    dispatcher = ToolDispatcher(client)
    await dispatcher.discover()

    result = await dispatcher.execute("server.echo", {"value": "hello"})

    assert result["error_code"] == "tool_invocation_failed"
    assert "server stopped responding" in str(result["content"])
    assert client.calls == [("server.echo", {"value": "hello"})]


@pytest.mark.asyncio
async def test_server_error_result_is_preserved_unchanged() -> None:
    client = FakeMCPClient()
    client.result = {
        "type": "tool_result",
        "name": "server.echo",
        "is_error": True,
        "content": [{"type": "text", "text": "permission denied"}],
        "metadata": {"request_id": "123"},
    }
    dispatcher = ToolDispatcher(client)
    await dispatcher.discover()

    result = await dispatcher.execute("server.echo", {"value": "hello"})

    assert result is client.result


@pytest.mark.asyncio
async def test_cancellation_propagates_without_retry() -> None:
    started = asyncio.Event()

    class WaitingClient(FakeMCPClient):
        async def call_tool(self, name: str, arguments: Payload) -> Payload:
            self.calls.append((name, arguments))
            started.set()
            await asyncio.Event().wait()
            return self.result

    client = WaitingClient()
    dispatcher = ToolDispatcher(client)
    await dispatcher.discover()
    running = asyncio.create_task(
        dispatcher.execute("server.echo", {"value": "hello"})
    )
    await started.wait()

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert client.calls == [("server.echo", {"value": "hello"})]
