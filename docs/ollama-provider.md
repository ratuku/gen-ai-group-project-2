# Ollama provider

The Ollama adapter implements the existing `ModelProvider` contract without
changing the agent loop. It streams model text, translates Ollama function calls
into provider-neutral tool requests, and sends complete MCP results back to the
model on the next turn.

## Prerequisites

1. Install and start [Ollama](https://ollama.com/download).
2. Pull a model that supports tool calling. For example:

   ```powershell
   ollama pull qwen3
   ```

3. Install this project and its Python dependencies:

   ```powershell
   python -m pip install -r requirements-dev.txt
   npm ci
   ```

`npm ci` is required for the configured filesystem MCP server, not for Ollama
itself. Local Ollama use does not require an API key.

## Configuration

Set the required model name before starting the CLI:

```powershell
$env:OLLAMA_MODEL = "qwen3"
```

The provider uses Ollama's default local endpoint. To select another endpoint,
set the optional host:

```powershell
$env:OLLAMA_HOST = "http://localhost:11434"
```

The provider does not pull models automatically. If the selected model is not
installed, the CLI reports the `ollama pull` command needed to obtain it.

## Run

Submit one task:

```powershell
coding-assistant `
  --agent coding_assistant.providers.ollama:create_agent `
  --task "Explain what this project does in one sentence."
```

Start an interactive session:

```powershell
coding-assistant --agent coding_assistant.providers.ollama:create_agent
```

The standard `config/mcp.json` connects both the local filesystem server and the
hosted DeepWiki server. Therefore, the standard configuration requires network
access even though the selected model runs locally. Use a separate MCP config
containing only local servers when an entirely offline session is required.

## Tool and history translation

MCP definitions use `name`, `description`, and `input_schema`. The adapter maps
these to Ollama function `name`, `description`, and `parameters`. Qualified MCP
names such as `filesystem.read_text_file` are preserved exactly.

The agent owns tool-call IDs, but Ollama's tool-message format associates results
using `tool_name`. When sending history to Ollama, the adapter removes agent-only
IDs, preserves tool order, and serializes the complete normalized MCP result as
JSON. The next Ollama response is translated back into `text` and `tool_call`
events for `BasicAgentLoop`.

## Troubleshooting

- **Could not connect to Ollama:** open the Ollama application or start the
  service, then check `OLLAMA_HOST`.
- **Model is unavailable:** run the `ollama pull <model>` command displayed by
  the CLI.
- **MCP connection failure:** verify Node.js and `npm ci` for the filesystem
  server, and verify internet access for the committed DeepWiki server.
