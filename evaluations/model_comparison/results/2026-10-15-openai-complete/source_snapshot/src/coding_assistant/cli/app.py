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

from coding_assistant.config import load_mcp_config
from coding_assistant.cli.display import ASSISTANT_NAME, TerminalView
from coding_assistant.contracts import AgentLoop, MCPClient as MCPClientContract, Payload
from coding_assistant.execution import ExecutionMode, PolicyMCPClient
from coding_assistant.mcp import MCPClient

HELP = "/help: show commands | /servers: connections | /tools: tools | /exit or /quit: exit"
AgentFactory = Callable[[MCPClientContract], AgentLoop]
ReadPrompt = Callable[[str], Awaitable[str]]
PROVIDER_FACTORIES = {
    "openai": "coding_assistant.providers.openai:create_agent",
    "groq": "coding_assistant.providers.groq:create_agent",
    "ollama": "coding_assistant.providers.ollama:create_agent",
}


def describe_tools(tools: Sequence[Payload]) -> str:
    return "\n".join(
        f"  {tool['name']} - {shorten(str(tool.get('description', '')), width=100)}"
        for tool in tools
    ) or "  No tools available."


class ConnectionCheckAgent:
    """Read-only adapter for inspecting configured MCP connections and tools."""

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
                "content": "Connection check supports 'list tools' or 'list servers'. "
                "For coding tasks, launch with --provider groq or --provider ollama; "
                "custom agents use --agent module:factory.",
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

    def create(client: MCPClientContract) -> AgentLoop:
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
    view = TerminalView(output)
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
                view.tool(str(event.get("name", "unknown")), event.get("arguments"))
            elif kind == "tool_result":
                is_error = bool(event.get("is_error", False))
                label = "Tool error" if is_error else "Result"
                view.panel(label, str(event.get("name", "")),
                           result_text(event.get("content") or event.get("structured_content", "")))
            elif kind == "error":
                failed = True
                view.marker("Error", str(event.get("content", event.get("message", "Task failed"))))
            elif kind == "completed":
                failed = failed or event.get("reason") in {"error", "iteration_limit"}
                view.marker("Failed" if failed else "Done")
            elif kind == "status":
                view.marker("Status", str(event.get("content", "")))
            else:
                print(f"[Event] {result_text(dict(event))}", file=output)
            output.flush()
    except Exception as error:
        if line_open:
            print(file=output)
        view.marker("Error", str(error))
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
    connection_check = options.connection_check and agent_factory is None
    if agent_factory is not None:
        factory: AgentFactory | None = agent_factory
    elif connection_check:
        factory = None
    else:
        factory = load_agent_factory(options.agent or PROVIDER_FACTORIES[options.provider or "groq"])
    view = TerminalView(output)
    active_prompt = read_prompt
    prompt_session: PromptSession[str] | None = None

    async def prompt_user(prompt: str) -> str:
        nonlocal active_prompt, prompt_session
        if active_prompt is not None:
            return await active_prompt(prompt)
        if prompt_session is None:
            prompt_session = PromptSession()
        return str(await prompt_session.prompt_async(prompt))

    async def approve_tool(name: str, arguments: Payload) -> bool:
        del arguments  # The immediately preceding tool panel displays exact arguments.
        while True:
            try:
                answer = (await prompt_user(f"Execute {name}? [y/N] ")).strip().lower()
            except EOFError:
                view.marker("Rejected", f"{name}; input closed")
                return False
            if answer in {"y", "yes"}:
                view.marker("Approved", name)
                return True
            if answer in {"", "n", "no"}:
                view.marker("Rejected", f"{name}; tool was not executed")
                return False
            view.marker("Approval", "Please answer y or n.")

    async with MCPClient(config.servers) as client:
        tools = await client.list_tools()
        print(f"Connected to {len(client.connected_servers)} MCP server(s):", file=output)
        for name in client.connected_servers:
            count = sum(tool.get("server") == name for tool in tools)
            print(f"  {name}: {count} tool(s)", file=output)
        if not config.servers:
            print("No MCP servers configured. Add servers to your --config file.", file=output)
        if connection_check:
            print("Connection check only; no model or tool execution.", file=output)
            agent: AgentLoop = ConnectionCheckAgent(client)
        else:
            assert factory is not None
            execution_mode: ExecutionMode = options.execution_mode
            policy_client = PolicyMCPClient(
                client,
                mode=execution_mode,
                approve=approve_tool if execution_mode == "confirm" else None,
            )
            agent = factory(policy_client)
        provider = getattr(agent, "provider", None)
        if connection_check:
            provider_name, model_name = "Connection check", "No LLM"
        else:
            provider_name = type(provider).__name__.removesuffix("Provider") if provider is not None else "Custom agent"
            model_name = str(getattr(provider, "model", "Custom agent"))
        if connection_check:
            execution = "Connection discovery only"
        elif options.execution_mode == "confirm":
            execution = "Confirmation required"
        else:
            execution = "Automatic tool execution"
        view.welcome(config.workspace_root, provider_name, model_name, len(client.connected_servers), execution)
        if options.task is not None:
            return await display_task(agent, options.task.strip(), output)

        if connection_check:
            greeting = "Enter a connection check ('list tools' or 'list servers'). "
        else:
            greeting = "Enter a task. "
        print(greeting + HELP, file=output, flush=True)
        while True:
            try:
                task = (await prompt_user(f"{ASSISTANT_NAME.lower()}> ")).strip()
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
                view.tools([(str(tool["name"]), str(tool.get("description", ""))) for tool in tools])
            elif task.startswith("/"):
                print("Unknown command. " + HELP, file=output)
            else:
                await display_task(agent, task, output)
            output.flush()


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{ASSISTANT_NAME}: an autonomous CLI coding assistant with MCP tools.")
    parser.add_argument("--config", type=Path, default=Path("config/mcp.json"), help="MCP JSON config (default: config/mcp.json).")
    parser.add_argument("--workspace", type=Path, help="Workspace exposed to configured servers (default: config parent directory's parent).")
    parser.add_argument("--task", help="Submit one task and exit instead of opening a prompt.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--provider", choices=tuple(PROVIDER_FACTORIES), help="Model provider (default: groq); configure credentials/model in the environment.")
    mode.add_argument("--agent", metavar="MODULE:FACTORY", help="Custom agent factory accepting MCPClient.")
    mode.add_argument("--connection-check", action="store_true", help="List MCP servers/tools without using an LLM.")
    parser.add_argument("--execution-mode", choices=("confirm", "auto"), default="confirm", help="Tool execution policy (default: confirm).")
    options = parser.parse_args(arguments)
    if options.agent is not None:
        module_name, separator, attribute = options.agent.partition(":")
        if not separator or not module_name.strip() or not attribute.strip() or ":" in attribute:
            parser.error("--agent must be module:factory")
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
