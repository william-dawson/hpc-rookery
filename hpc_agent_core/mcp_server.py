"""The one place that imports the MCP SDK's server class.

Every machine repo imports MCPServer from here, never from `mcp` directly,
and none of them declare "mcp" as their own dependency — only hpc-agent-core
does. mcp 2.0.0 renamed mcp.server.fastmcp.FastMCP to
mcp.server.mcpserver.MCPServer with no deprecation window, which broke every
consumer overnight because each one imported it independently and pinned (or
didn't pin) the SDK on its own. If the SDK's API surface moves again, this
file is the only one that needs to change.
"""
from mcp.server.mcpserver import MCPServer

__all__ = ["MCPServer"]
