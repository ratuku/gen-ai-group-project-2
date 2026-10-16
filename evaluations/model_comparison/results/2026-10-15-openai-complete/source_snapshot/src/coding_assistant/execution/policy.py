"""Provider-neutral policy gate for validated MCP tool execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from copy import deepcopy
from typing import Literal

from coding_assistant.contracts import MCPClient, Payload


ExecutionMode = Literal["confirm", "auto"]
ApprovalCallback = Callable[[str, Payload], Awaitable[bool]]


class PolicyMCPClient:
    """Apply an execution policy before delegating valid calls to MCP."""

    def __init__(
        self,
        client: MCPClient,
        *,
        mode: ExecutionMode,
        approve: ApprovalCallback | None = None,
    ) -> None:
        if mode not in {"confirm", "auto"}:
            raise ValueError("Execution mode must be 'confirm' or 'auto'")
        if mode == "confirm" and approve is None:
            raise ValueError("Confirmation mode requires an approval callback")
        self._client = client
        self.mode = mode
        self._approve = approve

    async def list_tools(self) -> Sequence[Payload]:
        """Return the delegate's tool definitions unchanged."""

        return await self._client.list_tools()

    async def call_tool(self, name: str, arguments: Payload) -> Payload:
        """Execute automatically or require approval without mutating arguments."""

        if self.mode == "confirm":
            assert self._approve is not None
            approved = await self._approve(name, deepcopy(dict(arguments)))
            if not approved:
                return {
                    "type": "tool_result",
                    "name": name,
                    "is_error": True,
                    "error_code": "tool_rejected",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"User rejected tool {name!r}; the tool was not executed."
                            ),
                        }
                    ],
                }
        return await self._client.call_tool(name, arguments)
