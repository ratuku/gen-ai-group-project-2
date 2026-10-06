# CLI Coding Assistant

This project builds an autonomous command-line coding assistant with model-provider
abstraction, dynamically discovered MCP tools, and a custom RAG MCP server.

## Development setup

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
pytest
mypy
```

The provisional vertical-slice interfaces are exported from
`coding_assistant.contracts`. The repository and runtime boundaries are documented in
[docs/architecture.md](docs/architecture.md). Concrete implementations and stronger
domain models will be extracted in later tickets after the end-to-end flow is validated.

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
