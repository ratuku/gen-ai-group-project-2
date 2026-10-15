"""Regressions for the live evaluation's tool-name, context, and quota failures."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from copy import deepcopy
import json
from pathlib import Path

import pytest
import httpx
from groq import APIError, APIStatusError, AsyncGroq

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.contracts import Payload
from coding_assistant.config import load_mcp_config
from coding_assistant.mcp import MCPClient
from coding_assistant.providers.groq import GroqProvider, _convert_messages, _convert_tools
from coding_assistant.providers.groq_context import ToolNames, dumps, request_view, tool_view
from coding_assistant.providers.groq_pacing import RequestPacer
from test_groq_provider import FakeGroqClient, FakeMCPClient, collect, status_error, text_chunk, tool_chunk


@pytest.mark.asyncio
async def test_pacer_reserves_rolling_tokens_and_reports_cancellable_waits() -> None:
    now = [0.0]
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)
        now[0] += delay

    pacer = RequestPacer(7000, clock=lambda: now[0], sleep=sleep)
    assert [e async for e in pacer.reserve(4000)] == []
    events = [e async for e in pacer.reserve(4000)]
    assert sum(waits) == 60 and all(wait <= 5 for wait in waits)
    assert all(e["wait_seconds"] == 5 for e in events)
    assert [e async for e in pacer.reserve(1000)]  # request-spacing guard
    assert now[0] == 62.1
    with pytest.raises(ValueError, match="allowance"):
        _ = [e async for e in pacer.reserve(7001)]


@pytest.mark.asyncio
async def test_daily_quota_is_not_retried_even_with_short_wait_hint() -> None:
    error = APIStatusError("Rate limit reached on tokens per day (TPD)",
                           response=status_error(429).response, body={})
    error.response.headers["retry-after"] = "1"
    client = ScriptedClient([error])
    provider = GroqProvider("model", api_key="key", client_factory=lambda key: client)
    events = [e async for e in BasicAgentLoop(provider, FakeMCPClient()).run("Task")]
    assert len(client.calls) == 1
    assert any(e.get("error_code") == "provider_daily_limit" for e in events)
    assert not any("waiting" in str(e.get("content")) for e in events)


@pytest.mark.asyncio
async def test_cancelled_pacing_wait_never_sends_an_api_request() -> None:
    pacer = RequestPacer()
    _ = [event async for event in pacer.reserve(7000)]
    client = ScriptedClient([(text_chunk("should not run"),)])
    provider = GroqProvider("model", api_key="key", pacer=pacer, client_factory=lambda key: client)
    stream = provider.stream([{"role": "user", "content": "Hi"}], [])
    event = await anext(stream)
    assert "pacing" in str(event["content"])
    task: asyncio.Future[Payload] = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.closed and not client.calls


def test_syntax_feedback_survives_compacted_source_result() -> None:
    messages: list[Payload] = [{"role": "user", "content": "Fix source"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "read", "name": "one.read", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "read", "content": {"is_error": False,
            "content": [{"type": "text", "text": "x" * 30000}],
            "validation": {"passed": False, "detail": "IndentationError: repair this source"}}}]
    view = request_view(_convert_messages(messages), (), ToolNames([{"name": "one.read"}]), budget=5000)
    assert "IndentationError" in str(view)


class ScriptedClient(FakeGroqClient):
    def __init__(self, turns: list[Exception | Sequence[object]]) -> None:
        super().__init__()
        self.turns = iter(turns)

    async def chat(self, *, model: str, messages: Sequence[Mapping[str, object]],
                   tools: Sequence[Mapping[str, object]], stream: bool) -> AsyncIterator[object]:
        self.calls.append({'model': model, 'messages': deepcopy(messages), 'tools': deepcopy(tools)})
        turn = next(self.turns)
        if isinstance(turn, Exception):
            raise turn

        async def chunks() -> AsyncIterator[object]:
            for chunk in turn:
                yield chunk

        return chunks()


def native_call(index: int, name: str, arguments: str) -> Payload:
    return {'index': index, 'id': f'call_{index}', 'function': {'name': name, 'arguments': arguments}}


@pytest.mark.asyncio
async def test_alias_and_unique_short_name_execute_only_discovered_tool() -> None:
    tools = await FakeMCPClient().list_tools()
    names = ToolNames(tools)
    assert names.forward['filesystem.read_text_file'] == 'filesystem__read_text_file'
    for native in ('filesystem__read_text_file', 'read_text_file'):
        client = ScriptedClient([(tool_chunk(native_call(0, native, '{"path":"README.md"}')),),
                                 (text_chunk('Done'),)])
        provider = GroqProvider('model', api_key='key', client_factory=lambda key: client)
        mcp = FakeMCPClient()
        events = [event async for event in BasicAgentLoop(provider, mcp).run('Read README.md')]
        assert mcp.calls == [('filesystem.read_text_file', {'path': 'README.md'})]
        assert events[-1]['reason'] == 'answered'


def test_ambiguous_short_names_and_wrong_server_are_not_routed() -> None:
    names = ToolNames([{'name': 'one.read'}, {'name': 'two.read'}])
    assert names.resolve({'name': 'read', 'arguments': {}})['name'] == 'read'
    assert names.resolve({'name': 'unknown.read', 'arguments': {}})['name'] == 'unknown.read'


def test_alias_collisions_are_distinct_and_deterministic() -> None:
    tools: list[Payload] = [{'name': 'one.two'}, {'name': 'one__two'}, {'name': 'x' * 90}]
    first, second = ToolNames(tools), ToolNames(list(reversed(tools)))
    assert first.forward == second.forward
    assert len(set(first.forward.values())) == 3
    assert all(len(alias) <= 64 for alias in first.forward.values())


def test_omit_only_optional_nulls_that_schema_forbids() -> None:
    tool: Payload = {'name': 'filesystem.read_text_file', 'input_schema': {
        'type': 'object', 'properties': {'path': {'type': 'string'}, 'head': {'type': 'number'},
                                      'nullable': {'anyOf': [{'type': 'number'}, {'type': 'null'}]}},
        'required': ['path']}}
    names = ToolNames([tool])
    call: Payload = {'name': 'read_text_file', 'arguments': {'path': None, 'head': None, 'nullable': None, 'unknown': None}}
    assert names.resolve(call)['arguments'] == {'path': None, 'nullable': None, 'unknown': None}
    assert call['arguments'] == {'path': None, 'head': None, 'nullable': None, 'unknown': None}


def test_schema_annotations_do_not_remove_properties_or_change_literal_values() -> None:
    schema = {'type': 'object', 'properties': {'title': {'type': 'string'}, 'examples': {'type': 'string'}},
              'required': ['title'], 'const': {'description': 'x' * 300}}
    tools: list[Payload] = [{'name': 'one.read', 'input_schema': schema}]
    view = tool_view(_convert_tools(tools), ToolNames(tools))
    assert view[0]['function']['parameters'] == schema  # type: ignore[index]


def history(count: int) -> list[Payload]:
    messages: list[Payload] = [{'role': 'user', 'content': 'Preserve this task exactly'}]
    for i in range(count):
        messages += [{'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': str(i), 'name': 'one.read', 'arguments': {'path': 'file.py'}}]},
            {'role': 'tool', 'tool_call_id': str(i), 'content': {
                'is_error': False, 'content': [{'type': 'text', 'text': 'evidence' * 120}],
                'structured_content': {'text': 'evidence' * 120}}}]
    return messages


def test_context_is_bounded_without_mutating_history_or_orphaning_results() -> None:
    messages = history(20)
    original = deepcopy(messages)
    names = ToolNames([{'name': 'one.read'}])
    view = request_view(_convert_messages(messages), (), names, budget=5000)
    assert len(dumps({'messages': view, 'tools': ()}).encode()) <= 5000
    assert view[1] == {'role': 'user', 'content': 'Preserve this task exactly'}
    ids = {call['id'] for message in view for call in message.get('tool_calls', [])}  # type: ignore[attr-defined]
    assert all(message.get('tool_call_id') in ids for message in view if message['role'] == 'tool')
    assert messages == original
    assert 'already executed' in str(view[0])


def test_duplicate_structured_result_is_removed_and_oversize_task_fails_explicitly() -> None:
    messages = history(1)
    view = request_view(_convert_messages(messages), (), ToolNames([{'name': 'one.read'}]))
    data = json.loads(str(view[-1]['content']))
    assert data == {'is_error': False, 'result': {'text': 'evidence' * 120}}
    with pytest.raises(ValueError, match='cannot fit'):
        request_view([{'role': 'user', 'content': 'x' * 20000}], (), ToolNames([]), budget=5000)


def test_large_completed_edit_is_summarized_with_its_outcome() -> None:
    messages: list[Payload] = [
        {'role': 'user', 'content': 'Edit this file'},
        {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'edited', 'name': 'one.edit', 'arguments': {'content': 'x' * 30000}}]},
        {'role': 'tool', 'tool_call_id': 'edited', 'content': {'is_error': False, 'content': 'Successfully edited file'}},
    ]
    original = deepcopy(messages)
    view = request_view(_convert_messages(messages), (), ToolNames([{'name': 'one.edit'}]), budget=5000)
    assert len(dumps({'messages': view, 'tools': ()}).encode()) <= 5000
    assert 'Already executed' in str(view[-1])
    assert '"is_error":false' in str(view[-1])
    assert not any(message['role'] == 'tool' for message in view)
    assert messages == original


@pytest.mark.asyncio
async def test_rate_limit_wait_is_visible_bounded_and_does_not_execute_tools() -> None:
    error = status_error(429)
    error.response.headers['retry-after'] = '0.25'
    client = ScriptedClient([error, (text_chunk('Recovered'),)])
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)

    provider = GroqProvider('model', api_key='key', client_factory=lambda key: client, sleep=sleep)
    events = [event async for event in BasicAgentLoop(provider, FakeMCPClient()).run('Hello')]
    assert waits == [0.25]
    assert any('waiting 0.25s' in str(event.get('content')) for event in events if event['type'] == 'status')
    assert events[-1]['reason'] == 'answered'
    assert client.closed


@pytest.mark.parametrize('delay', ['NaN', 'inf', '-1', '3600'])
@pytest.mark.asyncio
async def test_invalid_or_long_retry_after_does_not_wait(delay: str) -> None:
    error = status_error(429)
    error.response.headers['retry-after'] = delay
    client = ScriptedClient([error])
    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client),
                           [{'role': 'user', 'content': 'Hello'}], [])
    assert len(client.calls) == 1
    assert events[-1]['type'] == 'error'


@pytest.mark.asyncio
async def test_413_reduces_payload_without_changing_agent_history() -> None:
    client = ScriptedClient([status_error(413), (text_chunk('Recovered'),)])
    messages = history(15)
    original = deepcopy(messages)
    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client), messages, [])
    assert events[-1]['type'] == 'completed'
    assert len(dumps(client.calls[1]['messages'])) < len(dumps(client.calls[0]['messages']))
    assert messages == original


@pytest.mark.asyncio
async def test_empty_stream_and_malformed_batch_recover_before_any_execution() -> None:
    bad = tool_chunk(native_call(0, 'filesystem.read_text_file', '{"path":"README.md"}'),
                     native_call(1, 'filesystem.read_text_file', 'not-json'))
    client = ScriptedClient([(), (bad,), (text_chunk('Recovered'),)])
    mcp = FakeMCPClient()
    provider = GroqProvider('model', api_key='key', client_factory=lambda key: client)
    events = [event async for event in BasicAgentLoop(provider, mcp).run('Hello')]
    assert events[-1]['reason'] == 'answered'
    assert len(client.calls) == 3
    assert not mcp.calls


@pytest.mark.asyncio
async def test_control_marker_tool_name_is_regenerated_without_guessing_a_route() -> None:
    bad = tool_chunk(native_call(0, 'filesystem__read_text_file<|channel|>commentary', '{"path":"README.md"}'))
    client = ScriptedClient([(bad,), (text_chunk('Recovered'),)])
    mcp = FakeMCPClient()
    events = [event async for event in BasicAgentLoop(
        GroqProvider('model', api_key='key', client_factory=lambda key: client), mcp).run('Hello')]
    assert events[-1]['reason'] == 'answered'
    assert len(client.calls) == 2
    assert not mcp.calls


@pytest.mark.asyncio
async def test_cancellation_during_retry_wait_closes_client() -> None:
    error = status_error(429)
    error.response.headers['retry-after'] = '10'
    client = ScriptedClient([error])
    started = asyncio.Event()

    async def sleep(delay: float) -> None:
        started.set()
        await asyncio.Event().wait()

    provider = GroqProvider('model', api_key='key', client_factory=lambda key: client, sleep=sleep)
    task = asyncio.create_task(collect(provider, [{'role': 'user', 'content': 'Hi'}], []))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.closed


@pytest.mark.asyncio
async def test_sdk_sends_bounded_generation_and_local_validation_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        chunk = {'id': 'response', 'object': 'chat.completion.chunk', 'created': 1,
                 'model': 'openai/gpt-oss-20b', 'choices': [
                     {'index': 0, 'delta': {'content': 'Done'}, 'finish_reason': 'stop'}]}
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                              text='data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n')

    def sdk(*, api_key: str, max_retries: int, timeout: int) -> AsyncGroq:
        assert max_retries == 0 and timeout == 45
        return AsyncGroq(api_key=api_key, max_retries=max_retries,
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr('coding_assistant.providers.groq.AsyncGroq', sdk)
    events = await collect(GroqProvider('openai/gpt-oss-20b', api_key='test'),
                           [{'role': 'user', 'content': 'Hello'}], await FakeMCPClient().list_tools())
    assert events[-1]['type'] == 'completed'
    payload = requests[0]
    assert payload['disable_tool_validation'] is True
    assert payload['parallel_tool_calls'] is False
    assert payload['max_completion_tokens'] == 2048
    assert payload['temperature'] == 0
    assert payload['reasoning_effort'] == 'low'


@pytest.mark.asyncio
async def test_transient_service_failure_retries_without_tools_running() -> None:
    client = ScriptedClient([status_error(503), (text_chunk('Recovered'),)])
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)

    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client, sleep=sleep),
                           [{'role': 'user', 'content': 'Hello'}], [])
    assert events[-1]['type'] == 'completed'
    assert waits == [1.0]


@pytest.mark.asyncio
async def test_partial_text_is_not_replayed_after_stream_failure() -> None:
    error = status_error(429)
    error.response.headers['retry-after'] = '1'

    class PartialClient(FakeGroqClient):
        async def chat(self, *, model: str, messages: Sequence[Mapping[str, object]],
                       tools: Sequence[Mapping[str, object]], stream: bool) -> AsyncIterator[object]:
            self.calls.append({})

            async def chunks() -> AsyncIterator[object]:
                yield text_chunk('Partial response')
                raise error

            return chunks()

    client = PartialClient()
    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client),
                           [{'role': 'user', 'content': 'Hello'}], [])
    assert [e['type'] for e in events] == ['text', 'error']
    assert len(client.calls) == 1
    assert client.closed


@pytest.mark.asyncio
async def test_sdk_http_200_stream_error_is_repaired_before_tool_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        attempts.append(json.loads(request.content))
        data: dict[str, object]
        if len(attempts) == 1:
            data = {'error': {'message': 'Failed to parse tool call arguments as JSON'}}
        else:
            data = {'id': 'ok', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'model',
                    'choices': [{'index': 0, 'delta': {'content': 'Recovered'}, 'finish_reason': 'stop'}]}
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                              text='data: ' + json.dumps(data) + '\n\ndata: [DONE]\n\n')

    def sdk(*, api_key: str, max_retries: int, timeout: int) -> AsyncGroq:
        return AsyncGroq(api_key=api_key, max_retries=0,
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr('coding_assistant.providers.groq.AsyncGroq', sdk)
    mcp = FakeMCPClient()
    provider = GroqProvider('model', api_key='test')
    events = [e async for e in BasicAgentLoop(provider, mcp).run('Hello')]
    assert events[-1]['reason'] == 'answered'
    assert any('rejected tool stream' in str(e.get('content')) for e in events)
    assert len(attempts) == 2
    assert not mcp.calls


@pytest.mark.asyncio
async def test_windows_python_edit_keeps_indentation_with_real_filesystem_server(tmp_path: Path) -> None:
    path = tmp_path / 'solution.py'
    path.write_bytes(b'def average(values):\r\n    return sum(values) / (len(values) - 1)\r\n')
    old = 'def average(values):\r\n    return sum(values) / (len(values) - 1)\r'
    new = 'def average(values):\n    """Return the mean."""\n    if not values: raise ValueError("empty")\n    return sum(values) / len(values)\n'
    names = ToolNames([{'name': 'filesystem.edit_file', 'input_schema': {}}])
    original: Payload = {'name': 'filesystem.edit_file', 'arguments': {
        'path': str(path), 'edits': [{'oldText': old, 'newText': new}]}}
    call = names.resolve(original)
    config = load_mcp_config(Path(__file__).resolve().parents[1] / 'config/mcp.json', workspace_root=tmp_path)
    filesystem = next(server for server in config.servers if server.name == 'filesystem')
    async with MCPClient([filesystem]) as client:
        assert isinstance(call['arguments'], Mapping)
        result = await client.call_tool(str(call['name']), call['arguments'])
    assert not result['is_error'], result
    source = path.read_text(encoding='utf-8')
    compile(source, str(path), 'exec')
    assert source == new
    assert original['arguments']['edits'][0]['oldText'] == old  # type: ignore[index]


@pytest.mark.asyncio
async def test_parse_repair_can_survive_following_short_rate_limits() -> None:
    parse = APIError('Failed to parse tool call arguments as JSON',
                     request=httpx.Request('POST', 'https://api.groq.com'), body={})
    first, second = status_error(429), status_error(429)
    first.response.headers['retry-after'] = '2'
    second.response.headers['retry-after'] = '1'
    client = ScriptedClient([parse, first, second, (text_chunk('Recovered'),)])
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)

    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client, sleep=sleep),
                           [{'role': 'user', 'content': 'Hello'}], [])
    assert events[-1]['type'] == 'completed'
    assert waits == [2, 1]
    assert len(client.calls) == 4


@pytest.mark.asyncio
async def test_daily_limit_stops_without_waiting_and_reports_retained_edits() -> None:
    request = httpx.Request('POST', 'https://api.groq.com')
    error = APIStatusError('tokens per day allowance exhausted',
                           response=httpx.Response(429, request=request, headers={'retry-after': '960'}), body={})
    client = ScriptedClient([error])
    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client),
                           [{'role': 'user', 'content': 'Hello'}], [])
    assert len(client.calls) == 1
    assert 'daily allowance' in str(events[-1]['content'])
    assert 'edits are retained' in str(events[-1]['content'])
