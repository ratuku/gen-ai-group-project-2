# Juniper CLI usage

Run these commands from the repository root in Windows PowerShell. Python 3.11+
and Node.js are required. The CLI itself does not need a GPU.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[rag]"
npm.cmd ci
.\.venv\Scripts\coding-assistant.exe --help
.\.venv\Scripts\coding-assistant.exe --connection-check --task "list tools"
```

`.\.venv\Scripts\python.exe -m coding_assistant.cli` is an equivalent launch
command. Invoking the environment's executable directly avoids activation and PATH
requirements. If the environment is already activated, `coding-assistant` works too.

The CLI connects to all servers in `config/mcp.json`, discovers their tools, and
prints each connected server and its tool count. The current config contains the
filesystem, hosted DeepWiki, custom local RAG, and Python-check servers, so normal CLI use requires internet access.
A fresh checkout also needs `python -m rag_server.prepare` followed by
`python -m rag_server.index` before the first RAG query; see the root README.
A server connection failure produces an error and a nonzero exit, not a successful
connection banner.

## Execution modes

`--execution-mode confirm` is the default. For each valid model-requested action,
Juniper first shows a tool panel containing the exact qualified tool name and
arguments, then asks `Execute <tool>? [y/N]`. Enter `y` or `yes` to run it. Enter
`n`, `no`, or a blank response to reject it. Invalid answers are prompted again.
End-of-input safely rejects the pending action.

A rejected action never reaches the MCP server. The agent receives a normalized
error result with `error_code=tool_rejected`, so the model can explain the rejection
or choose a different action. Approval applies to one tool call only; another tool
call requires another decision.

Use automatic execution only in a workspace and configuration you trust:

```powershell
.\.venv\Scripts\coding-assistant.exe --provider groq --execution-mode auto
```

In `auto` mode, validated actions run without an approval prompt. Unknown tools and
invalid arguments are still blocked by the dispatcher in both modes.

## Terminal display and commands

Juniper shows the workspace, provider, model, connected-server count, version, and
execution mode in its startup panel. Model text streams as it arrives. Tool panels
show the qualified tool name and arguments; result panels show returned content.
Long results show the first 16 lines in an interactive terminal while the complete
result remains available to the model. `/tools` shows the discovered-tool table.

```text
juniper> /servers
juniper> /tools
juniper> /help
juniper> /exit
```

`/exit`, `/quit`, `exit`, `quit`, or end-of-input close all MCP connections and
exit successfully. Ctrl+C exits with status 130 and closes connections. Use Ctrl+D
for end-of-input on macOS/Linux; Windows terminals can use `/exit`. One-shot task
failures exit with status 1. Invalid CLI arguments exit with status 2. In interactive
mode, a failed task is shown and the user can submit another task.

Interactive mode requires a real terminal. When launching from a script with
redirected input/output, use `--task`. A one-shot task can still prompt for each
tool approval unless `--execution-mode auto` is selected.

## Connection check

`--connection-check` lists configured connections or tools without starting a
model or executing a tool. It accepts only `list tools` and `list servers` as tasks:

```powershell
.\.venv\Scripts\coding-assistant.exe --connection-check --task "list tools"
.\.venv\Scripts\coding-assistant.exe `
  --connection-check `
  --config .\config\mcp.json `
  --workspace . `
  --task "list servers"
```

`--config` selects an MCP JSON file. `--workspace` overrides `${workspaceRoot}`
for configured servers; otherwise the config loader uses the config directory's
parent. Run from the repository root or provide an explicit config path.

## Groq cloud tasks

Set `GROQ_API_KEY` in the same terminal that launches the CLI. In PowerShell 7+,
masked input keeps the key out of command history:

```powershell
$env:GROQ_API_KEY = Read-Host "Groq API key" -MaskInput
.\.venv\Scripts\coding-assistant.exe --provider groq
```

For a single model-backed task:

```powershell
.\.venv\Scripts\coding-assistant.exe `
  --provider groq `
  --execution-mode confirm `
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
for that configuration's location. Pass `--workspace` with the sample directory.
Do not commit or print the API key.

## Agent-loop integration

Use `--provider groq` (the default) or `--provider ollama` for the shipped adapters.
Ollama requires `OLLAMA_MODEL`; Groq requires `GROQ_API_KEY`, with optional
`GROQ_MODEL`. Provider selection, custom factories, and `--connection-check` are
mutually exclusive.

The CLI owns input, output, execution policy, and MCP connection cleanup. It wraps
the connected MCP client before passing it to the selected agent factory, so both
shipped providers and custom agents using that client receive the same confirm/auto
behavior. The provider interface and `BasicAgentLoop` behavior are unchanged.

Pass a synchronous factory that accepts the connected MCP-client contract and
returns an `AgentLoop` implementation:

```powershell
.\.venv\Scripts\coding-assistant.exe --agent your_agent_module:create_agent
.\.venv\Scripts\coding-assistant.exe `
  --agent your_agent_module:create_agent `
  --execution-mode auto `
  --task "Explain README.md"
```

The factory module must be importable in the active environment. The returned
agent's `run(task)` is an async iterator of the existing contract mappings:

- `text` with `content`: streamed answer text.
- `tool_call` with `name` and `arguments`: the requested action.
- `tool_result` with `name`, `content`, and optional `is_error`: its result.
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
.\.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_execution_policy.py
.\.venv\Scripts\python.exe -m mypy
```

Tests cover interactive commands, streamed results, confirmation, rejection,
automatic execution, failures, EOF/Ctrl+C cleanup, one-shot mode, and agent
factories. An integration test starts two real local stdio MCP servers, calls both
through an injected test agent in automatic mode, and verifies the results.

DeepWiki reads documentation and answers questions about specific public GitHub
repositories. Include a repository in `owner/repo` format in your task, for example:

```text
Use DeepWiki to explain the architecture of modelcontextprotocol/python-sdk.
```

The server name `deepwiki` is not a valid repository name.
