from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.types import CallToolResult, TextContent, Tool

import coding_assistant.mcp.client as client_module
from coding_assistant.config import ServerConfig
from coding_assistant.contracts import MCPClient as MCPClientContract
from coding_assistant.mcp import MCPClient, MCPClientError


class FakeSDKClient:
    instances: list[FakeSDKClient] = []
    fail_target: str | None = None
    fail_call = False
    return_tool_error = False
    tool_names_by_target: dict[object, tuple[str, ...]] = {}
    close_failures_by_target: dict[object, int] = {}

    def __init__(self, target: object, *, read_timeout_seconds: float) -> None:
        self.target = target
        self.read_timeout_seconds = read_timeout_seconds
        self.closed = False
        self.close_attempts = 0
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.__class__.instances.append(self)

    async def __aenter__(self) -> FakeSDKClient:
        if self.target == self.fail_target:
            raise RuntimeError("connection refused")
        return self

    async def __aexit__(self, *args: object) -> None:
        self.close_attempts += 1
        failures_remaining = self.close_failures_by_target.get(self.target, 0)
        if failures_remaining:
            self.close_failures_by_target[self.target] = failures_remaining - 1
            raise RuntimeError("close failed")
        self.closed = True

    async def list_tools(self, *, cursor: str | None = None) -> SimpleNamespace:
        suffix = str(self.target).rsplit("/", maxsplit=1)[-1]
        configured_names = self.tool_names_by_target.get(self.target)
        if configured_names is not None:
            return SimpleNamespace(
                tools=[
                    Tool(
                        name=name,
                        description=f"Tool from {suffix}",
                        input_schema={"type": "object"},
                    )
                    for name in configured_names
                ],
                next_cursor=None,
            )
        if cursor is None:
            return SimpleNamespace(
                tools=[
                    Tool(
                        name="search",
                        description=f"Search {suffix}",
                        input_schema={"type": "object"},
                    )
                ],
                next_cursor="page-2",
            )
        return SimpleNamespace(
            tools=[
                Tool(
                    name="details",
                    description=f"Details from {suffix}",
                    input_schema={"type": "object"},
                )
            ],
            next_cursor=None,
        )

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> CallToolResult:
        self.calls.append((name, arguments))
        if self.fail_call:
            raise RuntimeError("server stopped responding")
        if self.return_tool_error:
            return CallToolResult(
                content=[TextContent(type="text", text="permission denied")],
                is_error=True,
            )
        return CallToolResult(
            content=[TextContent(type="text", text=f"called {name}")],
            structured_content={"server": self.target},
        )


@pytest.fixture(autouse=True)
def reset_fake_client() -> None:
    FakeSDKClient.instances.clear()
    FakeSDKClient.fail_target = None
    FakeSDKClient.fail_call = False
    FakeSDKClient.return_tool_error = False
    FakeSDKClient.tool_names_by_target.clear()
    FakeSDKClient.close_failures_by_target.clear()


@pytest.mark.asyncio
async def test_discovers_qualified_tools_and_routes_duplicate_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "Client", FakeSDKClient)
    configs = (
        ServerConfig(name="first", url="https://example.com/first"),
        ServerConfig(name="second", url="https://example.com/second"),
    )
    client = MCPClient(configs)

    assert isinstance(client, MCPClientContract)
    async with client:
        tools = await client.list_tools()
        result = await client.call_tool("second.search", {"query": "MCP"})

    assert [tool["name"] for tool in tools] == [
        "first.search",
        "first.details",
        "second.search",
        "second.details",
    ]
    assert result["type"] == "tool_result"
    assert result["name"] == "second.search"
    assert result["structured_content"] == {
        "server": "https://example.com/second"
    }
    first, second = FakeSDKClient.instances
    assert first.calls == []
    assert second.calls == [("search", {"query": "MCP"})]
    assert first.closed is True
    assert second.closed is True


@pytest.mark.asyncio
async def test_escaped_qualified_names_cannot_collide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "Client", FakeSDKClient)
    first_target = "https://example.com/first"
    second_target = "https://example.com/second"
    FakeSDKClient.tool_names_by_target = {
        first_target: ("b.c",),
        second_target: ("c",),
    }
    client = MCPClient(
        (
            ServerConfig(name="a", url=first_target),
            ServerConfig(name="a.b", url=second_target),
        )
    )

    async with client:
        tools = await client.list_tools()
        await client.call_tool("a.b%2Ec", {})
        await client.call_tool("a%2Eb.c", {})

    assert [tool["name"] for tool in tools] == ["a.b%2Ec", "a%2Eb.c"]
    first, second = FakeSDKClient.instances
    assert first.calls == [("b.c", {})]
    assert second.calls == [("c", {})]


@pytest.mark.asyncio
async def test_call_discovers_tools_lazily_and_rejects_unknown_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "Client", FakeSDKClient)
    client = MCPClient(
        (ServerConfig(name="docs", url="https://example.com/docs"),)
    )

    async with client:
        result = await client.call_tool("docs.details", {})
        assert result["is_error"] is False
        with pytest.raises(MCPClientError, match="Unknown MCP tool"):
            await client.call_tool("docs.missing", {})


@pytest.mark.asyncio
async def test_preserves_tool_error_as_readable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "Client", FakeSDKClient)
    FakeSDKClient.return_tool_error = True
    client = MCPClient(
        (ServerConfig(name="files", url="https://example.com/files"),)
    )

    async with client:
        result = await client.call_tool("files.search", {"query": "secret"})

    assert result["is_error"] is True
    assert result["content"] == [
        {"type": "text", "text": "permission denied"}
    ]


@pytest.mark.asyncio
async def test_wraps_tool_invocation_failure_with_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "Client", FakeSDKClient)
    FakeSDKClient.fail_call = True
    client = MCPClient(
        (ServerConfig(name="docs", url="https://example.com/docs"),)
    )

    async with client:
        with pytest.raises(
            MCPClientError,
            match="Could not call 'docs.search': server stopped responding",
        ):
            await client.call_tool("docs.search", {"query": "MCP"})


@pytest.mark.asyncio
async def test_connect_all_rolls_back_connections_opened_before_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "Client", FakeSDKClient)
    FakeSDKClient.fail_target = "https://example.com/broken"
    client = MCPClient(
        (
            ServerConfig(name="working", url="https://example.com/working"),
            ServerConfig(name="broken", url="https://example.com/broken"),
        )
    )

    with pytest.raises(MCPClientError, match="connection refused"):
        await client.connect_all()

    assert client.connected_servers == ()
    assert FakeSDKClient.instances[0].closed is True


@pytest.mark.asyncio
async def test_disconnect_rejects_non_reverse_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "Client", FakeSDKClient)
    client = MCPClient(
        (
            ServerConfig(name="first", url="https://example.com/first"),
            ServerConfig(name="second", url="https://example.com/second"),
        )
    )
    await client.connect_all()

    with pytest.raises(MCPClientError, match="reverse connection order"):
        await client.disconnect("first")

    assert client.connected_servers == ("first", "second")
    await client.disconnect_all()
    assert len(client.connected_servers) == 0


@pytest.mark.asyncio
async def test_connect_rollback_continues_after_disconnect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "Client", FakeSDKClient)
    first_target = "https://example.com/first"
    second_target = "https://example.com/second"
    broken_target = "https://example.com/broken"
    FakeSDKClient.fail_target = broken_target
    FakeSDKClient.close_failures_by_target = {second_target: 1}
    client = MCPClient(
        (
            ServerConfig(name="first", url=first_target),
            ServerConfig(name="second", url=second_target),
            ServerConfig(name="broken", url=broken_target),
        )
    )

    with pytest.raises(
        MCPClientError,
        match="connection refused; rollback cleanup failed: .*close failed",
    ):
        await client.connect_all()

    first, second, _ = FakeSDKClient.instances
    assert second.close_attempts == 1
    assert first.closed is True
    assert client.connected_servers == ()


@pytest.mark.asyncio
async def test_real_stdio_server_is_discovered_and_invoked() -> None:
    server_script = Path(__file__).parent / "fixtures" / "echo_mcp_server.py"
    client = MCPClient(
        (
            ServerConfig(
                name="fixture",
                command=sys.executable,
                args=(str(server_script),),
            ),
        )
    )

    async with client:
        tools = await client.list_tools()
        result = await client.call_tool("fixture.echo", {"value": "hello MCP"})

    assert [tool["name"] for tool in tools] == ["fixture.echo"]
    assert result["is_error"] is False
    assert result["structured_content"] == {"result": "hello MCP"}


@pytest.mark.asyncio
async def test_real_stdio_servers_enforce_reverse_disconnect_order() -> None:
    server_script = Path(__file__).parent / "fixtures" / "echo_mcp_server.py"
    client = MCPClient(
        (
            ServerConfig(
                name="first",
                command=sys.executable,
                args=(str(server_script),),
            ),
            ServerConfig(
                name="second",
                command=sys.executable,
                args=(str(server_script),),
            ),
        )
    )
    await client.connect_all()

    try:
        with pytest.raises(MCPClientError, match="reverse connection order"):
            await client.disconnect("first")
    finally:
        await client.disconnect_all()

    assert len(client.connected_servers) == 0
