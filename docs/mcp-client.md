# MCP client

Issue #2 provides the transport-neutral client used by later server-integration
issues. It uses the official MCP Python SDK for stdio and Streamable HTTP transports.

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
`${workspaceRoot}` without exposing unrelated process environment variables.

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
