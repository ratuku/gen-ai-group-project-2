# Basic agent loop

`BasicAgentLoop` implements the existing `AgentLoop.run(task)` contract. It owns
conversation history and repeatedly asks a `ModelProvider` what to do next:

1. Append the user's task and discover MCP tool definitions through the tool
   dispatcher.
2. Send the history and tool definitions to `provider.stream(messages, tools)`.
3. Collect the assistant's text and complete tool-call events.
4. Validate requested tool names and arguments, then invoke valid calls
   sequentially through the existing `MCPClient.call_tool`.
5. Append all tool results, including structured content and error flags, and
   request the next model turn.
6. Finish with the model's nonempty final response, or report the iteration limit.

The default limit is eight model requests per user task. Multiple tool calls in a
single response all finish before the next model request. The limit counts model
turns, not individual tool calls. A tool call on the last allowed turn is executed
and recorded, but no additional model request is made to summarize its result.
The UI reports a limit error in that case, rather than inventing a final answer.

## Run the basic demo

```sh
coding-assistant --demo-loop
```

At the prompt, enter `inspect workspace`. The scripted provider first requests the
filesystem server's allowed directories, then lists the first allowed directory,
then builds a readable final response from that returned listing. Both calls are
real MCP calls. **The demo provider is deterministic, not a live LLM.** It supports
only this task and requires a server named `filesystem` with the two listing tools.
No file writes occur in this demo. The CLI connects only the filesystem server for
this workflow, so DeepWiki and internet access are not required.

```sh
coding-assistant --demo-loop --task "inspect workspace"
coding-assistant --demo-loop --max-iterations 1 --task "inspect workspace"
```

The second command demonstrates a readable iteration-limit failure (exit 1).
`/servers`, `/tools`, `/help`, and `/exit` also work in interactive loop-demo mode.

## Connect a real model provider

The loop is provider-independent. A provider adapter supplies normalized events;
it is responsible for its API connection and native tool-call encoding. Put a
factory in an importable module and select it with `--agent module:create_agent`:

```python
from coding_assistant.agent import BasicAgentLoop

def create_agent(client):
    provider = ...  # Your implementation of the ModelProvider protocol.
    return BasicAgentLoop(provider, client, max_iterations=8)
```

This example is an integration sketch, not a configured provider. Ollama and cloud
provider adapters remain separate work. The CLI's `--max-iterations` configures
only the built-in demo; a custom factory configures its own agent.

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

## Tool discovery and dispatch

At the start of each task, `ToolDispatcher.discover` obtains the normalized MCP
tool definitions and atomically builds a registry keyed by each exact discovered
tool name. It checks every input schema and compiles the appropriate JSON Schema
validator before the definitions are exposed to the model. Duplicate names,
malformed definitions, and invalid schemas fail discovery rather than leaving a
partially refreshed registry.

For each requested call, the dispatcher requires an exact name match and validates
the argument object without coercing values or inserting schema defaults. Unknown
tools and invalid arguments are not sent to MCP. Instead, they become model-visible
tool results with `is_error=true` and the stable error codes `unknown_tool` and
`invalid_arguments`. An MCP invocation exception similarly becomes
`tool_invocation_failed`; server-returned error results are preserved. These
recoverable results are added to history so the model can correct its request or
explain the failure. Cancellation propagates and calls are not retried.

The dispatcher validates and routes calls; it does not decide whether a valid call
requires user approval or may run automatically. Confirmation and automatic-mode
execution policy remain the scope of issue #13.

## Verification

Unit tests cover dispatcher discovery, strict argument validation, exact-name
routing, model-visible failures, sequential and multiple tool calls, results in
model context, cross-task state, streaming final answers, iteration limits, and
cancellation. The integration test runs the loop against a real local echo MCP
server with a scripted provider and verifies that a discovered tool is invoked and
its result is used in the final answer. This tests the loop contract; it does not
evaluate live-model planning quality.
