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

    def __init__(self, configs: object) -> None:
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
    inputs = iter([" ", "/help", "/servers", "/tools", "/unknown", "fail", "read README", "/exit"])
    async def read_prompt(prompt: str) -> str:
        return next(inputs)
    agent = RecordingAgent()
    output = io.StringIO()
    result = await app.run_cli(
        app.parse_arguments(["--config", str(config)]), output=output,
        read_prompt=read_prompt, agent_factory=lambda client: agent,
    )
    assert result == 0
    assert agent.tasks == ["fail", "read README"]
    text = output.getvalue()
    assert "Connected to 2 MCP server(s)" in text
    assert "external.search" in text
    assert "Unknown command" in text
    assert "[Error] Task failed" in text
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
        app.parse_arguments(["--config", str(config)]), output=io.StringIO(), read_prompt=read_prompt,
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
        app.parse_arguments(["--config", str(config), "--task", "Change a file"]),
        output=output,
    )
    assert result == 1
    assert "Connection demo only" in output.getvalue()
    assert "Coding tasks require an agent loop" in output.getvalue()
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
    assert output.getvalue().count("hello MCP") == 3
    assert "Both servers returned hello MCP." in output.getvalue()
    assert clients[0].connected_servers == ()


@pytest.mark.parametrize("limit,code", [(3, 0), (1, 1)])
@pytest.mark.asyncio
async def test_scripted_cli_demo_uses_loop_and_honors_limit(
    config: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, limit: int, code: int,
) -> None:
    class FilesystemDemoClient(FakeClient):
        async def list_tools(self) -> list[Payload]:
            return [{"name": f"filesystem.{name}", "server": "filesystem", "server_tool_name": name}
                    for name in ("list_allowed_directories", "list_directory")]
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
    assert FakeClient.instances[-1].closed
    if code == 0:
        assert "Workspace inspection complete" in output.getvalue()
        assert "[FILE] README.md" in output.getvalue()
    else:
        assert "Stopped after 1 model iterations" in output.getvalue()
