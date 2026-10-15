# Juniper - CLI Coding Assistant

## Submission report

**[Open PROJECT_REPORT.pdf](PROJECT_REPORT.pdf)**

The assignment's PDF report is in the repository's top-level folder. It contains
the system description and design decisions (page 1), two-model comparison
(page 2), advanced RAG insights (page 3), reflection (page 4), original planning
architecture (page 5), and updated architecture with explanations (page 6).
State and sequence diagrams follow on pages 7-10, including three complete
operations across inspection, bug repair, and a documentation-assisted feature.
Supporting files under `evaluations/` are test records, not additional submission
reports. See the [submission guide](output/pdf/README.md) for supporting evidence and current
validation limits.

**[Submission checklist](SUBMISSION_CHECKLIST.md)** |
**[Architecture and workflow diagrams](docs/diagrams.md)** |
**[Measured RAG comparison](evaluations/rag_evaluation/README.md)**

For reproducible end-to-end tasks and a two-model Groq comparison, see
[Model comparison](evaluations/model_comparison/README.md).

This project builds an autonomous command-line coding assistant with model-provider
abstraction, dynamically discovered MCP tools, and a custom RAG MCP server.

## Setup from a fresh checkout

Python 3.11 or newer is required. The Windows filesystem MCP integration also requires
Node.js available on `PATH`. Install the pinned official filesystem server with
`npm ci` before running the CLI or Windows regression tests.

Install Python 3.11+ and Node.js, then open PowerShell:

```powershell
git clone https://github.com/ratuku/gen-ai-group-project-2.git
Set-Location .\gen-ai-group-project-2
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm.cmd ci
.\.venv\Scripts\python.exe -m rag_server.prepare
.\.venv\Scripts\python.exe -m rag_server.index
.\.venv\Scripts\coding-assistant.exe --connection-check --task "list tools"
```

If you already have the project, open PowerShell in the folder containing this
README and start at environment creation. Run commands from that folder: a relative
`.venv` path will not work from your user home directory. No activation is required.
`requirements-dev.txt` installs the project, RAG extras, and development tools;
for runtime-only installation use `python -m pip install -r requirements.txt -e ".[rag]"`.

The first RAG preparation downloads two local model dependencies as needed
(the embedding model during preparation, the reranker on its first query).
Preparation and indexing run once; repeat them only after changing the corpus or
embedding settings. The resulting store is ignored by Git, so a fresh checkout
must build it. Inference uses the CPU and requires no paid API. DeepWiki and
initial model downloads require internet access.

For an existing Windows `GROQ_API_KEY` environment variable, load it into this
PowerShell session without printing it, then launch Juniper:

```powershell
if (-not $env:GROQ_API_KEY) {
    $env:GROQ_API_KEY = [Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'User')
}
if (-not $env:GROQ_API_KEY) {
    $env:GROQ_API_KEY = [Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'Machine')
}
.\.venv\Scripts\coding-assistant.exe --provider groq
```

Set the variable in Windows Environment Variables first if it is missing.
For Ollama, start the local service, pull a tool-capable model, and set
`OLLAMA_MODEL` as described below. Cloud limits are controlled by Groq; the
project does not require a paid upgrade. [Free-tier testing notes](evaluations/model_comparison/FREE_TIER_TESTING_NOTES.md)
explain pacing and resumable coding runs.

Verify the implementation without cloud calls:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m mypy
```

## macOS Python compatibility

Use Python 3.12 for the demo environment. Python 3.15 currently has no compatible
ONNX Runtime macOS wheel, which prevents Chroma installation. Pip may report this
as a dependency conflict across several Chroma versions; upgrading Chroma alone
will not resolve the missing wheel.

With Python 3.12 installed, create a fresh environment from the repository root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
npm ci
```

If `.venv` was created with another Python version, preserve or remove that old
environment before creating the new one. Activating it does not change its Python
version. `requirements.txt` installs the application and RAG dependencies declared
in `pyproject.toml`; `requirements-dev.txt` includes it and adds pytest and mypy.
For runtime-only use, install with `python -m pip install -r requirements.txt`.

## Basic CLI

```sh
coding-assistant --help
coding-assistant --provider groq
coding-assistant --provider groq --task "List the top-level project files using the filesystem tool."
coding-assistant --provider groq --execution-mode auto --task "List the top-level project files using the filesystem tool."
coding-assistant --connection-check --task "list tools"
```

Install the project and run `npm ci` first, as shown above. Use `/servers`, `/tools`,
`/help`, and `/exit` at the prompt. The default mode runs the Groq-backed agent;
set `GROQ_API_KEY` before launching it. `--provider ollama` selects the local provider
after setting `OLLAMA_MODEL`. `--connection-check` inspects MCP connections and
tool discovery without an LLM or tool execution. Tool calls require confirmation
by default; pass `--execution-mode auto` only when automatic execution is intended.
See [CLI usage and agent integration](docs/cli.md) and
[Basic agent loop](docs/agent-loop.md) for execution behavior and options. See
[Ollama provider](docs/ollama-provider.md) for local model setup and
[Groq Cloud provider](docs/groq-provider.md) for cloud model setup and live usage.

## Run Python scripts and tests

The additional local `checks` MCP server exposes `checks.run_python_check`.
Ask Juniper to run a trusted workspace script or pytest target after editing:

```text
Run tests/test_sample.py with checks.run_python_check in pytest mode, show the
result, and fix the implementation if the tests fail.
```

Tool arguments are `path`, `mode` (`script` or `pytest`), and `timeout_seconds`
(1-60). It uses the project interpreter without a shell, validates the target
inside the workspace, omits credential-like environment variables, and returns
the real exit status and up to 16,000 bytes of combined output. Confirmation
mode asks before executing; auto mode permits validated calls automatically.
Run trusted code: the subprocess has your account's permissions and is not an
OS sandbox. The agent's automatic syntax check is separate and does not execute
the edited code. Historical model-comparison scores predate this extra server.

## Ollama provider

Install and start Ollama, pull a tool-capable model, and select it through the
environment before launching the existing agent loop:

```powershell
ollama pull qwen3
$env:OLLAMA_MODEL = "qwen3"
coding-assistant --provider ollama
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
coding-assistant --provider groq
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

The shared streaming interfaces are exported from `coding_assistant.contracts`.
The final repository and runtime boundaries are documented in
[docs/architecture.md](docs/architecture.md), with
[state and sequence diagrams](docs/diagrams.md).

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
the output contract.

Step 2 stores those embeddings in Chroma and exposes `rag.search_docs` through MCP.
Run `python -m rag_server.index` after preparation. The tool returns original
snippets with source filenames, PDF pages, chunk IDs, and similarity scores.
See [Chroma storage and retrieval](docs/rag-retrieval.md) for setup, tool options,
index updates, tests, and retrieval limitations.

## Advanced RAG retrieval

`rag.search_docs` now reranks cosine candidates with a local cross-encoder by
default. Use `mode="cosine"` for the original baseline. No re-indexing is needed.
Compare both modes through the real MCP server with:

```sh
python -m rag_server.compare --query "How do I register a tool on a FastMCP server?"
```

See [Reranking and baseline comparison](docs/rag-reranking.md) for configuration,
model downloads, score interpretation, tests, and limitations.
