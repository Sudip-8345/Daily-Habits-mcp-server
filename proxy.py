from fastmcp import FastMCP

mcp = FastMCP.as_proxy(
    "https://daily-habits-mcp.fastmcp.app/mcp",
    name="DailyHabitsAgent",
)

if __name__ == "__main__":
    # Claude Desktop connects to MCP servers over stdio.
    # IMPORTANT: when using stdio, keep stdout reserved for MCP protocol.
    mcp.run(transport="stdio", show_banner=False)
