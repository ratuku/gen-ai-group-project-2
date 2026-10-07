"""Deterministic demo provider: real MCP calls, no LLM or credentials required."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path

from coding_assistant.contracts import Payload


def _tool_text(message: Payload) -> str:
    result = message.get("content")
    if not isinstance(result, Mapping):
        raise ValueError("Demo expected an MCP result")
    if result.get("is_error"):
        raise ValueError(f"Filesystem request failed: {result.get('content')}")
    content = result.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(block["text"]) for block in content
                         if isinstance(block, Mapping) and block.get("type") == "text")
    raise ValueError("Filesystem response did not contain text")


class WorkspaceDemoProvider:
    """Script just one read-only workflow so the loop can be demonstrated offline."""

    async def stream(self, messages: Sequence[Payload], tools: Sequence[Payload]) -> AsyncIterator[Payload]:
        user_index = max(index for index, message in enumerate(messages) if message.get("role") == "user")
        task = str(messages[user_index].get("content", "")).strip().lower()
        if task != "inspect workspace":
            yield {"type": "error", "content": "Scripted demo supports 'inspect workspace'. Use --agent for a live model-backed agent."}
            return
        names = {str(tool.get("server_tool_name")): str(tool["name"])
                 for tool in tools if tool.get("server") == "filesystem"}
        if not {"list_allowed_directories", "list_directory"}.issubset(names):
            yield {"type": "error", "content": "Demo requires the configured filesystem server's list_allowed_directories and list_directory tools."}
            return
        results = [message for message in messages[user_index + 1:] if message.get("role") == "tool"]
        if not results:
            yield {"type": "text", "content": "I will find the allowed workspace, then list its contents.\n"}
            yield {"type": "tool_call", "name": names["list_allowed_directories"], "arguments": {}}
        elif len(results) == 1:
            lines = _tool_text(results[0]).splitlines()
            paths = [line.strip() for line in lines if Path(line.strip()).is_absolute()]
            if not paths:
                yield {"type": "error", "content": "No allowed workspace path was returned by the filesystem server."}
                return
            yield {"type": "tool_call", "name": names["list_directory"], "arguments": {"path": paths[0]}}
        else:
            listing = _tool_text(results[-1])
            yield {"type": "text", "content": "Workspace inspection complete. The filesystem server returned:\n" + listing}
        yield {"type": "completed"}
