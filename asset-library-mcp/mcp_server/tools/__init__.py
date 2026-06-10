"""MCP tools for the Asset Library."""

from . import catalog_tools
from . import import_tools
from . import interior_design_tools
from . import catalog_management_tools


def register_all_tools(mcp, client):
    catalog_tools.register_tools(mcp, client)
    import_tools.register_tools(mcp, client)
    interior_design_tools.register_tools(mcp, client)
    catalog_management_tools.register_tools(mcp, client)
