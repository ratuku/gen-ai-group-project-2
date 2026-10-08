"""Retrieve useful public repository information through the DeepWiki MCP server."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from coding_assistant.config import load_mcp_config
from coding_assistant.contracts import Payload
from coding_assistant.mcp import MCPClient


SERVER_NAME = "deepwiki"
REQUIRED_TOOLS = {
    "deepwiki.ask_wiki_question",
    "deepwiki.read_wiki_contents",
    "deepwiki.read_wiki_structure",
}
SMOKE_REPOSITORY = "modelcontextprotocol/python-sdk"
SMOKE_QUESTION = (
    "What is the primary purpose of this repository, and name one capability "
    "provided by its MCP client API?"
)


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
    return "\n".join(parts).strip()


async def _run() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_mcp_config(project_root / "config" / "mcp.json")
    try:
        deepwiki = next(server for server in config.servers if server.name == SERVER_NAME)
    except StopIteration as exc:
        raise RuntimeError("DeepWiki MCP server is not configured") from exc

    async with MCPClient((deepwiki,)) as client:
        tools = await client.list_tools()
        tool_names = {str(tool["name"]) for tool in tools}
        print("Discovered DeepWiki tools:")
        for name in sorted(tool_names):
            print(f"  - {name}")

        missing = REQUIRED_TOOLS - tool_names
        if missing:
            raise RuntimeError(f"Missing required tools: {', '.join(sorted(missing))}")
        print("PASS: required DeepWiki tools discovered")

        print(f"Requesting external information about {SMOKE_REPOSITORY}...")
        result = await client.call_tool(
            "deepwiki.ask_wiki_question",
            {"repoName": SMOKE_REPOSITORY, "question": SMOKE_QUESTION},
        )
        if result.get("is_error"):
            detail = _text_content(result) or "unknown MCP tool error"
            raise RuntimeError(f"External-information request failed: {detail}")

        answer = _text_content(result)
        if not answer:
            raise RuntimeError("External-information request returned no text")
        print("PASS: useful external information retrieved")
        print("DeepWiki response:")
        print(answer)


def main() -> int:
    try:
        asyncio.run(_run())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("DeepWiki MCP smoke test completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
