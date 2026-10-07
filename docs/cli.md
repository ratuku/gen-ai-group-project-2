# Basic CLI demo

Run these commands from the repository root in your Python 3.11+ environment:

```sh
python -m pip install -e .
npm ci
coding-assistant --help
coding-assistant
```

`python -m coding_assistant.cli` is an equivalent launch command if the console
script is not on PATH. Node.js is needed for the configured filesystem server.

The CLI connects to all servers in `config/mcp.json`, discovers their tools, and
prints each connected server and its tool count. The current config contains only
the filesystem server. When the external MCP server is added to the config, the
same command will connect to both; no CLI changes are needed. A server connection
failure produces an error and a nonzero exit, not a successful connection banner.

## Demo commands

```text
you> /servers
you> /tools
you> list tools
you> list servers
you> /help
you> /exit
```

By default, the CLI explicitly runs a connection-only demo.
Use `coding-assistant --demo-loop` to exercise the basic agent cycle with a
scripted provider and real filesystem calls; see [Basic agent loop](agent-loop.md).
`list tools` and `list servers` pass through a small demo adapter implementing the
existing `AgentLoop.run(task)` interface. Other coding tasks report that an agent
loop is required; this mode does not invoke an LLM or execute filesystem actions.

For one task followed by exit:

```sh
coding-assistant --task "list tools"
coding-assistant --config config/mcp.json --workspace . --task "list servers"
```

`--config` selects an MCP JSON file. `--workspace` overrides `${workspaceRoot}`
for configured servers; otherwise the existing config loader uses the config
directory's parent. Run from the repo root or provide an explicit config path.

`/exit`, `/quit`, `exit`, `quit`, or end-of-input close all MCP connections and
exit successfully. Ctrl+C exits with status 130 and closes connections. Use Ctrl+D
for end-of-input on macOS/Linux; Windows terminals can use `/exit`. One-shot task
failures exit with status 1. Invalid CLI arguments exit with status 2. In interactive
mode, a failed task is shown and the user can submit another task.

## Agent-loop integration

The CLI owns input, output, and MCP connection cleanup. The agent and provider components
own model requests and reasoning; execution approval policy belongs to the later
tool-execution ticket.
The CLI makes no tool-execution decisions for a supplied agent.

Pass a synchronous factory that accepts the connected `MCPClient` and returns an
`AgentLoop` implementation:

```sh
coding-assistant --agent your_agent_module:create_agent
coding-assistant --agent your_agent_module:create_agent --task "Explain README.md"
```

The factory module must be importable in the active environment. `your_agent_module`
is an integration placeholder, not a module shipped in this ticket. The returned
agent's `run(task)` is an async iterator of the existing contract mappings:

- `text` with `content`: streamed answer text.
- `tool_call` with `name`: a visible tool invocation label.
- `tool_result` with `name`, `content`, and optional `is_error`: readable results.
- `status` with `content`: progress.
- `error` with `content` or `message`: task failure.
- `completed`: final completion marker.

The same agent instance is reused across interactive tasks. The agent decides
whether to retain conversation history. Model/provider flags can be added when
their interfaces are implemented; no unavailable provider options are advertised.

## Tests

```sh
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_cli.py
python -m mypy
```

Tests cover prompt input, commands, streamed results, failures, EOF/Ctrl+C cleanup,
one-shot mode, and the agent factory. An integration test starts two real local
stdio echo MCP servers, calls both through an injected test agent, and verifies
disconnection. These are test fixtures, not the future external production server.
