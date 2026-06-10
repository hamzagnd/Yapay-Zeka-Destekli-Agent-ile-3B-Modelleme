"""MCP tools for browsing and searching the local asset catalog."""

from typing import Optional, List
from .. import catalog


def register_tools(mcp, client):

    @mcp.tool()
    async def search_assets(
        query: Optional[str] = None,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        style: Optional[str] = None,
        tags: Optional[str] = None,
        limit: int = 20,
    ) -> str:
        """Search the local asset library catalog.

        Args:
            query: Free-text search against name, id, category, style, and tags
            category: Filter by category (e.g. seating, tables, lighting)
            subcategory: Filter by subcategory (e.g. sofa, desk, floor_lamp)
            style: Filter by style keyword (e.g. industrial, mid-century)
            tags: Comma-separated tags to match (e.g. "leather,wood")
            limit: Max results to return (default 20)
        """
        tag_list = [t.strip() for t in tags.split(",")] if tags else None

        results = catalog.search_assets(
            query=query,
            category=category,
            subcategory=subcategory,
            style=style,
            tags=tag_list,
            limit=limit,
        )

        if not results:
            return "No assets found. Try different search terms or remove filters."

        lines = [f"Found {len(results)} asset(s):\n"]
        for a in results:
            dim = a.get("dimensions_m", {})
            dim_str = (
                f"{dim.get('width', '?')}w x {dim.get('depth', '?')}d x {dim.get('height', '?')}h m"
                if dim else "dimensions unknown"
            )
            style_str = ", ".join(a.get("style", [])) or "—"
            tag_str = ", ".join(a.get("tags", [])) or "—"
            lines.append(
                f"  ID: {a['id']}\n"
                f"  Name: {a['name']}\n"
                f"  Category: {a.get('category')} / {a.get('subcategory')}\n"
                f"  Style: {style_str}\n"
                f"  Tags: {tag_str}\n"
                f"  Dimensions: {dim_str}\n"
                f"  Polys: {a.get('poly_count', '?')}\n"
            )
        lines.append("Use get_asset_info(id) for full details, or import_asset(id) to place it in Blender.")
        return "\n".join(lines)

    @mcp.tool()
    async def list_assets(
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        limit: int = 50,
    ) -> str:
        """List all assets in the catalog, optionally filtered by category.

        Args:
            category: Filter by category (e.g. seating, tables, beds)
            subcategory: Filter by subcategory (e.g. sofa, dining_table)
            limit: Max results (default 50)
        """
        results = catalog.search_assets(
            category=category,
            subcategory=subcategory,
            limit=limit,
        )

        if not results:
            return "No assets found."

        header = f"Assets ({len(results)}"
        if category:
            header += f" in '{category}'"
        if subcategory:
            header += f" / '{subcategory}'"
        header += "):\n"

        lines = [header]
        for a in results:
            lines.append(f"  {a['id']:40s}  {a['name']}")
        return "\n".join(lines)

    @mcp.tool()
    async def get_asset_info(asset_id: str) -> str:
        """Get full details about a single asset.

        Args:
            asset_id: The asset ID from the catalog (e.g. sofa_02_chesterfield)
        """
        asset = catalog.get_asset_by_id(asset_id)
        if not asset:
            return f"Asset '{asset_id}' not found. Use search_assets or list_assets to find valid IDs."

        dim = asset.get("dimensions_m", {})
        textures = asset.get("textures", {})
        slots = asset.get("material_slots", [])

        abs_file = catalog.resolve_file_path(asset["file"])

        lines = [
            f"Asset: {asset['name']}",
            f"  ID:           {asset['id']}",
            f"  Category:     {asset.get('category')} / {asset.get('subcategory')}",
            f"  Style:        {', '.join(asset.get('style', []))}",
            f"  Tags:         {', '.join(asset.get('tags', []))}",
            f"  Poly count:   {asset.get('poly_count', '?')}",
            f"  Resolution:   {asset.get('texture_resolution', '?')}",
            f"  Origin:       {asset.get('origin', '?')}",
            f"  Added:        {asset.get('added_at', '?')}",
        ]

        if dim:
            lines.append(
                f"  Dimensions:   {dim.get('width')}w x {dim.get('depth')}d x {dim.get('height')}h m"
            )

        lines.append(f"  .blend file:  {abs_file}")
        lines.append(f"  File exists:  {'YES' if abs_file.exists() else 'NO — check ASSET_LIBRARY_DIR'}")

        if slots:
            lines.append(f"  Material slots: {', '.join(s['slot'] for s in slots)}")

        if textures:
            lines.append("  Textures:")
            for tex_type, rel_path in textures.items():
                tex_abs = catalog.resolve_file_path(rel_path)
                exists = "ok" if tex_abs.exists() else "missing"
                lines.append(f"    {tex_type}: {rel_path}  [{exists}]")

        return "\n".join(lines)

    @mcp.tool()
    async def list_categories() -> str:
        """List all categories and their subcategories in the asset library."""
        cats = catalog.get_categories()
        if not cats:
            return "No categories found in catalog."

        lines = ["Asset Library Categories:\n"]
        for cat, subs in cats.items():
            lines.append(f"  {cat}:")
            lines.append(f"    {', '.join(subs)}")
        return "\n".join(lines)
