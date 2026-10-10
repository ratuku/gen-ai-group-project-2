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

Results: **112 + 7 = 119 tests passed**, including 32 CLI cases and real local
stdio-server integration. Type checking passed for 19 source files. Dependency
and whitespace checks passed. The unrelated RAG test suite was not run.

| Acceptance check | Result |
| --- | --- |
| Console and module launch, help without servers | Passed; exit 0 |
| Blank prompt input, help/server/tool commands, unknown commands | Passed |
| Single-task mode and configuration/workspace forwarding | Passed |
| Streamed text, visible tool calls/results, readable failures | Passed |
| Interactive task after an exception or provider error event | Passed |
| `/exit`, `/quit`, `exit`, `quit`, end-of-input | Passed; exit 0 and connections released |
| Ctrl+C at prompt and during a task; task cancellation | Passed; interruption returns 130 and cleanup tests pass |
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
.\.venv\Scripts\python.exe -m coding_assistant.cli --config $emptyConfig --task "list tools"
.\.venv\Scripts\coding-assistant.exe --config $emptyConfig --task "list servers"
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

All issue #8 acceptance checks passed. The issue should close only after the CLI
changes are reviewed and merged.
