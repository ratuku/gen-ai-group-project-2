"""OpenAI Chat Completions adapter for Juniper's existing MCP agent loop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
import math
import os
import re
from typing import cast

from openai import APIConnectionError, APIStatusError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.contracts import MCPClient, Payload
# Both APIs use the same native chat history and streamed function-call format.
from coding_assistant.providers.groq import (
    GroqProviderError, _GroqClient, _PendingToolCall, _consume_chunk,
    _convert_messages, _convert_tools, _summary_view,
)
from coding_assistant.providers.groq_context import ToolNames, request_view, task_progress, tool_view


DEFAULT_MODEL = "gpt-5.4-mini"


class _SDKOpenAIClient:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, max_retries=0, timeout=60)

    async def chat(
        self, *, model: str, messages: Sequence[Mapping[str, object]],
        tools: Sequence[Mapping[str, object]], stream: bool,
    ) -> AsyncIterator[object]:
        if not stream:
            raise ValueError("OpenAI provider requires streaming responses")
        options: dict[str, object] = {}
        if model.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4")):
            options["reasoning_effort"] = "low"
        if tools and model.startswith(("gpt-5.4-mini", "gpt-5.4-nano")):
            # These models require reasoning disabled for Chat Completions tools.
            options["reasoning_effort"] = "none"
        if tools:
            options["tools"] = cast(Iterable[ChatCompletionToolParam], tools)
            options["parallel_tool_calls"] = False
        response = await self._client.chat.completions.create(
            model=model,
            messages=cast(Iterable[ChatCompletionMessageParam], messages),
            stream=True, max_completion_tokens=4096, store=False,
            **options,
        )
        return cast(AsyncIterator[object], response)

    async def close(self) -> None:
        await self._client.close()


class OpenAIProvider:
    """Stream complete, validated tool calls; never execute partial generations."""

    def __init__(
        self, model: str, *, api_key: str,
        client_factory: Callable[[str], _GroqClient] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("OpenAI model must be a non-empty string")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("OpenAI API key must be a non-empty string")
        self.model = model.strip()
        self._api_key = api_key.strip()
        self._client_factory = client_factory or _SDKOpenAIClient
        self._sleep = sleep

    async def stream(self, messages: Sequence[Payload], tools: Sequence[Payload]) -> AsyncIterator[Payload]:
        client: _GroqClient | None = None
        emitted = False
        try:
            native_messages = _convert_messages(messages)
            names = ToolNames(tools)
            native_tools = tool_view(_convert_tools(tools), names)
            summary_only = task_progress(native_messages, names).summary_only
            if summary_only:
                native_tools = ()
                yield {"type": "status", "content": "Checks passed; ending repeated reads with a final summary."}
            view = request_view(native_messages, native_tools, names, budget=30000)
            if summary_only:
                view = _summary_view(view)
            client = self._client_factory(self._api_key)
            for attempt in range(3):
                try:
                    response = await client.chat(model=self.model, messages=view, tools=native_tools, stream=True)
                    pending: dict[int, _PendingToolCall] = {}
                    async for chunk in response:
                        for event in _consume_chunk(chunk, pending):
                            emitted = True
                            yield event
                    calls = [names.resolve(pending[index].finish()) for index in sorted(pending)]
                    if summary_only and calls:
                        raise ValueError("The model requested tools during final summarization")
                    if any(call["name"] not in names.original for call in calls):
                        raise ValueError("The model requested an unknown tool")
                    if not calls and not emitted:
                        raise ValueError("The model returned no text or tool calls")
                    for call in calls:
                        yield call
                    yield {"type": "completed"}
                    return
                except (APIStatusError, APIConnectionError) as error:
                    delay = _retry_delay(error, attempt)
                    if emitted or attempt == 2 or delay is None:
                        raise
                    yield {"type": "status", "content": f"OpenAI temporarily unavailable; waiting {delay:g}s (retry {attempt + 1}/2)",
                           "wait_seconds": delay}
                    await self._sleep(delay)
        except asyncio.CancelledError:
            raise
        except APIStatusError as error:
            code, message = _status_error(error, api_key=self._api_key)
            yield {"type": "error", "error_code": code, "content": message}
        except APIConnectionError:
            yield {"type": "error", "error_code": "provider_unavailable",
                   "content": "Could not connect to OpenAI. Check your internet connection and try again."}
        except (GroqProviderError, ValueError) as error:
            yield {"type": "error", "content": "Invalid OpenAI response: " + str(error).replace("Groq", "OpenAI")}
        except Exception:
            # Do not expose SDK request headers or credentials in unexpected errors.
            yield {"type": "error", "content": "OpenAI request failed unexpectedly. Check the model and connection."}
        finally:
            if client is not None:
                try:
                    await client.close()
                except Exception:
                    pass


def _quota_error(error: APIStatusError) -> bool:
    body = error.body
    if isinstance(body, Mapping):
        detail = body.get("error", body)
        if isinstance(detail, Mapping):
            return detail.get("code") in {"insufficient_quota", "billing_hard_limit_reached"} or detail.get("type") == "insufficient_quota"
    return False


def _retry_delay(error: APIStatusError | APIConnectionError, attempt: int) -> float | None:
    if isinstance(error, APIStatusError):
        if _quota_error(error) or error.status_code not in {408, 409, 429} and error.status_code < 500:
            return None
        hint = error.response.headers.get("retry-after")
        if hint is not None:
            try:
                delay = float(hint)
            except ValueError:
                return None
            return max(0.1, delay) if math.isfinite(delay) and 0 <= delay <= 30 else None
    return float(2 ** attempt)


def _status_error(error: APIStatusError, *, api_key: str = "") -> tuple[str, str]:
    if _quota_error(error):
        return "provider_quota", "OpenAI API credits or billing quota are exhausted. Check API billing; completed edits are retained."
    if error.status_code == 429:
        return "provider_rate_limit", "OpenAI rate limit reached. Wait for the limit to reset and retry; completed edits are retained."
    if error.status_code == 401:
        return "provider_auth", "OpenAI rejected OPENAI_API_KEY. Check that the saved key is valid."
    if error.status_code in {403, 404}:
        return "provider_request_error", "OpenAI model access was denied or the model was not found. Check OPENAI_MODEL and project access."
    message = f"OpenAI request failed (HTTP {error.status_code})."
    body = error.body
    if isinstance(body, Mapping):
        detail = body.get("error", body)
        if isinstance(detail, Mapping) and isinstance(detail.get("message"), str):
            reason = str(detail["message"])
            if api_key:
                reason = reason.replace(api_key, "[REDACTED]")
            reason = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", reason)
            message += " " + reason[:600]
    return "provider_request_error", message


def _configured_key() -> str:
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if value or os.name != "nt":
        return value
    # Existing terminals may predate a key added through Windows Environment Variables.
    import winreg
    for root, path in ((winreg.HKEY_CURRENT_USER, "Environment"),
                       (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
        try:
            with winreg.OpenKey(root, path) as registry:
                saved, _ = winreg.QueryValueEx(registry, "OPENAI_API_KEY")
                if isinstance(saved, str) and saved.strip():
                    return saved.strip()
        except OSError:
            continue
    return ""


def create_agent(client: MCPClient) -> BasicAgentLoop:
    api_key = _configured_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required. Save your OpenAI API key in the environment; never commit it.")
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip()
    if not model:
        raise ValueError("OPENAI_MODEL must not be blank when provided")
    return BasicAgentLoop(OpenAIProvider(model, api_key=api_key), client)
