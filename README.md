# CLI Coding Assistant

This project builds an autonomous command-line coding assistant with model-provider
abstraction, dynamically discovered MCP tools, and a custom RAG MCP server.

## Development setup

Python 3.11 or newer is required. The Windows filesystem MCP demo also requires
Node.js available on `PATH`. Install the pinned official filesystem server with
`npm ci` before running the demo or Windows regression tests.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
npm ci
pytest
mypy
```

## Basic CLI

```sh
coding-assistant --help
coding-assistant
coding-assistant --task "list tools"
coding-assistant --demo-loop --task "inspect workspace"
```

Install the project and run `npm ci` first, as shown above. Use `/servers`, `/tools`,
`/help`, and `/exit` at the prompt. The default mode demonstrates live MCP connections
and tool discovery. `--demo-loop` exercises the stateful agent loop with a clearly
labeled scripted provider and real filesystem calls. Live model-backed coding
tasks use the Ollama provider wired through `--agent`.
See [CLI demo and agent integration](docs/cli.md) and
[Basic agent loop](docs/agent-loop.md) for options and demo commands. See
[Ollama provider](docs/ollama-provider.md) for local model setup and
[Groq Cloud provider](docs/groq-provider.md) for cloud model setup and live usage.

## Ollama provider

Install and start Ollama, pull a tool-capable model, and select it through the
environment before launching the existing agent loop:

```powershell
ollama pull qwen3
$env:OLLAMA_MODEL = "qwen3"
coding-assistant --agent coding_assistant.providers.ollama:create_agent
```

The adapter streams text and supports MCP tool calls through the provider-neutral
agent interface. It does not download models automatically. `OLLAMA_HOST` may be
set when the Ollama service is not available at its default local endpoint.

## Groq Cloud provider

Create a Groq Cloud API key, keep it out of Git, and select the cloud adapter
through the same agent interface:

```powershell
$env:GROQ_API_KEY = "your-key"
$env:GROQ_MODEL = "openai/gpt-oss-20b"  # Optional; this is the default.
coding-assistant --agent coding_assistant.providers.groq:create_agent
```

The provider streams responses and preserves MCP tool calls and results across
model turns. Prompts, tool definitions, and returned tool results are sent to Groq
Cloud. See [Groq Cloud provider](docs/groq-provider.md) for setup, security guidance,
and troubleshooting.

## Filesystem MCP smoke test

The committed MCP configuration starts the official filesystem server through
`node` directly and grants it access only to this repository. Run the end-to-end
smoke test from the repository root:

```powershell
python scripts/smoke_filesystem_mcp.py
```

The script displays the dynamically discovered `filesystem.*` tools, creates a
temporary directory in the repository, writes and reads a file through MCP, and
confirms that the server rejects access to the parent directory. Each successful
step prints `PASS`; any failure exits with a nonzero status. Temporary files are
removed even when a step fails. Windows regression tests in `pytest` also exercise
read/write/list operations in `R&D`, `repo%USERNAME%`, `repo^name`, and a path with
spaces, and verify that outside read/write/list operations remain denied.

## External-resource MCP smoke test

The committed MCP configuration also connects the hosted DeepWiki server over
Streamable HTTP. With internet access, verify tool discovery and retrieval of useful
external information from a public GitHub repository with:

```powershell
python scripts/smoke_external_mcp.py
```

The smoke test asks DeepWiki a concrete question about the public MCP Python SDK
repository, prints the answer, and exits with a nonzero status if discovery or the
external request fails. Do not send secrets or private repository information to
the external service.

The provisional vertical-slice interfaces are exported from
`coding_assistant.contracts`. The repository and runtime boundaries are documented in
[docs/architecture.md](docs/architecture.md). Concrete implementations and stronger
domain models will be extracted in later tickets after the end-to-end flow is validated.

The concrete multi-server MCP client and its configuration format are documented in
[docs/mcp-client.md](docs/mcp-client.md). Individual server configurations are added by
the filesystem, external-resource, and custom-RAG integration issues.

## Learning outcomes

By completing this project, we will:

Design and implement an autonomous agentic loop that reasons, acts, observes results, and iterates toward task completion.
Implement LLM tool calling for file operations, command execution, and information retrieval.
Build an MCP client that dynamically connects to and loads tools from multiple MCP servers.
Develop a custom RAG MCP server with document processing, embeddings, vector storage, and retrieval.
Apply an advanced RAG technique. 
Implement model-provider abstraction supporting Ollama and at least one cloud-based LLM provider.
Build an interactive CLI with streaming responses, tool-call visibility, and confirmation/auto-execution modes.
Design and document system architecture using state and sequence diagrams.
Evaluate AI system performance by comparing LLMs and analyzing the effectiveness of the RAG approach.
Collaboratively develop and document a complete AI application using Git and GitHub.

## RAG document preparation

Step 1 loads documents, splits token-budgeted chunks, and generates local semantic
embeddings. Install with `python -m pip install -e ".[rag]"`, then run
`python -m rag_server.prepare`. See [RAG preparation](docs/rag-preparation.md) for
the output contract and remaining storage/retrieval stages.
