"""Groq Cloud adapter for the provider-neutral agent contract."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, cast

from groq import APIConnectionError, APIStatusError, APITimeoutError, AsyncGroq
from groq.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.contracts import MCPClient, Payload


DEFAULT_MODEL = "openai/gpt-oss-20b"


class GroqProviderError(ValueError):
    """A Groq request or response could not satisfy the provider contract."""


class _GroqClient(Protocol):
    def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, object]],
        tools: Sequence[Mapping[str, object]],
        stream: bool,
    ) -> Awaitable[AsyncIterator[object]]:
        """Return streamed native chat-completion chunks."""

    async def close(self) -> None:
        """Release the underlying HTTP client."""


ClientFactory = Callable[[str], _GroqClient]


class _SDKGroqClient:
    """Small typed boundary around the official nested SDK resources."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncGroq(api_key=api_key)

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, object]],
        tools: Sequence[Mapping[str, object]],
        stream: bool,
    ) -> AsyncIterator[object]:
        if not stream:
            raise ValueError("Groq provider requires streaming responses")
        native_messages = cast(Iterable[ChatCompletionMessageParam], messages)
        if tools:
            response = await self._client.chat.completions.create(
                model=model,
                messages=native_messages,
                tools=cast(Iterable[ChatCompletionToolParam], tools),
                stream=True,
            )
        else:
            response = await self._client.chat.completions.create(
                model=model,
                messages=native_messages,
                stream=True,
            )
        return cast(AsyncIterator[object], response)

    async def close(self) -> None:
        await self._client.close()


class GroqProvider:
    """Translate Groq chat completions into provider-neutral streaming events."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str,
        client_factory: ClientFactory | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Groq model must be a non-empty string")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Groq API key must be a non-empty string")
        self.model = model.strip()
        self._api_key = api_key.strip()
        self._client_factory = client_factory or _SDKGroqClient

    async def stream(
        self,
        messages: Sequence[Payload],
        tools: Sequence[Payload],
    ) -> AsyncIterator[Payload]:
        client: _GroqClient | None = None
        try:
            native_messages = _convert_messages(messages)
            native_tools = _convert_tools(tools)
            client = self._client_factory(self._api_key)
            response = await client.chat(
                model=self.model,
                messages=native_messages,
                tools=native_tools,
                stream=True,
            )
            pending: dict[int, _PendingToolCall] = {}
            async for chunk in response:
                for event in _consume_chunk(chunk, pending):
                    yield event
            for index in sorted(pending):
                yield pending[index].finish()
            yield {"type": "completed"}
        except asyncio.CancelledError:
            raise
        except APITimeoutError as error:
            yield {
                "type": "error",
                "content": f"Groq request timed out. Try again. Details: {_error_detail(error)}",
            }
        except APIConnectionError as error:
            yield {
                "type": "error",
                "content": (
                    "Could not connect to Groq Cloud. Check the internet connection "
                    f"and try again. Details: {_error_detail(error)}"
                ),
            }
        except APIStatusError as error:
            yield {"type": "error", "content": _status_error_message(error, self.model)}
        except GroqProviderError as error:
            yield {"type": "error", "content": f"Invalid Groq response: {error}"}
        except Exception as error:
            yield {
                "type": "error",
                "content": f"Groq request failed: {_error_detail(error)}",
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
    """Build the standard agent from environment-based Groq configuration."""

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is required. Create a Groq Cloud API key and set it "
            "in the environment; never commit the key."
        )
    model_value = os.environ.get("GROQ_MODEL")
    model = model_value.strip() if model_value is not None else DEFAULT_MODEL
    if not model:
        raise ValueError("GROQ_MODEL must not be blank when provided")
    return BasicAgentLoop(GroqProvider(model, api_key=api_key), client)


def _convert_messages(
    messages: Sequence[Payload],
) -> tuple[Mapping[str, object], ...]:
    converted: list[Mapping[str, object]] = []
    for index, message in enumerate(messages):
        role = message.get("role")
        if role not in {"user", "assistant", "tool"}:
            raise GroqProviderError(
                f"Conversation message at index {index} has unsupported role {role!r}"
            )

        if role in {"user", "assistant"}:
            content = message.get("content")
            if not isinstance(content, str):
                raise GroqProviderError(
                    f"{role.title()} message at index {index} requires string content"
                )
            native: dict[str, object] = {"role": role, "content": content}
            calls = message.get("tool_calls")
            if calls is not None:
                if role != "assistant" or not _is_sequence(calls):
                    raise GroqProviderError(
                        f"Message at index {index} has invalid tool_calls"
                    )
                native["tool_calls"] = [
                    _convert_history_call(call, index)
                    for call in cast(Sequence[object], calls)
                ]
            converted.append(native)
            continue

        call_id = message.get("tool_call_id")
        if not isinstance(call_id, str) or not call_id:
            raise GroqProviderError(
                f"Tool message at index {index} requires a non-empty tool_call_id"
            )
        converted.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
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
    call_id = mapping.get("id")
    name = mapping.get("name")
    arguments = mapping.get("arguments")
    if not isinstance(call_id, str) or not call_id:
        raise GroqProviderError(
            f"Assistant tool call in message at index {message_index} "
            "requires a non-empty id"
        )
    if not isinstance(name, str) or not name.strip():
        raise GroqProviderError(
            f"Assistant tool call in message at index {message_index} "
            "requires a non-empty name"
        )
    if not isinstance(arguments, Mapping) or not all(
        isinstance(key, str) for key in arguments
    ):
        raise GroqProviderError(
            f"Assistant tool call {name!r} requires object arguments"
        )
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(
                dict(arguments), ensure_ascii=False, sort_keys=True, default=str
            ),
        },
    }


def _convert_tools(tools: Sequence[Payload]) -> tuple[Mapping[str, object], ...]:
    converted: list[Mapping[str, object]] = []
    for index, tool in enumerate(tools):
        name = tool.get("name")
        description = tool.get("description", "")
        schema = tool.get("input_schema")
        if not isinstance(name, str) or not name.strip():
            raise GroqProviderError(
                f"Tool definition at index {index} requires a non-empty name"
            )
        if not isinstance(description, str):
            raise GroqProviderError(
                f"Tool definition {name!r} requires a string description"
            )
        if not isinstance(schema, Mapping):
            raise GroqProviderError(
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


def _consume_chunk(
    chunk: object, pending: dict[int, _PendingToolCall]
) -> tuple[Payload, ...]:
    payload = _as_mapping(chunk, "Groq response chunk")
    choices = payload.get("choices")
    if not _is_sequence(choices):
        raise GroqProviderError("Groq response chunk choices must be an array")
    events: list[Payload] = []
    for choice_value in cast(Sequence[object], choices):
        choice = _as_mapping(choice_value, "Groq response choice")
        choice_index = choice.get("index")
        if choice_index != 0:
            raise GroqProviderError(
                f"Groq response returned unsupported choice index {choice_index!r}"
            )
        delta = _as_mapping(choice.get("delta"), "Groq response choice delta")
        content = delta.get("content")
        if content is not None:
            if not isinstance(content, str):
                raise GroqProviderError("Groq response content must be a string")
            if content:
                events.append({"type": "text", "content": content})
        fragments = delta.get("tool_calls")
        if fragments is None:
            continue
        if not _is_sequence(fragments):
            raise GroqProviderError("Groq response tool_calls must be an array")
        for fragment in cast(Sequence[object], fragments):
            mapping = _as_mapping(fragment, "Groq tool-call fragment")
            index = mapping.get("index")
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise GroqProviderError("Groq tool-call fragment requires a valid index")
            pending.setdefault(index, _PendingToolCall()).add(mapping)
    return tuple(events)


@dataclass
class _PendingToolCall:
    id_parts: list[str] = field(default_factory=list)
    name_parts: list[str] = field(default_factory=list)
    argument_parts: list[str] = field(default_factory=list)

    def add(self, fragment: Mapping[str, object]) -> None:
        call_type = fragment.get("type")
        if call_type is not None and call_type != "function":
            raise GroqProviderError(
                f"Groq tool-call fragment has unsupported type {call_type!r}"
            )
        call_id = fragment.get("id")
        if call_id is not None:
            if not isinstance(call_id, str):
                raise GroqProviderError("Groq tool-call id fragment must be a string")
            self.id_parts.append(call_id)
        function_value = fragment.get("function")
        if function_value is None:
            return
        function = _as_mapping(function_value, "Groq tool-call function fragment")
        name = function.get("name")
        if name is not None:
            if not isinstance(name, str):
                raise GroqProviderError("Groq function name fragment must be a string")
            self.name_parts.append(name)
        arguments = function.get("arguments")
        if arguments is not None:
            if not isinstance(arguments, str):
                raise GroqProviderError("Groq function arguments fragment must be a string")
            self.argument_parts.append(arguments)

    def finish(self) -> Payload:
        call_id = "".join(self.id_parts)
        name = "".join(self.name_parts)
        arguments_text = "".join(self.argument_parts)
        if not call_id:
            raise GroqProviderError("Groq tool call requires a non-empty id")
        if not name.strip():
            raise GroqProviderError("Groq tool call requires a non-empty function name")
        try:
            arguments = json.loads(arguments_text)
        except json.JSONDecodeError as error:
            raise GroqProviderError(
                f"Groq tool call {name!r} returned invalid JSON arguments: {error.msg}"
            ) from error
        if not isinstance(arguments, Mapping) or not all(
            isinstance(key, str) for key in arguments
        ):
            raise GroqProviderError(
                f"Groq tool call {name!r} requires object arguments"
            )
        return {
            "type": "tool_call",
            "id": call_id,
            "name": name,
            "arguments": dict(arguments),
        }


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, Mapping):
            return cast(Mapping[str, object], dumped)
    raise GroqProviderError(f"{label} must be an object")


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _status_error_message(error: APIStatusError, model: str) -> str:
    detail = _error_detail(error)
    if error.status_code in {401, 403}:
        return (
            "Groq authentication failed. Check GROQ_API_KEY and confirm the key is "
            f"active. Details: {detail}"
        )
    if error.status_code == 404:
        return (
            f"Groq model {model!r} is unavailable. Check GROQ_MODEL against the "
            f"models enabled for the account. Details: {detail}"
        )
    if error.status_code == 429:
        return (
            "Groq Free plan rate limit reached. Wait for the limit to reset and "
            f"try again. Details: {detail}"
        )
    return f"Groq request failed with status {error.status_code}: {detail}"


def _error_detail(error: BaseException) -> str:
    return str(error) or type(error).__name__
