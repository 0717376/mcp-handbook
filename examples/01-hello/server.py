"""Minimal MCP server: one tool that echoes back whatever it was given."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hello")


@mcp.tool()
def echo(text: str) -> str:
    """Return the input text unchanged."""
    return text


if __name__ == "__main__":
    mcp.run()
