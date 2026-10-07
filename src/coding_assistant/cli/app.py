"""Small terminal UI over the AgentLoop contract and shared MCP client."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from importlib import import_module
import json
from pathlib import Path
import sys
from textwrap import shorten
from typing import TextIO

from prompt_toolkit import PromptSession

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.agent.demo import WorkspaceDemoProvider
from coding_assistant.config import load_mcp_config
from coding_assistant.contracts import AgentLoop, Payload
from coding_assistant.mcp import MCPClient

HELP = "/help: show commands | /servers: connections | /tools: tools | /exit or /quit: exit"
AgentFactory = Callable[[MCPClient], AgentLoop]
ReadPrompt = Callable[[str], Awaitable[str]]


def describe_tools(tools: Sequence[Payload]) -> str:
    return "\n".join(
        f"  {tool['name']} - {shorten(str(tool.get('description', '')), width=100)}"
        for tool in tools
    ) or "  No tools available."


class ConnectionDemoAgent:
    """Temporary discovery-only adapter, not the autonomous agent implementation."""

    def __init__(self, client: MCPClient) -> None:
        self.client = client

    async def run(self, task: str) -> AsyncIterator[Payload]:
        request = task.strip().lower()
        if request in {"list tools", "show tools", "tools"}:
            yield {"type": "text", "content": describe_tools(await self.client.list_tools())}
        elif request in {"list servers", "show servers", "servers"}:
            yield {"type": "text", "content": ", ".join(self.client.connected_servers) or "No servers connected."}
        else:
            yield {
                "type": "error",
                "content": "Connection demo supports 'list tools' or 'list servers'. "
                "Coding tasks require an agent loop supplied with --agent module:factory.",
            }
            return
        yield {"type": "completed"}


def load_agent_factory(spec: str) -> AgentFactory:
    """Load a synchronous factory accepting the already-connected MCP client."""
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("--agent must be module:factory")
    factory = getattr(import_module(module_name), attribute)
    if not callable(factory):
        raise ValueError(f"Agent factory {spec!r} is not callable")

    def create(client: MCPClient) -> AgentLoop:
        agent = factory(client)
        if not isinstance(agent, AgentLoop):
            raise ValueError("Agent factory must return an object with async run(task)")
        return agent

    return create


def result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(block["text"]) if isinstance(block, Mapping) and "text" in block
            else json.dumps(block, ensure_ascii=False, default=str)
            for block in content
        )
    return json.dumps(content, ensure_ascii=False, default=str)


async def display_task(agent: AgentLoop, task: str, output: TextIO) -> int:
    """Render streamed contract events without owning reasoning or tool execution."""
    line_open = False
    failed = False
    try:
        async for event in agent.run(task):
            kind = event.get("type")
            if kind == "text":
                content = str(event.get("content", ""))
                output.write(content)
                if content:
                    line_open = not content.endswith("\n")
                output.flush()
                continue
            if line_open:
                print(file=output)
                line_open = False
            if kind == "tool_call":
                print(f"[Tool] {event.get('name', 'unknown')}", file=output)
            elif kind == "tool_result":
                is_error = bool(event.get("is_error", False))
                label = "Tool error" if is_error else "Result"
                print(f"[{label}] {event.get('name', '')}", file=output)
                print(result_text(event.get("content", event.get("structured_content", ""))), file=output)
            elif kind == "error":
                failed = True
                print(f"[Error] {event.get('content', event.get('message', 'Task failed'))}", file=output)
            elif kind == "completed":
                print("[Failed]" if failed else "[Done]", file=output)
            elif kind == "status":
                print(f"[Status] {event.get('content', '')}", file=output)
            else:
                print(f"[Event] {result_text(dict(event))}", file=output)
            output.flush()
    except Exception as error:
        if line_open:
            print(file=output)
        print(f"[Error] {error}", file=output, flush=True)
        return 1
    if line_open:
        print(file=output, flush=True)
    return 1 if failed else 0


async def run_cli(
    options: argparse.Namespace,
    *,
    output: TextIO,
    read_prompt: ReadPrompt | None = None,
    agent_factory: AgentFactory | None = None,
) -> int:
    config = load_mcp_config(options.config, workspace_root=options.workspace)
    factory = agent_factory or (load_agent_factory(options.agent) if options.agent else ConnectionDemoAgent)
    async with MCPClient(config.servers) as client:
        tools = await client.list_tools()
        print(f"Connected to {len(client.connected_servers)} MCP server(s):", file=output)
        for name in client.connected_servers:
            count = sum(tool.get("server") == name for tool in tools)
            print(f"  {name}: {count} tool(s)", file=output)
        if not config.servers:
            print("No MCP servers configured. Add servers to your --config file.", file=output)
        if options.demo_loop and agent_factory is None:
            print("Scripted agent-loop demo; real MCP calls, no live LLM.", file=output)
            agent: AgentLoop = BasicAgentLoop(WorkspaceDemoProvider(), client, max_iterations=options.max_iterations)
        else:
            if options.agent is None and agent_factory is None:
                print("Connection demo only; use --demo-loop to try the basic agent cycle.", file=output)
            agent = factory(client)
        if options.task is not None:
            return await display_task(agent, options.task.strip(), output)

        hint = "inspect workspace" if options.demo_loop else "list tools"
        print(f"Enter a task (demo: '{hint}'). " + HELP, file=output, flush=True)
        if read_prompt is None:
            session: PromptSession[str] = PromptSession()
            read_prompt = session.prompt_async
        while True:
            try:
                task = (await read_prompt("you> ")).strip()
            except EOFError:
                print("Goodbye.", file=output)
                return 0
            except KeyboardInterrupt:
                print("\nInterrupted. Goodbye.", file=output)
                return 130
            if not task:
                continue
            if task.lower() in {"/exit", "/quit", "exit", "quit"}:
                print("Goodbye.", file=output)
                return 0
            if task == "/help":
                print(HELP, file=output)
            elif task == "/servers":
                print("\n".join(client.connected_servers) or "No servers connected.", file=output)
            elif task == "/tools":
                print(describe_tools(tools), file=output)
            elif task.startswith("/"):
                print("Unknown command. " + HELP, file=output)
            else:
                await display_task(agent, task, output)
            output.flush()


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Basic coding-assistant CLI and MCP connection demo.")
    parser.add_argument("--config", type=Path, default=Path("config/mcp.json"), help="MCP JSON config (default: config/mcp.json).")
    parser.add_argument("--workspace", type=Path, help="Workspace exposed to configured servers (default: config parent directory's parent).")
    parser.add_argument("--task", help="Submit one task and exit instead of opening a prompt.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--agent", metavar="MODULE:FACTORY", help="Agent factory accepting MCPClient; default: connection-only demo.")
    mode.add_argument("--demo-loop", action="store_true", help="Run the basic agent loop with a scripted, read-only workspace demo (no LLM).")
    parser.add_argument("--max-iterations", type=int, default=8, help="Model-step limit for --demo-loop (default: 8); custom factories configure their own limit.")
    options = parser.parse_args(arguments)
    if options.max_iterations < 1:
        parser.error("--max-iterations must be positive")
    if options.task is not None and not options.task.strip():
        parser.error("--task must not be empty")
    return options


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        return asyncio.run(run_cli(options, output=sys.stdout))
    except KeyboardInterrupt:
        print("\nInterrupted. Goodbye.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
