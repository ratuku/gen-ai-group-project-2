from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
import asyncio
import io
import json
from pathlib import Path
import sys

import pytest

from coding_assistant.cli import app
from coding_assistant.agent import BasicAgentLoop
from coding_assistant.contracts import Payload
from coding_assistant.mcp import MCPClient


class FakeClient:
    instances: list[FakeClient] = []

    def __init__(self, configs: Sequence[object]) -> None:
        self.configs = tuple(configs)
        self.connected_servers = ("filesystem", "external")
        self.closed = False
        self.instances.append(self)

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True

    async def list_tools(self) -> list[Payload]:
        return [{"name": f"{name}.search", "server": name, "description": "Search documents"}
                for name in self.connected_servers]


class RecordingAgent:
    def __init__(self) -> None:
        self.tasks: list[str] = []

    async def run(self, task: str) -> AsyncIterator[Payload]:
        self.tasks.append(task)
        if task == "fail":
            raise RuntimeError("Task failed")
        if task == "error":
            yield {"type": "error", "content": "Provider unavailable"}
            yield {"type": "completed"}
            return
        yield {"type": "text", "content": "Hello "}
        yield {"type": "text", "content": task}
        yield {"type": "tool_call", "name": "filesystem.read_file"}
        yield {"type": "tool_result", "name": "filesystem.read_file",
               "content": [{"type": "text", "text": "file contents"}]}
        yield {"type": "completed"}


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "mcp.json"
    path.write_text('{"mcpServers": {}}', encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_prompt_tasks_commands_and_exit_close_connections(
    config: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "MCPClient", FakeClient)
    inputs = iter([" ", "/help", "/servers", "/tools", "/unknown", "fail", "error", "read README", "/exit"])
    async def read_prompt(prompt: str) -> str:
        return next(inputs)
    agent = RecordingAgent()
    output = io.StringIO()
    result = await app.run_cli(
        app.parse_arguments(["--config", str(config)]), output=output,
        read_prompt=read_prompt, agent_factory=lambda client: agent,
    )
    assert result == 0
    assert agent.tasks == ["fail", "error", "read README"]
    text = output.getvalue()
    assert "Connected to 2 MCP server(s)" in text
    assert "external.search" in text
    assert "Unknown command" in text
    assert "[Error] Task failed" in text
    assert "[Error] Provider unavailable\n[Failed]" in text
    assert "Hello read README\n[Tool] filesystem.read_file" in text
    assert "file contents" in text
    assert "[Done]" in text
    assert text.endswith("Goodbye.\n")
    assert FakeClient.instances[-1].closed


@pytest.mark.parametrize("exception,code", [(EOFError, 0), (KeyboardInterrupt, 130)])
@pytest.mark.asyncio
async def test_eof_and_interrupt_close_connections(
    config: Path, monkeypatch: pytest.MonkeyPatch, exception: type[BaseException], code: int,
) -> None:
    monkeypatch.setattr(app, "MCPClient", FakeClient)
    async def read_prompt(prompt: str) -> str:
        raise exception()
    result = await app.run_cli(
        app.parse_arguments(["--config", str(config), "--connection-demo"]), output=io.StringIO(), read_prompt=read_prompt,
    )
    assert result == code
    assert FakeClient.instances[-1].closed


@pytest.mark.parametrize("task,code", [("read README", 0), ("fail", 1)])
@pytest.mark.asyncio
async def test_one_shot_does_not_prompt(
    config: Path, monkeypatch: pytest.MonkeyPatch, task: str, code: int,
) -> None:
    monkeypatch.setattr(app, "MCPClient", FakeClient)
    async def never_prompt(prompt: str) -> str:
        raise AssertionError("One-shot mode must not prompt")
    result = await app.run_cli(
        app.parse_arguments(["--config", str(config), "--task", task]),
        output=io.StringIO(), read_prompt=never_prompt,
        agent_factory=lambda client: RecordingAgent(),
    )
    assert result == code
    assert FakeClient.instances[-1].closed


@pytest.mark.asyncio
async def test_connection_failure_is_not_reported_as_success(
    config: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenClient(FakeClient):
        async def list_tools(self) -> list[Payload]:
            raise RuntimeError("External server unavailable")
    monkeypatch.setattr(app, "MCPClient", BrokenClient)
    output = io.StringIO()
    with pytest.raises(RuntimeError, match="unavailable"):
        await app.run_cli(app.parse_arguments(["--config", str(config)]), output=output)
    assert "Connected to" not in output.getvalue()
    assert FakeClient.instances[-1].closed


@pytest.mark.asyncio
async def test_error_event_returns_failure() -> None:
    class ErrorAgent:
        async def run(self, task: str) -> AsyncIterator[Payload]:
            yield {"type": "error", "content": "Provider unavailable"}
            yield {"type": "completed"}
    output = io.StringIO()
    assert await app.display_task(ErrorAgent(), "task", output) == 1
    assert "[Failed]" in output.getvalue()
    assert "[Done]" not in output.getvalue()


@pytest.mark.asyncio
async def test_demo_does_not_claim_to_execute_coding_tasks(
    config: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "MCPClient", FakeClient)
    output = io.StringIO()
    result = await app.run_cli(
        app.parse_arguments(["--config", str(config), "--connection-demo", "--task", "Change a file"]),
        output=output,
    )
    assert result == 1
    assert "Connection demo only" in output.getvalue()
    assert "For coding tasks, launch with --provider groq or --provider ollama" in output.getvalue()
    assert "[Done]" not in output.getvalue()
    assert FakeClient.instances[-1].closed


@pytest.mark.asyncio
async def test_cancellation_during_task_closes_connections(
    config: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "MCPClient", FakeClient)
    started = asyncio.Event()
    class WaitingAgent:
        async def run(self, task: str) -> AsyncIterator[Payload]:
            started.set()
            await asyncio.Event().wait()
            yield {"type": "completed"}
    task = asyncio.create_task(app.run_cli(
        app.parse_arguments(["--config", str(config), "--task", "Wait"]),
        output=io.StringIO(), agent_factory=lambda client: WaitingAgent(),
    ))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert FakeClient.instances[-1].closed


def test_help_needs_no_server(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        app.main(["--help"])
    assert error.value.code == 0
    assert "--config" in capsys.readouterr().out


def test_missing_config_returns_readable_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert app.main(["--config", str(tmp_path / "missing.json"), "--task", "list tools"]) == 1
    error = capsys.readouterr().err
    assert "Configuration file not found" in error
    assert "Traceback" not in error


def test_blank_task_rejected() -> None:
    with pytest.raises(SystemExit) as error:
        app.parse_arguments(["--task", "  "])
    assert error.value.code == 2


@pytest.mark.parametrize("arguments", [
    ["--unknown"], ["--max-iterations", "0"],
    ["--max-iterations", "not-a-number"],
    ["--demo-loop", "--agent", "example:create_agent"],
    ["--agent", "missing_separator"], ["--agent", ":factory"],
    ["--agent", "module:"], ["--agent", "module:factory:extra"],
])
def test_invalid_arguments_exit_with_usage_error(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        app.main(arguments)
    assert error.value.code == 2


@pytest.mark.parametrize("command", ["/exit", "/quit", "exit", "quit"])
@pytest.mark.asyncio
async def test_exit_aliases_close_connections(
    config: Path, monkeypatch: pytest.MonkeyPatch, command: str,
) -> None:
    monkeypatch.setattr(app, "MCPClient", FakeClient)
    async def read_prompt(prompt: str) -> str:
        return command
    output = io.StringIO()
    assert await app.run_cli(
        app.parse_arguments(["--config", str(config), "--connection-demo"]),
        output=output, read_prompt=read_prompt,
    ) == 0
    assert output.getvalue().endswith("Goodbye.\n")
    assert FakeClient.instances[-1].closed


@pytest.mark.parametrize("mode, greeting", [
    ("connection", "Enter a task (demo: 'list tools')."),
    ("scripted", "Enter a task (demo: 'inspect workspace')."),
    ("selected", "Enter a task."),
    ("injected", "Enter a task."),
])
@pytest.mark.asyncio
async def test_interactive_prompt_matches_selected_agent(
    config: Path, monkeypatch: pytest.MonkeyPatch, mode: str, greeting: str,
) -> None:
    from types import ModuleType
    monkeypatch.setattr(app, "MCPClient", FakeClient)
    arguments = ["--config", str(config)]
    factory: app.AgentFactory | None = None
    agent = RecordingAgent()
    if mode == "scripted":
        config.write_text(json.dumps({"mcpServers": {
            "filesystem": {"url": "https://example.com/filesystem"},
        }}), encoding="utf-8")
        arguments.append("--demo-loop")
    elif mode == "connection":
        arguments.append("--connection-demo")
    elif mode == "selected":
        module = ModuleType("cli_prompt_agent")
        def create(client: MCPClient) -> RecordingAgent:
            return agent
        monkeypatch.setattr(module, "create", create, raising=False)
        monkeypatch.setitem(sys.modules, "cli_prompt_agent", module)
        arguments.extend(["--agent", "cli_prompt_agent:create"])
    elif mode == "injected":
        factory = lambda client: agent
    async def read_prompt(prompt: str) -> str:
        return "/exit"
    output = io.StringIO()
    assert await app.run_cli(
        app.parse_arguments(arguments), output=output,
        read_prompt=read_prompt, agent_factory=factory,
    ) == 0
    assert greeting + " " + app.HELP in output.getvalue()
    if mode in {"selected", "injected"}:
        assert "(demo:" not in output.getvalue()
    assert FakeClient.instances[-1].closed


@pytest.mark.asyncio
async def test_workspace_option_reaches_configured_server(
    config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()
    config.write_text(json.dumps({"mcpServers": {
        "filesystem": {"command": "node", "args": ["${workspaceRoot}"]},
    }}), encoding="utf-8")
    monkeypatch.setattr(app, "MCPClient", FakeClient)
    assert await app.run_cli(app.parse_arguments([
        "--config", str(config), "--workspace", str(workspace),
        "--connection-demo", "--task", "list tools",
    ]), output=io.StringIO()) == 0
    server = FakeClient.instances[-1].configs[0]
    assert getattr(server, "args") == (str(workspace),)
    assert getattr(server, "cwd") == workspace
    assert FakeClient.instances[-1].closed


def test_interrupt_during_task_returns_130_and_closes_connections(
    config: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    class InterruptingAgent:
        async def run(self, task: str) -> AsyncIterator[Payload]:
            yield {"type": "text", "content": "Working"}
            raise KeyboardInterrupt()
    monkeypatch.setattr(app, "MCPClient", FakeClient)
    monkeypatch.setattr(app, "load_agent_factory", lambda spec: lambda client: InterruptingAgent())
    assert app.main([
        "--config", str(config), "--agent", "test:create", "--task", "Wait",
    ]) == 130
    assert FakeClient.instances[-1].closed
    captured = capsys.readouterr()
    assert "Interrupted. Goodbye." in captured.err
    assert "Traceback" not in captured.err


def test_malformed_config_returns_readable_error(
    config: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    config.write_text("not JSON", encoding="utf-8")
    assert app.main(["--config", str(config), "--task", "list tools"]) == 1
    error = capsys.readouterr().err
    assert "Error:" in error
    assert "Traceback" not in error


def test_load_agent_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import ModuleType
    module = ModuleType("cli_test_agent")
    agent = RecordingAgent()
    def create(client: MCPClient) -> RecordingAgent:
        return agent
    monkeypatch.setattr(module, "create", create, raising=False)
    monkeypatch.setitem(sys.modules, "cli_test_agent", module)
    assert app.load_agent_factory("cli_test_agent:create")(MCPClient(())) is agent
    with pytest.raises(ValueError, match="module:factory"):
        app.load_agent_factory("missing_separator")


@pytest.mark.asyncio
async def test_cli_connects_and_calls_two_real_stdio_servers(tmp_path: Path) -> None:
    server = Path(__file__).parent / "fixtures" / "echo_mcp_server.py"
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"mcpServers": {
        name: {"command": sys.executable, "args": [str(server)], "cwd": str(tmp_path)}
        for name in ("first", "second")
    }}), encoding="utf-8")
    clients: list[MCPClient] = []
    class EchoProvider:
        async def stream(self, messages: Sequence[Payload], tools: Sequence[Payload]) -> AsyncIterator[Payload]:
            results = [message for message in messages if message.get("role") == "tool"]
            if len(results) < 2:
                name = "first.echo" if not results else "second.echo"
                yield {"type": "tool_call", "name": name, "arguments": {"value": "hello MCP"}}
            else:
                assert all("hello MCP" in str(result["content"]) for result in results)
                yield {"type": "text", "content": "Both servers returned hello MCP."}
            yield {"type": "completed"}
    def create_agent(client: MCPClient) -> BasicAgentLoop:
        clients.append(client)
        return BasicAgentLoop(EchoProvider(), client)
    output = io.StringIO()
    result = await app.run_cli(
        app.parse_arguments(["--config", str(config), "--task", "hello MCP"]),
        output=output, agent_factory=create_agent,
    )
    assert result == 0
    assert "Connected to 2 MCP server(s)" in output.getvalue()
    assert "[Result] first.echo" in output.getvalue()
    assert "[Result] second.echo" in output.getvalue()
    assert output.getvalue().count('\nhello MCP\n') == 2
    assert output.getvalue().count('"value": "hello MCP"') == 2
    assert "Both servers returned hello MCP." in output.getvalue()
    assert clients[0].connected_servers == ()


@pytest.mark.parametrize("limit,code", [(3, 0), (1, 1)])
@pytest.mark.asyncio
async def test_scripted_cli_demo_uses_loop_and_honors_limit(
    config: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, limit: int, code: int,
) -> None:
    config.write_text(json.dumps({"mcpServers": {
        "filesystem": {"url": "https://example.com/filesystem"},
        "deepwiki": {"url": "https://mcp.deepwiki.com/mcp"},
    }}), encoding="utf-8")
    class FilesystemDemoClient(FakeClient):
        async def list_tools(self) -> list[Payload]:
            return [
                {
                    "name": "filesystem.list_allowed_directories",
                    "server": "filesystem",
                    "server_tool_name": "list_allowed_directories",
                    "input_schema": {
                        "type": "object",
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "filesystem.list_directory",
                    "server": "filesystem",
                    "server_tool_name": "list_directory",
                    "input_schema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
            ]
        async def call_tool(self, name: str, arguments: Payload) -> Payload:
            if name.endswith("list_allowed_directories"):
                content = f"Allowed directories:\n{tmp_path}"
            else:
                assert arguments == {"path": str(tmp_path)}
                content = "[FILE] README.md"
            return {"content": [{"type": "text", "text": content}], "is_error": False}
    monkeypatch.setattr(app, "MCPClient", FilesystemDemoClient)
    output = io.StringIO()
    result = await app.run_cli(app.parse_arguments([
        "--config", str(config), "--demo-loop", "--max-iterations", str(limit),
        "--task", "inspect workspace",
    ]), output=output)
    assert result == code
    assert "no live LLM" in output.getvalue()
    client = FakeClient.instances[-1]
    assert [getattr(server, "name", None) for server in client.configs] == ["filesystem"]
    assert client.closed
    if code == 0:
        assert "Workspace inspection complete" in output.getvalue()
        assert "[FILE] README.md" in output.getvalue()
    else:
        assert "Stopped after 1 model iterations" in output.getvalue()


@pytest.mark.asyncio
async def test_normal_cli_keeps_all_configured_servers(
    config: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config.write_text(json.dumps({"mcpServers": {
        "filesystem": {"url": "https://example.com/filesystem"},
        "deepwiki": {"url": "https://mcp.deepwiki.com/mcp"},
    }}), encoding="utf-8")
    monkeypatch.setattr(app, "MCPClient", FakeClient)

    result = await app.run_cli(
        app.parse_arguments(["--config", str(config), "--connection-demo", "--task", "list tools"]),
        output=io.StringIO(),
    )

    assert result == 0
    client = FakeClient.instances[-1]
    assert [getattr(server, "name", None) for server in client.configs] == [
        "filesystem", "deepwiki",
    ]
    assert client.closed


@pytest.mark.parametrize("arguments, provider", [
    ([], "groq"), (["--provider", "groq"], "groq"),
    (["--provider", "ollama"], "ollama"),
])
@pytest.mark.asyncio
async def test_provider_shortcuts_and_default_use_real_agent_factory(
    config: Path, monkeypatch: pytest.MonkeyPatch, arguments: list[str], provider: str,
) -> None:
    monkeypatch.setattr(app, "MCPClient", FakeClient)
    specs: list[str] = []
    def load(spec: str) -> app.AgentFactory:
        specs.append(spec)
        return lambda client: RecordingAgent()
    monkeypatch.setattr(app, "load_agent_factory", load)
    output = io.StringIO()
    assert await app.run_cli(app.parse_arguments([
        "--config", str(config), *arguments, "--task", "read README",
    ]), output=output) == 0
    assert specs == [f"coding_assistant.providers.{provider}:create_agent"]
    assert "Juniper | AI Coding Assistant" in output.getvalue()
    assert "Connection demo only" not in output.getvalue()
    assert "Hello read README" in output.getvalue()
    assert FakeClient.instances[-1].closed


@pytest.mark.asyncio
async def test_tool_arguments_are_visible_and_structured_results_render() -> None:
    class ToolAgent:
        async def run(self, task: str) -> AsyncIterator[Payload]:
            yield {"type": "tool_call", "name": "filesystem.read_text_file",
                   "arguments": {"path": "sample.txt"}}
            yield {"type": "tool_result", "name": "filesystem.read_text_file",
                   "content": [], "structured_content": {"project": "Juniper"}}
            yield {"type": "completed", "reason": "answered"}
    output = io.StringIO()
    assert await app.display_task(ToolAgent(), "Read sample", output) == 0
    text = output.getvalue()
    assert '"path": "sample.txt"' in text
    assert '"project": "Juniper"' in text
    assert "[Done]" in text


@pytest.mark.asyncio
async def test_failed_completion_does_not_claim_success() -> None:
    class FailedAgent:
        async def run(self, task: str) -> AsyncIterator[Payload]:
            yield {"type": "completed", "reason": "error"}
    output = io.StringIO()
    assert await app.display_task(FailedAgent(), "task", output) == 1
    assert "[Failed]" in output.getvalue()
    assert "[Done]" not in output.getvalue()


def test_terminal_panels_show_literal_tool_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coding_assistant.cli.display import TerminalView
    class TerminalOutput(io.StringIO):
        def isatty(self) -> bool:
            return True
    monkeypatch.setenv("NO_COLOR", "1")
    output = TerminalOutput()
    view = TerminalView(output)
    view.welcome(Path("sample"), "Groq", "test-model", 1)
    view.panel("Tool", "filesystem.read_text_file", '[red]sample.txt[/red]')
    view.tool("filesystem.write_file", {"path": "greet.py", "content": "def greet():\n    return 'Hello'"})
    view.tools([("filesystem.read_text_file", "Read a file")])
    text = output.getvalue()
    assert "Juniper" in text and "test-model" in text
    assert "[red]sample.txt[/red]" in text
    assert "Available MCP tools" in text
    assert "def greet():" in text and "return 'Hello'" in text
    assert "\x1b[" not in text
