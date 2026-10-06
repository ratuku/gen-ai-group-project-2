from __future__ import annotations

import importlib
from collections.abc import AsyncIterator, Mapping, Sequence

import pytest

from coding_assistant.contracts import AgentLoop, MCPClient, ModelProvider, Payload


class FakeProvider:
    async def stream(
        self,
        messages: Sequence[Payload],
        tools: Sequence[Payload],
    ) -> AsyncIterator[Payload]:
        del tools
        if not any(message.get("type") == "tool_result" for message in messages):
            yield {
                "type": "tool_call",
                "name": "read_file",
                "arguments": {"path": "README.md"},
            }
        else:
            yield {"type": "text", "content": "README inspected"}
            yield {"type": "completed"}


class FakeMCPClient:
    async def list_tools(self) -> Sequence[Payload]:
        return ({"name": "read_file", "description": "Read a file"},)

    async def call_tool(self, name: str, arguments: Payload) -> Payload:
        return {
            "type": "tool_result",
            "name": name,
            "arguments": arguments,
            "content": "README contents",
        }


class FakeAgent:
    def __init__(self, provider: ModelProvider, mcp_client: MCPClient) -> None:
        self.provider = provider
        self.mcp_client = mcp_client

    async def run(self, task: str) -> AsyncIterator[Payload]:
        messages: list[Payload] = [{"role": "user", "content": task}]
        tools = await self.mcp_client.list_tools()
        while True:
            tool_requested = False
            async for event in self.provider.stream(messages, tools):
                yield event
                if event.get("type") == "tool_call":
                    name = event.get("name")
                    arguments = event.get("arguments")
                    if not isinstance(name, str) or not isinstance(arguments, Mapping):
                        raise ValueError("invalid fake tool call")
                    result = await self.mcp_client.call_tool(name, arguments)
                    messages.append(result)
                    yield result
                    tool_requested = True
                elif event.get("type") == "completed":
                    return
            if not tool_requested:
                return


def test_scaffolded_packages_import() -> None:
    packages = (
        "coding_assistant.cli",
        "coding_assistant.agent",
        "coding_assistant.providers",
        "coding_assistant.mcp",
        "coding_assistant.execution",
        "coding_assistant.config",
        "rag_server",
        "rag_server.ingestion",
        "rag_server.chunking",
        "rag_server.embeddings",
        "rag_server.retrieval",
        "rag_server.storage",
    )
    for package in packages:
        assert importlib.import_module(package)


def test_minimal_fakes_satisfy_protocols() -> None:
    provider = FakeProvider()
    client = FakeMCPClient()
    agent = FakeAgent(provider, client)
    assert isinstance(provider, ModelProvider)
    assert isinstance(client, MCPClient)
    assert isinstance(agent, AgentLoop)


@pytest.mark.asyncio
async def test_vertical_slice_reaches_tool_result_and_completion() -> None:
    agent: AgentLoop = FakeAgent(FakeProvider(), FakeMCPClient())
    events = [event async for event in agent.run("inspect the README")]
    assert [event["type"] for event in events] == [
        "tool_call",
        "tool_result",
        "text",
        "completed",
    ]
