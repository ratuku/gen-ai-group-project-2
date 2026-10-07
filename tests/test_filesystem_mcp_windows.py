"""Real Windows launcher regressions; install the server with npm ci first."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coding_assistant.config import load_mcp_config
from coding_assistant.mcp import MCPClient


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher regression")
@pytest.mark.parametrize("name", ["R&D", "repo%USERNAME%", "repo^name", "repo with spaces"])
async def test_workspace_path_reaches_real_server_unchanged(
    tmp_path: Path, name: str
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / name
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    config = load_mcp_config(
        project_root / "config" / "mcp.json", workspace_root=workspace
    )
    target = workspace / "hello.txt"
    async with MCPClient(config.servers) as client:
        result = await client.call_tool(
            "filesystem.write_file", {"path": str(target), "content": "hello"}
        )
        assert not result["is_error"], result
        assert target.read_text(encoding="utf-8") == "hello"
        result = await client.call_tool("filesystem.read_text_file", {"path": str(target)})
        assert not result["is_error"], result
        assert result["content"] == [{"type": "text", "text": "hello"}]
        result = await client.call_tool("filesystem.list_directory", {"path": str(workspace)})
        assert not result["is_error"], result
        assert "hello.txt" in str(result["content"])
        for tool, arguments in (
            ("read_text_file", {"path": str(outside)}),
            ("write_file", {"path": str(outside), "content": "changed"}),
            ("list_directory", {"path": str(tmp_path)}),
        ):
            result = await client.call_tool(f"filesystem.{tool}", arguments)
            assert result["is_error"], result
        assert outside.read_text(encoding="utf-8") == "private"
