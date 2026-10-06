"""Concrete multi-server client built on the official MCP Python SDK."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from contextlib import AsyncExitStack
from types import TracebackType

from mcp import Client, StdioServerParameters
from mcp.types import CallToolResult, Tool

from coding_assistant.config import ServerConfig
from coding_assistant.contracts import Payload


class MCPClientError(RuntimeError):
    """A configured server could not be connected, discovered, or invoked."""


class MCPClient:
    """Own server lifecycles and expose one collision-safe MCP tool namespace.

    Tools are presented as ``server_name.tool_name``. Qualification preserves
    the server needed for routing and prevents tools with the same name on two
    servers from overwriting each other.
    """

    def __init__(self, configs: Sequence[ServerConfig]) -> None:
        self._configs = {config.name: config for config in configs}
        if len(self._configs) != len(configs):
            raise ValueError("MCP server names must be unique")
        self._clients: dict[str, Client] = {}
        self._stacks: dict[str, AsyncExitStack] = {}
        self._routes: dict[str, tuple[str, str]] = {}

    @property
    def connected_servers(self) -> tuple[str, ...]:
        """Return connected server names in connection order."""

        return tuple(self._clients)

    async def __aenter__(self) -> MCPClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        await self.disconnect_all()

    async def connect(self, server_name: str) -> None:
        """Open one configured connection; repeated calls are idempotent."""

        if server_name in self._clients:
            return
        config = self._get_config(server_name)
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            target = _connection_target(config)
            sdk_client = Client(target, read_timeout_seconds=config.timeout_seconds)
            connected = await stack.enter_async_context(sdk_client)
        except Exception as exc:
            await stack.aclose()
            raise MCPClientError(
                f"Could not connect to MCP server {server_name!r}: "
                f"{_describe_exception(exc)}"
            ) from exc

        self._clients[server_name] = connected
        self._stacks[server_name] = stack

    async def connect_all(self) -> None:
        """Connect every configured server, rolling back this attempt on failure."""

        newly_connected: list[str] = []
        try:
            for server_name in self._configs:
                if server_name not in self._clients:
                    await self.connect(server_name)
                    newly_connected.append(server_name)
        except BaseException:
            for server_name in reversed(newly_connected):
                await self.disconnect(server_name)
            raise

    async def disconnect(self, server_name: str) -> None:
        """Close one connection; repeated calls are safe."""

        self._clients.pop(server_name, None)
        self._routes = {
            name: route
            for name, route in self._routes.items()
            if route[0] != server_name
        }
        stack = self._stacks.pop(server_name, None)
        if stack is None:
            return
        try:
            await stack.aclose()
        except Exception as exc:
            raise MCPClientError(
                f"Could not disconnect MCP server {server_name!r}: "
                f"{_describe_exception(exc)}"
            ) from exc

    async def disconnect_all(self) -> None:
        """Close all active connections in reverse connection order."""

        failures: list[str] = []
        for server_name in reversed(tuple(self._stacks)):
            try:
                await self.disconnect(server_name)
            except MCPClientError as exc:
                failures.append(str(exc))
        if failures:
            raise MCPClientError("; ".join(failures))

    async def list_tools(self) -> Sequence[Payload]:
        """Discover and normalize tools from every configured server."""

        await self.connect_all()
        discovered: list[Payload] = []
        routes: dict[str, tuple[str, str]] = {}
        for server_name, client in self._clients.items():
            try:
                tools = await _list_all_tools(client)
            except Exception as exc:
                raise MCPClientError(
                    f"Could not discover tools from MCP server {server_name!r}: "
                    f"{_describe_exception(exc)}"
                ) from exc

            for tool in tools:
                qualified_name = f"{server_name}.{tool.name}"
                routes[qualified_name] = (server_name, tool.name)
                discovered.append(_normalize_tool(server_name, qualified_name, tool))

        self._routes = routes
        return tuple(discovered)

    async def call_tool(self, name: str, arguments: Payload) -> Payload:
        """Invoke a previously discovered qualified tool name."""

        if name not in self._routes:
            await self.list_tools()
        try:
            server_name, server_tool_name = self._routes[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._routes)) or "(none)"
            raise MCPClientError(
                f"Unknown MCP tool {name!r}; discovered tools: {available}"
            ) from exc

        client = self._clients[server_name]
        try:
            result = await client.call_tool(server_tool_name, dict(arguments))
        except Exception as exc:
            raise MCPClientError(
                f"Could not call {name!r}: {_describe_exception(exc)}"
            ) from exc
        return _normalize_result(name, server_name, result)

    def _get_config(self, server_name: str) -> ServerConfig:
        try:
            return self._configs[server_name]
        except KeyError as exc:
            available = ", ".join(sorted(self._configs)) or "(none)"
            raise MCPClientError(
                f"Unknown MCP server {server_name!r}; configured servers: {available}"
            ) from exc


async def _list_all_tools(client: Client) -> list[Tool]:
    tools: list[Tool] = []
    cursor: str | None = None
    while True:
        result = await client.list_tools(cursor=cursor)
        tools.extend(result.tools)
        cursor = result.next_cursor
        if cursor is None:
            return tools


def _normalize_tool(server_name: str, qualified_name: str, tool: Tool) -> Payload:
    return {
        "name": qualified_name,
        "server": server_name,
        "server_tool_name": tool.name,
        "description": tool.description or "",
        "input_schema": dict(tool.input_schema),
    }


def _normalize_result(
    qualified_name: str, server_name: str, result: CallToolResult
) -> Payload:
    payload: dict[str, object] = {
        "type": "tool_result",
        "name": qualified_name,
        "server": server_name,
        "is_error": result.is_error,
        "content": [
            block.model_dump(by_alias=True, exclude_none=True) for block in result.content
        ],
    }
    if result.structured_content is not None:
        payload["structured_content"] = result.structured_content
    if result.meta is not None:
        payload["metadata"] = result.meta
    return payload


def _connection_target(config: ServerConfig) -> str | StdioServerParameters:
    if config.url is not None:
        return config.url

    assert config.command is not None
    command = shutil.which(config.command)
    if command is None:
        raise MCPClientError(
            f"Executable {config.command!r} was not found on PATH for server "
            f"{config.name!r}"
        )
    return StdioServerParameters(
        command=command,
        args=list(config.args),
        env=config.env or None,
        cwd=config.cwd,
    )


def _describe_exception(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(_describe_exception(nested) for nested in exc.exceptions)
    return str(exc) or type(exc).__name__
