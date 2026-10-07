"""Basic stateful model -> tool results -> model cycle."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from copy import deepcopy
from uuid import uuid4

from coding_assistant.contracts import MCPClient, ModelProvider, Payload


class BasicAgentLoop:
    """Own conversation state; use the existing MCP client for tool invocation.

    Provider adapters translate their native responses into complete ``text`` and
    ``tool_call`` events. Tool names/schema validation and execution policy belong
    to the later dispatcher ticket; this loop only checks the event envelope.
    """

    def __init__(
        self, provider: ModelProvider, mcp_client: MCPClient, *, max_iterations: int = 8,
    ) -> None:
        if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
            raise ValueError("max_iterations must be a positive integer")
        self.provider = provider
        self.mcp_client = mcp_client
        self.max_iterations = max_iterations
        self._messages: list[Payload] = []
        self._running = False

    @property
    def messages(self) -> tuple[Payload, ...]:
        """A snapshot, so callers cannot mutate the running conversation."""
        return tuple(deepcopy(self._messages))

    async def run(self, task: str) -> AsyncIterator[Payload]:
        if not task.strip():
            raise ValueError("Task must not be empty")
        if self._running:
            raise RuntimeError("This agent is already processing a task")
        self._running = True
        self._messages.append({"role": "user", "content": task.strip()})
        pending: list[Payload] = []
        try:
            tools = await self.mcp_client.list_tools()
            for iteration in range(1, self.max_iterations + 1):
                yield {"type": "status", "content": f"Model step {iteration}/{self.max_iterations}"}
                text_parts: list[str] = []
                calls: list[Payload] = []
                ids: set[str] = set()
                async for event in self.provider.stream(self.messages, deepcopy(tools)):
                    kind = event.get("type")
                    if kind == "text":
                        text = event.get("content")
                        if not isinstance(text, str):
                            raise ValueError("Model text event must contain string content")
                        text_parts.append(text)
                        yield {"type": "text", "content": text}
                    elif kind == "tool_call":
                        call = _parse_call(event)
                        call_id = str(call["id"])
                        if call_id in ids:
                            raise ValueError("Model returned duplicate tool call IDs")
                        ids.add(call_id)
                        calls.append(call)
                    elif kind == "error":
                        raise RuntimeError(str(event.get("content", event.get("message", "Model failed"))))
                    elif kind not in {"completed", "status"}:
                        raise ValueError(f"Unsupported model event: {kind!r}")

                text = "".join(text_parts)
                if not calls:
                    if not text.strip():
                        raise ValueError("Model returned neither a final response nor tool calls")
                    self._messages.append({"role": "assistant", "content": text})
                    yield {"type": "completed", "reason": "answered", "iterations": iteration}
                    return

                self._messages.append({"role": "assistant", "content": text, "tool_calls": calls})
                pending = list(calls)
                for call in calls:
                    name = str(call["name"])
                    arguments = call["arguments"]
                    assert isinstance(arguments, Mapping)
                    yield {"type": "tool_call", **call}
                    try:
                        result = await self.mcp_client.call_tool(name, arguments)
                    except Exception as error:
                        result = {"type": "tool_result", "name": name, "is_error": True, "content": str(error)}
                    # Keep the complete result (including structured content and error
                    # flags) available to the next model request.
                    self._messages.append({
                        "role": "tool", "name": name, "tool_call_id": call["id"],
                        "content": deepcopy(dict(result)),
                    })
                    pending.pop(0)
                    yield {**result, "type": "tool_result", "name": name, "tool_call_id": call["id"]}

            message = f"Stopped after {self.max_iterations} model iterations without a final response."
            self._messages.append({"role": "assistant", "content": message})
            yield {"type": "error", "content": message}
            yield {"type": "completed", "reason": "iteration_limit", "iterations": self.max_iterations}
        except asyncio.CancelledError:
            raise
        except Exception as error:
            message = f"Agent stopped: {error}"
            self._messages.append({"role": "assistant", "content": message})
            yield {"type": "error", "content": message}
            yield {"type": "completed", "reason": "error"}
        finally:
            # A cancelled task must not leave unmatched tool calls in the history
            # used by a subsequent request. No tool is retried automatically.
            for call in pending:
                self._messages.append({
                    "role": "tool", "name": call["name"], "tool_call_id": call["id"],
                    "content": {"is_error": True, "content": "Task interrupted; tool outcome unknown."},
                })
            self._running = False


def _parse_call(event: Payload) -> Payload:
    name, arguments = event.get("name"), event.get("arguments")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Model tool call requires a non-empty name")
    if not isinstance(arguments, Mapping) or not all(isinstance(key, str) for key in arguments):
        raise ValueError("Model tool arguments must be an object with string keys")
    call_id = event.get("id", f"call_{uuid4().hex}")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError("Model tool call ID must be a non-empty string")
    return {"id": call_id, "name": name, "arguments": dict(arguments)}
