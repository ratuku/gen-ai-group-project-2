# Basic agent loop

`BasicAgentLoop` implements the existing `AgentLoop.run(task)` contract. It owns
conversation history and repeatedly asks a `ModelProvider` what to do next:

1. Append the user's task and discover MCP tool definitions through the tool
   dispatcher.
2. Send history and tool definitions to `provider.stream(messages, tools)`.
3. Collect the assistant's text and complete tool-call events.
4. Validate requested tool names and arguments.
5. Route valid calls through the configured execution policy and MCP client.
6. Append every tool result and request the next model turn.
7. Finish with the model's nonempty final response, or report the iteration limit.

The default limit is eight model requests per user task. Multiple tool calls in a
single response finish sequentially before the next model request. The limit counts
model turns, not tool calls. A tool call on the last allowed turn is executed and
recorded, but no additional model request is made to summarize its result. The UI
reports a limit error instead of inventing a final answer.

## Connect a model provider

The loop is provider-independent. A provider adapter supplies normalized events;
it is responsible for its API connection and native tool-call encoding. Put a
factory in an importable module and select it with `--agent module:create_agent`:

```python
from coding_assistant.agent import BasicAgentLoop

def create_agent(client):
    provider = ...  # Any implementation of the ModelProvider protocol.
    return BasicAgentLoop(provider, client, max_iterations=8)
```

The project includes Ollama and Groq Cloud implementations. Select them with
`--provider ollama` or `--provider groq` after setting the required environment
variables. See [Ollama provider](ollama-provider.md) and
[Groq Cloud provider](groq-provider.md) for setup and live examples. A custom
factory configures its own iteration limit.

## Provider event and history contract

Providers emit `text` events with string `content`, complete `tool_call` events
with `name`, object `arguments`, and optional string `id`, and optionally a
`completed` marker. A response containing tool calls continues the loop even when
it also contains a completed marker. Ending a response with nonempty text and no
tool calls is a final answer. Empty responses and provider errors become readable
failure events. The loop emits exactly one final `completed` event on normal or
handled-error exit, with reason `answered`, `iteration_limit`, or `error`.

History is provider-neutral:

- User: `role=user`, `content=task`.
- Assistant: `role=assistant`, concatenated `content`, optional `tool_calls` list
  containing `{id, name, arguments}` objects.
- Tool: `role=tool`, `name`, `tool_call_id`, and `content` containing the complete
  normalized MCP result object.

History persists across tasks on the same agent instance; the `messages` property
returns a deep copy. Tool exceptions become error results for the next model turn.
There are no automatic retries. On cancellation, pending tool calls get an
interruption result so later requests do not inherit unmatched calls. Concurrent
tasks on one agent are rejected. History trimming and durable session storage are
not included in this basic version.

## Tool discovery, validation, and execution policy

At the start of each task, `ToolDispatcher.discover` obtains normalized MCP tool
definitions and atomically builds a registry keyed by exact discovered tool name.
It checks every input schema and compiles its JSON Schema validator before exposing
the definitions to the model. Duplicate names, malformed definitions, and invalid
schemas fail discovery rather than leaving a partially refreshed registry.

For each requested call, the dispatcher requires an exact name match and validates
the argument object without coercing values or inserting schema defaults. Unknown
tools and invalid arguments are not sent to MCP. Instead, they become model-visible
tool results with `is_error=true` and stable error codes `unknown_tool` and
`invalid_arguments`. An MCP invocation exception similarly becomes
`tool_invocation_failed`; server-returned error results are preserved.

Valid calls pass through `PolicyMCPClient`. In the default `confirm` mode, the CLI
shows the exact tool name and arguments, waits for a per-call decision, and invokes
MCP only after approval. Rejection returns a model-visible result with
`error_code=tool_rejected`; it is added to history like any other tool result. In
`auto` mode, valid calls are delegated immediately. The policy wrapper leaves the
`ModelProvider` and `BasicAgentLoop` interfaces unchanged.

```powershell
coding-assistant --provider groq --execution-mode confirm
coding-assistant --provider groq --execution-mode auto --task "Inspect this project"
```

Cancellation propagates, and calls are not retried.

## Verification

Unit tests cover discovery, strict validation, exact-name routing, model-visible
failures, sequential and multiple tool calls, confirmation, automatic execution,
rejection without MCP invocation, results in model context, cross-task state,
streaming final answers, iteration limits, and cancellation. Integration tests run
the loop against local MCP test servers and verify that discovered tools are called
and their results are used in final answers. These tests validate the loop contract;
they do not evaluate live-model planning quality.
