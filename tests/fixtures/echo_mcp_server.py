"""Small stdio MCP server used only by the client integration test."""

from mcp.server import MCPServer

mcp = MCPServer("issue-2-test-server")


@mcp.tool()
def echo(value: str) -> str:
    """Return the supplied value."""

    return value


if __name__ == "__main__":
    mcp.run(transport="stdio")
