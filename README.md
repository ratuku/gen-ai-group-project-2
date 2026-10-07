# CLI Coding Assistant

This project builds an autonomous command-line coding assistant with model-provider
abstraction, dynamically discovered MCP tools, and a custom RAG MCP server.

## Development setup

Python 3.11 or newer is required. The Windows filesystem MCP demo also requires
Node.js with `npx` available on `PATH`. The first run downloads the pinned official
filesystem server package.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
pytest
mypy
```

## Filesystem MCP smoke test

The committed MCP configuration starts the official filesystem server through
`cmd /c npx` and grants it access only to this repository. Run the end-to-end
smoke test from the repository root:

```powershell
python scripts/smoke_filesystem_mcp.py
```

The script displays the dynamically discovered `filesystem.*` tools, creates a
temporary directory in the repository, writes and reads a file through MCP, and
confirms that the server rejects access to the parent directory. Each successful
step prints `PASS`; any failure exits with a nonzero status. Temporary files are
removed even when a step fails.

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
