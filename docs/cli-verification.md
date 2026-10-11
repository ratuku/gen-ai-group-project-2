# Issue #8 CLI verification

Verified on Windows with Python 3.14.6 on October 10, 2026. The branch starts at
`8d71a16`, the merge of the Groq provider. No local GPU was used.

## Automated checks

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_agent_loop.py tests/test_tool_dispatcher.py tests/test_groq_provider.py tests/test_ollama_provider.py tests/test_mcp_client.py tests/test_mcp_config.py
.\.venv\Scripts\python.exe -m pytest tests/test_architecture.py tests/test_filesystem_mcp_windows.py
.\.venv\Scripts\python.exe -m mypy src/coding_assistant tests/test_cli.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Results after the assignment-alignment changes: **125 tests passed**, including
38 CLI cases and real local stdio-server integration. The final layout refinements
were checked with all 38 CLI cases again. Type checking passed for 20 source files. Dependency
and whitespace checks passed. The unrelated RAG test suite was not run.

| Acceptance check | Result |
| --- | --- |
| Console and module launch, help without servers | Passed; exit 0 |
| Blank prompt input, help/server/tool commands, unknown commands | Passed; automated prompt tests inject complete lines |
| Single-task mode and configuration/workspace forwarding | Passed |
| Streamed text, visible tool calls/results, readable failures | Passed |
| Interactive task after an exception or provider error event | Passed |
| `/exit`, `/quit`, `exit`, `quit`, end-of-input | Passed; exit 0 and connections released |
| Ctrl+C at prompt | Passed in a real terminal; exit 130 |
| During-task interruption and cancellation | Automated checks pass with a test client; real server interruption verification recorded below |
| Task/startup errors and invalid arguments | Passed; exit codes 1 and 2 |
| Demo suggestions only in demo modes | Passed |

## Installed CLI and live Groq checks

The installed console executable and `python -m coding_assistant.cli` were checked
from the repository root. Empty and filesystem-only configurations were created
in temporary directories. The filesystem workspace contained only `sample.txt`:

```text
The sample project is named Juniper. Its release color is blue.
```

The following commands passed. `$emptyConfig`, `$filesystemConfig`, and
`$sampleWorkspace` refer to those temporary paths; the filesystem configuration
uses the absolute path to the installed Node filesystem server script.

```powershell
.\.venv\Scripts\coding-assistant.exe --help
.\.venv\Scripts\python.exe -m coding_assistant.cli --connection-demo --config $emptyConfig --task "list tools"
.\.venv\Scripts\coding-assistant.exe --connection-demo --config $emptyConfig --task "list servers"
.\.venv\Scripts\coding-assistant.exe --config $filesystemConfig --workspace $sampleWorkspace --demo-loop --task "inspect workspace"
.\.venv\Scripts\coding-assistant.exe --config $emptyConfig --agent coding_assistant.providers.groq:create_agent --task "Reply with one short greeting."
.\.venv\Scripts\coding-assistant.exe --config $filesystemConfig --workspace $sampleWorkspace --agent coding_assistant.providers.groq:create_agent --task "Read the file at $sampleWorkspace\sample.txt using filesystem.read_text_file. Summarize its project name and release color."
```

Live tests used the default `openai/gpt-oss-20b` model and a locally configured
`GROQ_API_KEY`; the key is not recorded here. Both Groq single-task checks returned
exit 0 and `[Done]`. The filesystem check invoked the MCP tool and identified
Juniper correctly.

Interactive checks were performed in a real Windows terminal:

- Connection demo: `/help`, `/tools`, `list tools`, then `/exit`; task output and
  successful exit were observed.
- Groq with no tools: a short greeting returned `Hello!` and `[Done]`, followed by
  `/quit` and exit 0.
- Groq with filesystem tools: an explicit path to `sample.txt` triggered
  `filesystem.read_text_file`. The tool returned the sample contents; the model
  answered `Project Name: Juniper` and `Release Color: Blue`, followed by `[Done]`.
- Ctrl+C printed `Interrupted. Goodbye.`; the CLI's exit code was checked directly.

The initial attempt to pipe interactive input failed because prompt-toolkit could
not find a Windows console. Interactive tests were rerun successfully in a real
terminal. Piped interactive input remains unsupported; use `--task` for automation.

No Groq provider failure was reproduced. In particular, qualified MCP tool names
were accepted by the live service. These smoke checks do not cover truncated Groq
streams or constitute the later two-model evaluation in issue #14.

The command and lifecycle tests pass. The user reported an input-editing problem
in the initially launched terminal, then confirmed on October 10 that the input
problem was resolved. An isolated Windows console probe also verified Backspace;
this is separate from the tests that inject complete prompt lines. The issue
should close only after the CLI changes are reviewed and merged.

## Assignment-aligned CLI

Juniper now uses Groq for a normal launch, supports `--provider groq` and
`--provider ollama`, and preserves custom factories through `--agent`. Discovery
without an LLM is explicitly selected with `--connection-demo`.

The terminal shows a branded session panel containing workspace, provider, model,
server count, version, and execution behavior. Tool arguments and results are
visible in separate panels; model text continues to stream. Captured output uses
plain labels, and `NO_COLOR` disables terminal styling.

A live `--provider groq` coding task created `greet.py` in the sample workspace
using `filesystem.write_file`, inspected it using filesystem listing/read tools,
and completed successfully. Running the generated file separately printed
`Hello, Juniper!`. The CLI's easier provider selection uses the existing adapters;
no model/provider logic was added to the main agent loop.

This update covers the CLI scope only. Confirmation mode, shell-command tools,
custom RAG retrieval, advanced RAG, and final evaluation/deliverables remain
separate project work. The startup panel explicitly identifies the current
automatic execution behavior.

## Follow-up review

The user-facing interactive launcher now uses the normal configuration with both
filesystem and DeepWiki. The earlier sample-task launcher remains a filesystem-only
test. A fresh regression run passed all 125 tests, type checking passed for 20
source files, and dependency and whitespace checks passed.

A live Groq task using the normal configuration connected to filesystem (14 tools)
and DeepWiki (3 tools), called `deepwiki.read_wiki_structure` with
`repoName="modelcontextprotocol/python-sdk"`, returned documentation topics, and
finished with `[Done]` and exit 0:

```powershell
.\.venv\Scripts\coding-assistant.exe --config .\config\mcp.json `
  --workspace $sampleWorkspace --provider groq `
  --task "Use deepwiki.read_wiki_structure with repoName modelcontextprotocol/python-sdk. Report three documentation topics from the returned result. Do not write any files."
```

The earlier user-reported DeepWiki failure used `repoName="deepwiki"`, which the
server rejected because it requires a repository identifier. That tool-argument
failure does not indicate a connection failure, and this successful explicit
request does not establish that every model-generated argument will be correct.

This verification record accompanies the issue #8 CLI changes. The issue should
remain open until the reviewed changes are merged.

The review found and fixed argument validation for malformed `--agent` values.
Missing/empty components or extra separators now produce a usage error and exit 2;
module-import and factory-startup failures remain exit 1. Four regression cases
were added to the CLI suite.
After these fixes, all 42 CLI cases passed again and type checking passed for
20 source files. Whitespace validation passed.

A bounded Windows console harness ran a waiting test agent through the actual CLI
with the real filesystem server connected. It sent a native console Ctrl+C signal
during the active task and observed CLI exit 130, an empty connection list after
cleanup, and filesystem-process exit 0. This verifies local interruption and
process cleanup; the waiting agent did not use Groq or DeepWiki. The harness
invocation was `.\.venv\Scripts\python.exe $interruptProbe` in a separate Windows
console. Its recorded outcome was:

```json
{"exit_code": 130, "signal_sent": [true], "server_exit_codes": [0], "connections_released": true, "passed": true}
```
