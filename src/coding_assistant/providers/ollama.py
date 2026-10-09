"""Ollama adapter for the provider-neutral agent contract."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Protocol, cast

from ollama import AsyncClient, ResponseError

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.contracts import MCPClient, Payload


class OllamaProviderError(ValueError):
    """An Ollama request or response could not satisfy the provider contract."""


class _OllamaClient(Protocol):
    def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, object]],
        tools: Sequence[Mapping[str, object]],
        stream: bool,
    ) -> Awaitable[AsyncIterator[object]]:
        """Return streamed native chat response objects."""

    async def close(self) -> None:
        """Release the underlying HTTP client."""


ClientFactory = Callable[[str | None], _OllamaClient]


class OllamaProvider:
    """Translate between Ollama chat data and provider-neutral events.

    A new asynchronous SDK client is created for each model turn and closed after
    the response stream finishes. The agent loop continues to own conversation
    state and MCP tool execution.
    """

    def __init__(
        self,
        model: str,
        *,
        host: str | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Ollama model must be a non-empty string")
        if host is not None and (not isinstance(host, str) or not host.strip()):
            raise ValueError("Ollama host must be a non-empty string when provided")
        self.model = model.strip()
        self.host = host.strip() if host is not None else None
        self._client_factory = client_factory or _create_client

    async def stream(
        self,
        messages: Sequence[Payload],
        tools: Sequence[Payload],
    ) -> AsyncIterator[Payload]:
        client: _OllamaClient | None = None
        try:
            native_messages = _convert_messages(messages)
            native_tools = _convert_tools(tools)
            client = self._client_factory(self.host)
            response = await client.chat(
                model=self.model,
                messages=native_messages,
                tools=native_tools,
                stream=True,
            )
            async for chunk in response:
                message = _response_message(chunk)
                content = message.get("content")
                if content is not None:
                    if not isinstance(content, str):
                        raise OllamaProviderError(
                            "Ollama response message content must be a string"
                        )
                    if content:
                        yield {"type": "text", "content": content}

                calls = message.get("tool_calls")
                if calls is not None:
                    if not _is_sequence(calls):
                        raise OllamaProviderError(
                            "Ollama response tool_calls must be an array"
                        )
                    for call in cast(Sequence[object], calls):
                        yield _convert_response_call(call)
            yield {"type": "completed"}
        except asyncio.CancelledError:
            raise
        except ConnectionError as error:
            endpoint = self.host or "the default local endpoint"
            yield {
                "type": "error",
                "content": (
                    f"Could not connect to Ollama at {endpoint}. Start Ollama and "
                    f"confirm OLLAMA_HOST is correct. Details: {_error_detail(error)}"
                ),
            }
        except ResponseError as error:
            if error.status_code == 404:
                content = (
                    f"Ollama model {self.model!r} is unavailable. Download it with "
                    f"`ollama pull {self.model}` and try again. Details: "
                    f"{_error_detail(error)}"
                )
            else:
                content = f"Ollama request failed: {_error_detail(error)}"
            yield {"type": "error", "content": content}
        except OllamaProviderError as error:
            yield {"type": "error", "content": f"Invalid Ollama response: {error}"}
        except Exception as error:
            yield {
                "type": "error",
                "content": f"Ollama request failed: {_error_detail(error)}",
            }
        finally:
            if client is not None:
                try:
                    await client.close()
                except Exception:
                    # Closing must not replace the model response or its original
                    # failure. Each turn owns a fresh client, so it is not reused.
                    pass


def create_agent(client: MCPClient) -> BasicAgentLoop:
    """Build the standard agent from environment-based Ollama configuration."""

    model = os.environ.get("OLLAMA_MODEL", "").strip()
    if not model:
        raise ValueError(
            "OLLAMA_MODEL is required; for example, set it to a downloaded "
            "tool-capable model such as 'qwen3'"
        )
    host_value = os.environ.get("OLLAMA_HOST")
    host = host_value.strip() if host_value is not None else None
    if host_value is not None and not host:
        raise ValueError("OLLAMA_HOST must not be blank when provided")
    return BasicAgentLoop(OllamaProvider(model, host=host), client)


def _create_client(host: str | None) -> _OllamaClient:
    # The SDK overload returns ChatResponse objects, which this adapter treats as
    # native objects and normalizes through model_dump().
    return cast(_OllamaClient, AsyncClient(host=host))


def _convert_messages(
    messages: Sequence[Payload],
) -> tuple[Mapping[str, object], ...]:
    converted: list[Mapping[str, object]] = []
    for index, message in enumerate(messages):
        role = message.get("role")
        if role not in {"user", "assistant", "tool"}:
            raise OllamaProviderError(
                f"Conversation message at index {index} has unsupported role {role!r}"
            )

        if role in {"user", "assistant"}:
            content = message.get("content")
            if not isinstance(content, str):
                raise OllamaProviderError(
                    f"{role.title()} message at index {index} requires string content"
                )
            native: dict[str, object] = {"role": role, "content": content}
            calls = message.get("tool_calls")
            if calls is not None:
                if role != "assistant" or not _is_sequence(calls):
                    raise OllamaProviderError(
                        f"Message at index {index} has invalid tool_calls"
                    )
                native["tool_calls"] = [
                    _convert_history_call(call, index)
                    for call in cast(Sequence[object], calls)
                ]
            converted.append(native)
            continue

        name = message.get("name")
        if not isinstance(name, str) or not name.strip():
            raise OllamaProviderError(
                f"Tool message at index {index} requires a non-empty name"
            )
        converted.append(
            {
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(
                    message.get("content"),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            }
        )
    return tuple(converted)


def _convert_history_call(call: object, message_index: int) -> Mapping[str, object]:
    mapping = _as_mapping(
        call, f"Assistant tool call in message at index {message_index}"
    )
    name = mapping.get("name")
    arguments = mapping.get("arguments")
    if not isinstance(name, str) or not name.strip():
        raise OllamaProviderError(
            f"Assistant tool call in message at index {message_index} "
            "requires a non-empty name"
        )
    if not isinstance(arguments, Mapping) or not all(
        isinstance(key, str) for key in arguments
    ):
        raise OllamaProviderError(
            f"Assistant tool call {name!r} requires object arguments"
        )
    return {
        "function": {"name": name, "arguments": dict(arguments)},
    }


def _convert_tools(tools: Sequence[Payload]) -> tuple[Mapping[str, object], ...]:
    converted: list[Mapping[str, object]] = []
    for index, tool in enumerate(tools):
        name = tool.get("name")
        description = tool.get("description", "")
        schema = tool.get("input_schema")
        if not isinstance(name, str) or not name.strip():
            raise OllamaProviderError(
                f"Tool definition at index {index} requires a non-empty name"
            )
        if not isinstance(description, str):
            raise OllamaProviderError(
                f"Tool definition {name!r} requires a string description"
            )
        if not isinstance(schema, Mapping):
            raise OllamaProviderError(
                f"Tool definition {name!r} requires an object input_schema"
            )
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": dict(schema),
                },
            }
        )
    return tuple(converted)


def _response_message(chunk: object) -> Mapping[str, object]:
    payload = _as_mapping(chunk, "Ollama response chunk")
    return _as_mapping(payload.get("message"), "Ollama response message")


def _convert_response_call(call: object) -> Payload:
    mapping = _as_mapping(call, "Ollama response tool call")
    function = _as_mapping(
        mapping.get("function"), "Ollama response tool call function"
    )
    name = function.get("name")
    arguments = function.get("arguments")
    if not isinstance(name, str) or not name.strip():
        raise OllamaProviderError(
            "Ollama response tool call requires a non-empty function name"
        )
    if not isinstance(arguments, Mapping) or not all(
        isinstance(key, str) for key in arguments
    ):
        raise OllamaProviderError(
            f"Ollama response tool call {name!r} requires object arguments"
        )
    event: dict[str, object] = {
        "type": "tool_call",
        "name": name,
        "arguments": dict(arguments),
    }
    call_id = mapping.get("id")
    if call_id is not None:
        if not isinstance(call_id, str) or not call_id:
            raise OllamaProviderError(
                f"Ollama response tool call {name!r} has an invalid id"
            )
        event["id"] = call_id
    return event


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, Mapping):
            return cast(Mapping[str, object], dumped)
    raise OllamaProviderError(f"{label} must be an object")


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _error_detail(error: BaseException) -> str:
    return str(error) or type(error).__name__
