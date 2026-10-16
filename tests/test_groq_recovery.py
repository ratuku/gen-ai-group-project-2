"""Regressions for the live evaluation's tool-name, context, and quota failures."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from copy import deepcopy
import json
from pathlib import Path

import pytest
import httpx
from groq import APIError, APIStatusError, AsyncGroq
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.contracts import Payload
from coding_assistant.config import load_mcp_config
from coding_assistant.mcp import MCPClient
from coding_assistant.providers.groq import GroqProvider, _convert_messages, _convert_tools
from coding_assistant.providers.groq_context import ToolNames, dumps, request_view, tool_view, _result_view, task_progress
from test_groq_provider import FakeGroqClient, FakeMCPClient, collect, status_error, text_chunk, tool_chunk


@pytest.mark.asyncio
async def test_default_provider_sends_consecutive_requests_without_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ScriptedClient([(text_chunk("First"),), (text_chunk("Second"),)])
    monkeypatch.setattr('coding_assistant.providers.groq._SDKGroqClient', lambda key: client)
    provider = GroqProvider("model", api_key="key")
    for expected in ("First", "Second"):
        events = []
        async for event in provider.stream([{"role": "user", "content": "Hi"}], []):
            assert event["type"] != "status"
            events.append(event)
        assert events == [{"type": "text", "content": expected}, {"type": "completed"}]
    assert len(client.calls) == 2
    assert client.closed


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
    original = deepcopy(schema)
    tools: list[Payload] = [{'name': 'one.read', 'input_schema': schema}]
    view = tool_view(_convert_tools(tools), ToolNames(tools))
    parameters = view[0]['function']['parameters']  # type: ignore[index]
    assert parameters['const'] == schema['const']
    assert set(parameters['properties']) == {'title', 'examples'}
    assert parameters['properties']['title'] == {'type': 'string'}
    assert parameters['properties']['examples']['anyOf'][0] == {'type': 'string'}
    assert schema == original


def test_model_schema_accepts_optional_nulls_without_weakening_required_or_nested_arguments() -> None:
    schema = {'type': 'object', 'properties': {
        'path': {'type': 'string'}, 'head': {'type': 'integer', 'minimum': 1},
        'mode': {'enum': ['short', 'full']},
        'nullable': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
        'options': {'type': 'object', 'properties': {'count': {'type': 'integer'}}, 'required': ['count']},
    }, 'required': ['path'], 'additionalProperties': False}
    tools: list[Payload] = [{'name': 'one.read', 'input_schema': schema}]
    original = deepcopy(tools)
    names = ToolNames(tools)
    parameters = tool_view(_convert_tools(tools), names)[0]['function']['parameters']  # type: ignore[index]
    validator = Draft202012Validator(parameters)
    assert validator.is_valid({'path': 'file', 'head': None, 'mode': None, 'nullable': None, 'options': None})
    assert not validator.is_valid({'path': None})
    assert not validator.is_valid({'path': 'file', 'head': 0})
    assert not validator.is_valid({'path': 'file', 'mode': 'unknown'})
    assert not validator.is_valid({'path': 'file', 'options': {'count': None}})
    assert not validator.is_valid({'path': 'file', 'unknown': None})
    assert names.resolve({'name': 'one__read', 'arguments': {
        'path': 'file', 'head': None, 'mode': None, 'nullable': None, 'options': None,
    }})['arguments'] == {'path': 'file', 'nullable': None}
    assert tools == original


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


def test_compacted_check_result_keeps_failure_status_and_traceback_conclusion() -> None:
    result = {'is_error': False, 'structured_content': {
        'command': ['python', '-I', 'C:/' + 'long/path/' * 50 + 'check.py'],
        'returncode': 1, 'timed_out': False, 'passed': False,
        'output': 'Long traceback with repeated filenames\n' * 100
                  + 'AssertionError: Quantities must affect the subtotal\n',
    }}
    view = _result_view(json.dumps(result), 240)
    assert '"passed":false' in view
    assert '"returncode":1' in view
    assert 'AssertionError: Quantities must affect the subtotal' in view
    assert len(view) <= 240


def test_failed_check_and_repeated_reads_remain_visible_after_context_compaction() -> None:
    messages: list[Payload] = [{'role': 'user', 'content': 'Fix cart.py without changing check_cart.py'}]
    for index, name, arguments, result in [
        (0, 'checks.run_python_check', {'path': 'check_cart.py', 'mode': 'script'},
         {'is_error': False, 'structured_content': {'passed': False, 'returncode': 1, 'output': 'AssertionError: wrong total'}}),
        (1, 'filesystem.read_text_file', {'path': 'check_cart.py', 'line_end': 200},
         {'is_error': False, 'content': [{'type': 'text', 'text': 'checks\n' * 3000}]}),
        (2, 'filesystem.read_text_file', {'path': 'check_cart.py', 'line_end': 400},
         {'is_error': False, 'content': [{'type': 'text', 'text': 'checks\n' * 3000}]}),
    ]:
        messages += [
            {'role': 'assistant', 'content': '', 'tool_calls': [{'id': str(index), 'name': name, 'arguments': arguments}]},
            {'role': 'tool', 'tool_call_id': str(index), 'content': result},
        ]
    original = deepcopy(messages)
    names = ToolNames([{'name': 'filesystem.read_text_file'}, {'name': 'checks.run_python_check'}])
    view = request_view(_convert_messages(messages), (), names, budget=5000)
    instructions = str(view[0]['content'])
    assert '"passed":false' in instructions
    assert 'check FAILED on the current code' in instructions
    assert 'Make a corrective edit before rerunning' in instructions
    assert 'Repeated file reads' in instructions
    assert len(dumps({'messages': view, 'tools': ()}).encode()) <= 5000
    assert messages == original

    messages += [
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'fix', 'name': 'filesystem.write_file',
                                                         'arguments': {'path': 'cart.py', 'content': 'pass'}}]},
        {'role': 'tool', 'tool_call_id': 'fix', 'content': {'is_error': False, 'content': 'Written'}},
    ]
    view = request_view(_convert_messages(messages), (), names, budget=5000)
    assert 'code changed after that check' in str(view[0]['content'])
    assert 'Repeated file reads' not in str(view[0]['content'])


def test_old_tasks_and_retrieval_data_do_not_set_current_behavioral_check_state() -> None:
    messages: list[Payload] = [
        {'role': 'user', 'content': 'Earlier task'},
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'old', 'name': 'checks.run_python_check', 'arguments': {'path': 'old.py'}}]},
        {'role': 'tool', 'tool_call_id': 'old', 'content': {'is_error': False, 'structured_content': {'passed': False, 'returncode': 1}}},
        {'role': 'user', 'content': 'New task'},
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'rag', 'name': 'rag.search_docs', 'arguments': {'query': 'test results'}}]},
        {'role': 'tool', 'tool_call_id': 'rag', 'content': {'is_error': False, 'structured_content': {'passed': True, 'returncode': 0}}},
    ]
    names = ToolNames([{'name': 'checks.run_python_check'}, {'name': 'rag.search_docs'}])
    view = request_view(_convert_messages(messages), (), names)
    assert 'Latest behavioral check (data)' not in str(view[0]['content'])


@pytest.mark.asyncio
@pytest.mark.parametrize('extra_tool_request', [False, True])
async def test_passing_checks_and_repeated_reads_finish_with_no_more_tools(extra_tool_request: bool) -> None:
    class CheckedClient(FakeMCPClient):
        async def list_tools(self) -> Sequence[Payload]:
            return [*(await super().list_tools()), {
                'name': 'checks.run_python_check', 'input_schema': {
                    'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path'],
                },
            }]

        async def call_tool(self, name: str, arguments: Payload) -> Payload:
            self.calls.append((name, arguments))
            if name == 'checks.run_python_check':
                return {'is_error': False, 'structured_content': {
                    'passed': True, 'returncode': 0, 'output': 'ALL CART CHECKS PASSED',
                }}
            return {'is_error': False, 'content': [{'type': 'text', 'text': 'def total(): return 40\n'}]}

    turns: list[Exception | Sequence[object]] = [
        (tool_chunk(native_call(0, 'filesystem__read_text_file', '{"path":"cart.py"}')),),
        (tool_chunk(native_call(0, 'checks__run_python_check', '{"path":"check_cart.py"}')),),
        (tool_chunk(native_call(0, 'filesystem__read_text_file', '{"path":"cart.py"}')),),
    ]
    if extra_tool_request:
        turns.append((tool_chunk(native_call(0, 'filesystem__read_text_file', '{"path":"cart.py"}')),))
    turns.append((text_chunk('Cart repaired; all checks passed.'),))
    client = ScriptedClient(turns)
    mcp = CheckedClient()
    provider = GroqProvider('model', api_key='key', client_factory=lambda key: client)
    events = [event async for event in BasicAgentLoop(provider, mcp, max_iterations=4).run('Fix cart.py and run its checks')]
    assert events[-1]['reason'] == 'answered'
    assert events[-1]['iterations'] == 4
    assert len(mcp.calls) == 3
    assert client.calls[-1]['tools'] == ()
    assert all(call['tools'] for call in client.calls[:3])
    assert all(call['tools'] == () for call in client.calls[3:])
    assert 'No tools are available for this response' in str(client.calls[-1]['messages'])
    final_messages = client.calls[-1]['messages']
    assert isinstance(final_messages, Sequence)
    assert not any(message.get('role') == 'tool' or 'tool_calls' in message for message in final_messages)
    assert final_messages[-1]['role'] == 'user'

def test_summary_only_requires_a_current_pass_unchanged_code_and_repeated_read() -> None:
    names = ToolNames([{'name': 'filesystem.read_text_file'}, {'name': 'filesystem.write_file'},
                       {'name': 'checks.run_python_check'}])
    messages: list[Payload] = [{'role': 'user', 'content': 'Repair cart'}]
    for index, name, arguments, result in [
        (0, 'filesystem.read_text_file', {'path': 'cart.py'}, {'is_error': False, 'content': 'source'}),
        (1, 'checks.run_python_check', {'path': 'check.py'},
         {'is_error': False, 'structured_content': {'passed': True, 'returncode': 0}}),
        (2, 'filesystem.read_text_file', {'path': 'cart.py'}, {'is_error': False, 'content': 'source'}),
    ]:
        messages += [
            {'role': 'assistant', 'content': '', 'tool_calls': [{'id': str(index), 'name': name, 'arguments': arguments}]},
            {'role': 'tool', 'tool_call_id': str(index), 'content': result},
        ]
    assert task_progress(_convert_messages(messages), names).summary_only
    failed = deepcopy(messages)
    failed[4] = {'role': 'tool', 'tool_call_id': '1', 'content': {
        'is_error': False, 'structured_content': {'passed': False, 'returncode': 1},
    }}
    assert not task_progress(_convert_messages(failed), names).summary_only
    assert not task_progress(_convert_messages(messages + [{'role': 'user', 'content': 'Now add another feature'}]), names).summary_only
    changed = messages + [
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'write', 'name': 'filesystem.write_file', 'arguments': {'path': 'cart.py', 'content': 'new'}}]},
        {'role': 'tool', 'tool_call_id': 'write', 'content': {'is_error': False, 'content': 'written'}},
    ]
    assert not task_progress(_convert_messages(changed), names).summary_only


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
@pytest.mark.parametrize('options, expected', [
    ({'head': None, 'tail': None}, {}),
    ({'head': 2, 'tail': None}, {'head': 2}),
    ({'head': None, 'tail': 3}, {'tail': 3}),
])
async def test_sdk_optional_null_read_survives_groq_schema_validation(
    monkeypatch: pytest.MonkeyPatch, options: dict[str, int | None], expected: dict[str, int],
) -> None:
    class ReadClient(FakeMCPClient):
        async def list_tools(self) -> Sequence[Payload]:
            return [{'name': 'filesystem.read_text_file', 'input_schema': {
                'type': 'object', 'properties': {
                    'path': {'type': 'string'}, 'head': {'type': 'number'}, 'tail': {'type': 'number'},
                }, 'required': ['path'], 'additionalProperties': False,
            }}]

    requests: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        delta: dict[str, object]
        if any(message['role'] == 'tool' for message in payload['messages']):
            delta = {'content': 'Read complete'}
        else:
            arguments = {'path': 'README.md', **options}
            schema = payload['tools'][0]['function']['parameters']
            if not Draft202012Validator(schema).is_valid(arguments):
                return httpx.Response(400, json={'error': {
                    'message': 'Tool call validation failed: /head and /tail expected number, but got null',
                }})
            delta = {'tool_calls': [{
                'index': 0, 'id': 'read', 'type': 'function',
                'function': {'name': 'filesystem__read_text_file', 'arguments': json.dumps(arguments)},
            }]}
        chunk = {'id': 'response', 'object': 'chat.completion.chunk', 'created': 1,
                 'model': 'model', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': 'stop'}]}
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                              text='data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n')

    def sdk(*, api_key: str, max_retries: int, timeout: int) -> AsyncGroq:
        return AsyncGroq(api_key=api_key, max_retries=max_retries,
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr('coding_assistant.providers.groq.AsyncGroq', sdk)
    mcp = ReadClient()
    events = [event async for event in BasicAgentLoop(GroqProvider('model', api_key='test'), mcp).run('Read README')]
    assert events[-1]['reason'] == 'answered'
    assert len(requests) == 2
    assert mcp.calls == [('filesystem.read_text_file', {'path': 'README.md', **expected})]
    assert not any(event['type'] == 'error' for event in events)


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
@pytest.mark.parametrize('stream_error', [True, False])
async def test_rejected_edit_regenerates_with_write_tool_instead_of_repeating_bad_json(stream_error: bool) -> None:
    failed = '{"name":"filesystem__edit_file","arguments":{"edits":[{"oldText":"old"},"newText":"new"}]}}'
    detail = {'message': 'Failed to parse tool call arguments as JSON', 'code': 'tool_use_failed',
              'failed_generation': failed}
    error: APIError
    if stream_error:
        error = APIError(detail['message'], request=httpx.Request('POST', 'https://api.groq.com'), body=detail)
    else:
        error = APIStatusError(detail['message'], response=status_error(400).response, body={'error': detail})
    tools: list[Payload] = [
        {'name': 'filesystem.edit_file', 'input_schema': {'type': 'object'}},
        {'name': 'filesystem.write_file', 'input_schema': {
            'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}},
            'required': ['path', 'content'], 'additionalProperties': False,
        }},
    ]
    original = deepcopy(tools)
    client = ScriptedClient([error, (tool_chunk(native_call(
        0, 'filesystem__write_file', json.dumps({'path': 'cart.py', 'content': 'def total():\n    return 40\n'}),
    )),)])
    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client),
                           [{'role': 'user', 'content': 'Fix cart.py. Run checks before and after.'}], tools)
    assert events[-1]['type'] == 'completed'
    assert events[-2]['name'] == 'filesystem.write_file'
    assert events[-2]['arguments'] == {'path': 'cart.py', 'content': 'def total():\n    return 40\n'}
    assert len(client.calls) == 2
    offered = client.calls[1]['tools']
    assert isinstance(offered, Sequence)
    assert [tool['function']['name'] for tool in offered] == ['filesystem__write_file']
    assert 'complete updated file' in str(client.calls[1]['messages'])
    assert 'requested checks and ordering' in str(client.calls[1]['messages'])
    assert tools == original
    assert detail['failed_generation'] == failed


@pytest.mark.asyncio
async def test_rejected_edit_cannot_execute_after_it_is_removed_from_retry_tools() -> None:
    error = APIError('Failed to parse tool call arguments as JSON',
                     request=httpx.Request('POST', 'https://api.groq.com'),
                     body={'failed_generation': '{"name":"filesystem__edit_file","arguments":broken}'})
    tools: list[Payload] = [
        {'name': 'filesystem.edit_file', 'input_schema': {'type': 'object'}},
        {'name': 'filesystem.write_file', 'input_schema': {'type': 'object'}},
    ]
    client = ScriptedClient([
        error,
        (tool_chunk(native_call(0, 'filesystem__edit_file', '{}')),),
        (text_chunk('I could not perform the edit.'),),
    ])
    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client),
                           [{'role': 'user', 'content': 'Fix file'}], tools)
    assert events[-1]['type'] == 'completed'
    assert not any(event['type'] == 'tool_call' for event in events)


@pytest.mark.asyncio
async def test_rejected_edit_without_write_tool_preserves_discovered_capabilities() -> None:
    error = APIError('Failed to parse tool call arguments as JSON',
                     request=httpx.Request('POST', 'https://api.groq.com'),
                     body={'failed_generation': '{"name":"filesystem__edit_file","arguments":broken}'})
    tools: list[Payload] = [{'name': 'filesystem.edit_file', 'input_schema': {'type': 'object'}}]
    client = ScriptedClient([error, (text_chunk('Unable to edit.'),)])
    await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client),
                  [{'role': 'user', 'content': 'Fix file'}], tools)
    assert client.calls[0]['tools'] == client.calls[1]['tools']


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
async def test_rate_limit_retries_have_their_own_budget_after_format_repairs() -> None:
    parse = APIError('Failed to parse tool call arguments as JSON',
                     request=httpx.Request('POST', 'https://api.groq.com'), body={})
    rate = status_error(429)
    rate.response.headers['retry-after'] = '17.85'
    client = ScriptedClient([parse] * 4 + [rate] * 5 + [(text_chunk('Recovered'),)])
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)

    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client, sleep=sleep),
                           [{'role': 'user', 'content': 'Hello'}], [])
    assert events[-1]['type'] == 'completed'
    assert waits == [17.85] * 5
    assert len(client.calls) == 10
    assert client.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('delay, expected_waits', [(40, 3), (0.1, 10)])
async def test_persistent_rate_limits_stop_at_wait_or_retry_bound(delay: float, expected_waits: int) -> None:
    rate = status_error(429)
    rate.response.headers['retry-after'] = str(delay)
    client = ScriptedClient([rate] * (expected_waits + 1))
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client, sleep=sleep),
                           [{'role': 'user', 'content': 'Hello'}], [])
    assert waits == [delay] * expected_waits
    assert len(client.calls) == expected_waits + 1
    assert events[-1]['error_code'] == 'provider_rate_limit'
    assert client.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('hint, expected', [('217.5ms', 0.2175), ('17.849999999s', 17.849999999)])
async def test_rate_limit_accepts_seconds_or_milliseconds_in_server_hint(hint: str, expected: float) -> None:
    rate = APIStatusError(f'Rate limit reached. Please try again in {hint}.',
                          response=status_error(429).response, body={})
    client = ScriptedClient([rate, (text_chunk('Recovered'),)])
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    events = await collect(GroqProvider('model', api_key='key', client_factory=lambda key: client, sleep=sleep),
                           [{'role': 'user', 'content': 'Hello'}], [])
    assert waits == [expected]
    assert events[-1]['type'] == 'completed'


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
