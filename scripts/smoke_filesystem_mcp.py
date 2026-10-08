"""Exercise the configured filesystem MCP server against a disposable directory."""

from __future__ import annotations

import asyncio
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import uuid4

from coding_assistant.config import load_mcp_config
from coding_assistant.contracts import Payload
from coding_assistant.mcp import MCPClient


REQUIRED_TOOLS = {
    "filesystem.create_directory",
    "filesystem.list_directory",
    "filesystem.read_text_file",
    "filesystem.write_file",
}


def _text_content(result: Payload) -> str:
    content = result.get("content")
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, Mapping):
            value = block.get("text")
            if isinstance(value, str):
                parts.append(value)
    return "\n".join(parts)


def _require_success(step: str, result: Payload) -> None:
    if result.get("is_error"):
        detail = _text_content(result) or "unknown MCP tool error"
        raise RuntimeError(f"{step} failed: {detail}")
    print(f"PASS: {step}")


async def _run() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_mcp_config(project_root / "config" / "mcp.json")
    try:
        filesystem = next(
            server for server in config.servers if server.name == "filesystem"
        )
    except StopIteration as exc:
        raise RuntimeError("Filesystem MCP server is not configured") from exc
    smoke_dir = project_root / f".filesystem-mcp-smoke-{uuid4().hex}"
    smoke_file = smoke_dir / "hello.txt"

    try:
        async with MCPClient((filesystem,)) as client:
            tools = await client.list_tools()
            tool_names = {str(tool["name"]) for tool in tools}
            print("Discovered filesystem tools:")
            for name in sorted(
                name for name in tool_names if name.startswith("filesystem.")
            ):
                print(f"  - {name}")

            missing = REQUIRED_TOOLS - tool_names
            if missing:
                raise RuntimeError(f"Missing required tools: {', '.join(sorted(missing))}")
            print("PASS: required tools discovered")

            result = await client.call_tool(
                "filesystem.create_directory", {"path": str(smoke_dir)}
            )
            _require_success("create directory inside workspace", result)

            expected = "filesystem MCP smoke test\n"
            result = await client.call_tool(
                "filesystem.write_file",
                {"path": str(smoke_file), "content": expected},
            )
            _require_success("write file inside workspace", result)

            result = await client.call_tool(
                "filesystem.list_directory", {"path": str(smoke_dir)}
            )
            _require_success("list directory inside workspace", result)
            if "hello.txt" not in _text_content(result):
                raise RuntimeError("Directory listing did not contain hello.txt")
            print("PASS: directory listing contains hello.txt")

            result = await client.call_tool(
                "filesystem.read_text_file", {"path": str(smoke_file)}
            )
            _require_success("read file inside workspace", result)
            if _text_content(result) != expected:
                raise RuntimeError("Read content did not match written content")
            print("PASS: read content matches written content")

            result = await client.call_tool(
                "filesystem.list_directory", {"path": str(project_root.parent)}
            )
            if not result.get("is_error"):
                raise RuntimeError("Filesystem server allowed access outside workspace")
            print("PASS: access outside workspace was rejected")
    finally:
        shutil.rmtree(smoke_dir, ignore_errors=True)
        if smoke_dir.exists():
            raise RuntimeError(f"Could not clean up smoke directory: {smoke_dir}")
        print("PASS: temporary smoke files cleaned up")


def main() -> int:
    if sys.platform != "win32":
        print("FAIL: this demo configuration currently supports Windows only")
        return 1
    try:
        asyncio.run(_run())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("Filesystem MCP smoke test completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
