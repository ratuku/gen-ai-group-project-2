# Groq Cloud provider

The Groq adapter implements the existing `ModelProvider` contract without changing
the CLI, agent loop, MCP client, or tool dispatcher. It streams text, assembles
fragmented function calls, preserves tool-call IDs, and sends complete MCP results
back to the cloud model on the next turn.

## Free account and API key

Groq Cloud provides a rate-limited Free plan. A payment method is required only if
you choose to upgrade to a paid tier. Current limits and model availability can
change, so check the official [Groq rate-limit documentation](https://console.groq.com/docs/rate-limits).

1. Create or sign in to a Groq Cloud account.
2. Create an API key in the Groq Console.
3. Store the key only in your environment. Never place it in source code, Git,
   screenshots, logs, or committed configuration files.

In Windows PowerShell:

```powershell
$env:GROQ_API_KEY = "your-key"
```

The variable applies only to the current PowerShell process and its children. This
repository does not contain or load a committed key file.

## Model configuration

The default is `openai/gpt-oss-20b`, a tool-capable model currently listed under
Groq's Free plan limits. Override it when another enabled model is preferred:

```powershell
$env:GROQ_MODEL = "openai/gpt-oss-20b"
```

Model availability is controlled by Groq and may change independently of this
project. A missing or unavailable model produces an actionable CLI error.

## Install and run

Install the project dependencies and the filesystem MCP server from the repository
root:

```powershell
python -m pip install -r requirements-dev.txt
npm.cmd ci
```

Run a single task:

```powershell
coding-assistant `
  --config .\config\mcp.json `
  --workspace . `
  --agent coding_assistant.providers.groq:create_agent `
  --task "List the top-level project files using the filesystem tool."
```

Omit `--task` for the interactive prompt.

The standard `config/mcp.json` connects both the local filesystem server and the
hosted DeepWiki server. It therefore needs internet access in addition to the Groq
API connection. Use a separate MCP configuration containing only local servers when
DeepWiki is not wanted.

## Data and tool-call flow

Conversation messages, MCP tool definitions, and tool results sent back for model
reasoning leave the local machine and are processed by Groq Cloud. Do not submit
secrets or private repository content unless that use is permitted by your team and
Groq's applicable terms.

MCP tools still execute through this application's existing dispatcher. The model
requests a tool; the dispatcher validates its exact name and JSON arguments, invokes
the configured MCP server, and adds the normalized result to conversation history.
Groq does not directly execute the local filesystem tool.

Groq streams tool-call IDs, names, and JSON arguments in fragments. The adapter
assembles and validates a complete object before emitting the provider-neutral
`tool_call` event expected by `BasicAgentLoop`.

## Troubleshooting

- **Missing key:** set `GROQ_API_KEY` in the same terminal used to start the CLI.
- **Authentication failure:** create an active key and replace the environment value.
- **Rate limit:** wait for the Free plan limit to reset, then retry.
- **Model unavailable:** set `GROQ_MODEL` to a tool-capable model enabled for the
  account.
- **Connection failure:** confirm internet access and Groq service availability.
