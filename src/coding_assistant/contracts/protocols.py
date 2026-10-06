"""Provisional boundaries for the first end-to-end vertical slice.

These intentionally use provider-neutral mappings. Stronger domain models should be
extracted only after a working CLI-to-MCP flow validates what data is actually needed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Protocol, runtime_checkable

Payload = Mapping[str, object]


@runtime_checkable
class ModelProvider(Protocol):
    """Streams provider-neutral events from a local or cloud model adapter."""

    def stream(
        self,
        messages: Sequence[Payload],
        tools: Sequence[Payload],
    ) -> AsyncIterator[Payload]:
        """Stream text, tool requests, and completion events."""


@runtime_checkable
class AgentLoop(Protocol):
    """Coordinates the first CLI, provider, and MCP vertical slice."""

    def run(self, task: str) -> AsyncIterator[Payload]:
        """Stream UI-facing events until the task finishes or fails."""


@runtime_checkable
class MCPClient(Protocol):
    """Discovers and invokes tools exposed by configured MCP servers."""

    async def list_tools(self) -> Sequence[Payload]:
        """Return normalized definitions from all connected servers."""

    async def call_tool(self, name: str, arguments: Payload) -> Payload:
        """Invoke a discovered tool and return its normalized result."""
