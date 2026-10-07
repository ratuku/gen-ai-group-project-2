# MCP client

Issue #2 provides the transport-neutral client used by later server-integration
issues. It uses the official MCP Python SDK for stdio and Streamable HTTP transports.

## Filesystem server

`config/mcp.json` includes the official filesystem MCP server for the Windows
demo. It is launched directly with `node` and pinned to version `2026.8.31`. Its only
allowed directory is `${workspaceRoot}`, which the configuration loader expands
to the repository root. The server therefore cannot read or modify sibling or
parent directories.

Node.js must be available on `PATH`; install the server first with `npm ci`. From the repository root, verify
the real server and client together with:

```powershell
python scripts/smoke_filesystem_mcp.py
```

The smoke test discovers the server's tools, exercises directory listing plus
file writing and reading, verifies the access boundary, and removes its temporary
directory afterward.

## Configuration

Servers use the conventional `mcpServers` JSON object:

```json
{
  "mcpServers": {
    "local-example": {
      "command": "example-command",
      "args": ["--root", "${workspaceRoot}"],
      "env": {},
      "timeoutSeconds": 60
    },
    "remote-example": {
      "url": "https://example.com/mcp",
      "timeoutSeconds": 60
    }
  }
}
```

The loader validates that each server defines exactly one transport and expands
`${workspaceRoot}` and `${configDir}` without exposing unrelated process environment
variables. `${configDir}` is the directory containing the JSON configuration, so
the installed server can be located independently of the allowed workspace.
Launching the JavaScript entry point directly avoids `cmd.exe` and `npx.cmd`
parsing of workspace characters such as `&`, `%`, and `^`.

## Usage

```python
from coding_assistant.config import load_mcp_config
from coding_assistant.mcp import MCPClient

config = load_mcp_config("config/mcp.json")

async with MCPClient(config.servers) as client:
    tools = await client.list_tools()
    result = await client.call_tool(
        "local-example.example_tool",
        {"input": "example value"},
    )
```

The asynchronous context manager closes subprocesses and HTTP sessions even when an
operation fails.

## Discovery and routing

`MCPClient.list_tools()` connects configured servers, follows tool-list pagination,
and returns provider-neutral mappings. Tool names are qualified as
`server_name.tool_name`; this prevents collisions and gives `call_tool()` the routing
information it needs. Literal `%` and `.` characters inside either name are
percent-escaped, so the qualified name remains unique even when names contain the
separator.

Tool failures returned by a server remain normal `tool_result` payloads with
`is_error=true`. Connection, discovery, and protocol failures raise `MCPClientError`.
Because MCP transports use nested asynchronous contexts, individual connections must
be closed in reverse connection order. `disconnect_all()` handles that ordering and
continues attempting cleanup if one server fails to close.
