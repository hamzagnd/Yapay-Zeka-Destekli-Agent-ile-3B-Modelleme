"""MCP Server for the local asset library."""

from mcp.server.fastmcp import FastMCP
from .blender_client import BlenderClient
from .tools import register_all_tools

mcp = FastMCP("asset-library-mcp")

client = BlenderClient(host="localhost", port=8766)

register_all_tools(mcp, client)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
