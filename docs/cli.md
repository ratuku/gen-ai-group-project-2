# Juniper CLI usage

Run these commands from the repository root in Windows PowerShell. Python 3.11+
and Node.js are required. The CLI itself does not need a GPU.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
npm.cmd ci
.\.venv\Scripts\coding-assistant.exe --help
.\.venv\Scripts\coding-assistant.exe --connection-demo
```

`.\.venv\Scripts\python.exe -m coding_assistant.cli` is an equivalent launch
command. Invoking the environment's executable directly avoids activation and PATH
requirements. If the environment is already activated, `coding-assistant` works too.

The normal CLI connects to all servers in `config/mcp.json`, discovers their tools,
and prints each connected server and its tool count. The current config contains
the filesystem and hosted DeepWiki servers, so normal CLI use requires internet
access. A server connection failure produces an error and a nonzero exit, not a
successful connection banner.

`--demo-loop` intentionally selects only the filesystem server. This keeps the
scripted workspace demonstration independent of DeepWiki and internet availability
while normal CLI and custom-agent modes retain access to every configured server.

## Terminal display

Juniper shows the workspace, provider, model, connected-server count, version, and
current execution behavior in its startup panel. Model text streams as it arrives.
Tool panels show the qualified tool name and its arguments; result panels show
the returned content. Long results show the first 16 lines in the terminal while
the complete result remains available to the model. `/tools` shows a tool table.

Captured single-task output uses plain labels. Set `NO_COLOR` to disable colors.
The current execution behavior is automatic; confirmation mode is separate work
in issue #13 and is not advertised as implemented.

## Demo commands

```text
juniper> /servers
juniper> /tools
juniper> list tools
juniper> list servers
juniper> /help
juniper> /exit
```

The default CLI runs the real Groq agent. Use `--connection-demo` to explicitly
select connection discovery without an LLM.
Use `.\.venv\Scripts\coding-assistant.exe --demo-loop` to exercise the basic agent cycle with a
scripted provider and real filesystem calls; see [Basic agent loop](agent-loop.md).
In `--connection-demo`, `list tools` and `list servers` pass through a small adapter implementing the
existing `AgentLoop.run(task)` interface. Other coding tasks report that an agent
loop is required; this mode does not invoke an LLM or execute filesystem actions.

For one task followed by exit:

```powershell
.\.venv\Scripts\coding-assistant.exe --connection-demo --task "list tools"
.\.venv\Scripts\coding-assistant.exe --connection-demo --config .\config\mcp.json --workspace . --task "list servers"
.\.venv\Scripts\coding-assistant.exe --demo-loop --task "inspect workspace"
```

`--config` selects an MCP JSON file. `--workspace` overrides `${workspaceRoot}`
for configured servers; otherwise the existing config loader uses the config
directory's parent. Run from the repo root or provide an explicit config path.

`/exit`, `/quit`, `exit`, `quit`, or end-of-input close all MCP connections and
exit successfully. Ctrl+C exits with status 130 and closes connections. Use Ctrl+D
for end-of-input on macOS/Linux; Windows terminals can use `/exit`. One-shot task
failures exit with status 1. Invalid CLI arguments exit with status 2. In interactive
mode, a failed task is shown and the user can submit another task.

Interactive mode requires a real Windows terminal. When launching from a script
with redirected input/output, use `--task` instead of piping prompts into the CLI.

## Groq cloud tasks

Groq runs the model in the cloud, so a powerful local GPU is unnecessary. Set
`GROQ_API_KEY` in the same terminal that launches the CLI. In PowerShell 7+, masked
input keeps the key out of command history:

```powershell
$env:GROQ_API_KEY = Read-Host "Groq API key" -MaskInput
.\.venv\Scripts\coding-assistant.exe --provider groq
```

The live-provider prompt says `Enter a task.`; demo modes show their supported
example task. For a single model-backed task:

```powershell
.\.venv\Scripts\coding-assistant.exe `
  --provider groq `
  --workspace . `
  --task "List the top-level project files using the filesystem tool."
```

The default model is configured by the provider; `GROQ_MODEL` overrides it. See
[Groq provider setup](groq-provider.md) for configuration and troubleshooting.
Prompts, tool definitions, and returned file contents are sent to Groq. Use a
temporary workspace containing only harmless sample files when checking this flow.

To check a text-only request without starting any MCP servers, create an empty
configuration outside the repository:

```powershell
$cliTestConfig = Join-Path ([IO.Path]::GetTempPath()) "coding-assistant-empty-mcp.json"
[IO.File]::WriteAllText($cliTestConfig, '{"mcpServers": {}}')
.\.venv\Scripts\coding-assistant.exe `
  --config $cliTestConfig `
  --provider groq `
  --task "Reply with one short greeting."
```

For filesystem-only tests, use a separate configuration containing just the
`filesystem` entry from `config/mcp.json`, with the Node server script path resolved
for that configuration's location. This avoids connecting to DeepWiki. Pass
`--workspace` with the sample directory. Do not commit or print the API key.

## Agent-loop integration

Use `--provider groq` (the default) or `--provider ollama` for the shipped adapters.
Ollama requires `OLLAMA_MODEL`; Groq requires `GROQ_API_KEY`, with optional
`GROQ_MODEL`. Providers, custom factories, and demo modes are mutually exclusive.

The CLI owns input, output, and MCP connection cleanup. The agent and provider components
own model requests and reasoning; execution approval policy belongs to the later
tool-execution ticket.
The CLI makes no tool-execution decisions for a supplied agent.

Pass a synchronous factory that accepts the connected `MCPClient` and returns an
`AgentLoop` implementation:

```powershell
.\.venv\Scripts\coding-assistant.exe --agent your_agent_module:create_agent
.\.venv\Scripts\coding-assistant.exe --agent your_agent_module:create_agent --task "Explain README.md"
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
whether to retain conversation history. The shipped factories are
`coding_assistant.providers.groq:create_agent` and
`coding_assistant.providers.ollama:create_agent`; see their provider documentation
for environment-based model configuration.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests/test_cli.py
.\.venv\Scripts\python.exe -m mypy
```

Tests cover prompt input, commands, streamed results, failures, EOF/Ctrl+C cleanup,
one-shot mode, and the agent factory. An integration test starts two real local
stdio echo MCP servers, calls both through an injected test agent, and verifies
disconnection. These local test fixtures are separate from the configured hosted
DeepWiki server.

DeepWiki reads documentation and answers questions about specific public GitHub
repositories. Include a repository in `owner/repo` format in your task, for example:

```text
Use DeepWiki to explain the architecture of modelcontextprotocol/python-sdk.
```

The server name `deepwiki` is not a valid repository name.

See the [issue #8 verification record](cli-verification.md) for the automated and
live Windows/Groq checks performed on October 10, 2026.
