"""MCP tools for importing local .blend assets into the active Blender scene."""

from typing import List, Optional
from .. import catalog


def register_tools(mcp, client):

    @mcp.tool()
    async def import_asset(
        asset_id: str,
        location: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        scale: float = 1.0,
        name: Optional[str] = None,
    ) -> str:
        """Import a local .blend asset into the current Blender scene.

        Requires the Asset Library Blender addon to be running (port 8766).
        Press N in the 3D viewport → Asset Library tab → Start Server.

        Args:
            asset_id: Asset ID from the catalog (e.g. sofa_02_chesterfield)
            location: [x, y, z] placement in meters (default [0, 0, 0])
            rotation: [x, y, z] rotation in degrees (default [0, 0, 0])
            scale: Uniform scale factor (default 1.0)
            name: Override name for the imported object in Blender
        """
        asset = catalog.get_asset_by_id(asset_id)
        if not asset:
            return (
                f"Asset '{asset_id}' not found in catalog. "
                "Use search_assets or list_assets to find valid IDs."
            )

        abs_file = catalog.resolve_file_path(asset["file"])
        if not abs_file.exists():
            return (
                f"File not found: {abs_file}\n"
                "Make sure ASSET_LIBRARY_DIR is set correctly and the .blend file exists."
            )

        loc = location or [0.0, 0.0, 0.0]
        rot = rotation or [0.0, 0.0, 0.0]

        result = await client.execute(
            "import_blend_asset",
            {
                "file_path": str(abs_file),
                "location": loc,
                "rotation": rot,
                "scale": scale,
                "name": name or asset["name"],
            },
        )

        imported = result.get("imported_objects", [])
        obj_name = result.get("name", asset_id)
        obj_loc = result.get("location", loc)

        lines = [
            f"Imported '{asset['name']}' as '{obj_name}'",
            f"  Location: ({obj_loc[0]:.3f}, {obj_loc[1]:.3f}, {obj_loc[2]:.3f})",
            f"  Objects:  {', '.join(imported)}",
        ]
        if len(imported) > 1:
            lines.append(f"  (root object: {obj_name})")
        return "\n".join(lines)

    @mcp.tool()
    async def check_asset_library_connection() -> str:
        """Check if the Asset Library Blender addon server is running.

        The addon listens on port 8766 (separate from the Orchestrator on 8765).
        Start it in Blender: press N in 3D viewport → Asset Library tab → Start Server.
        """
        try:
            healthy = await client.health_check()
            if healthy:
                return (
                    "Asset Library addon is running and responsive (port 8766).\n"
                    "You can use import_asset to bring .blend assets into the scene."
                )
            return (
                "Asset Library addon is NOT responding on port 8766.\n"
                "In Blender: press N in the 3D viewport → 'Asset Library' tab → 'Start Server'."
            )
        except Exception as e:
            return f"Connection error: {e}"
