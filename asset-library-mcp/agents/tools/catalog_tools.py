"""Catalog tools for agno agents — wraps mcp_server/catalog.py directly.

v2 additions: search by semantic_tag/room_type, list_companions, container details.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_server import catalog


def search_catalog(
    query: str = None,
    subcategory: str = None,
    style: str = None,
    room_type: str = None,
    semantic_tag: str = None,
    limit: int = 10,
) -> str:
    """Search the asset catalog for furniture.

    Prefer ROOM_TYPE for room-aware filtering (e.g. room_type='office' returns assets
    tagged for office use). Use SEMANTIC_TAG for thematic intent (e.g. 'work', 'cozy').

    Args:
        query:        Free-text search (name, tags, semantic_tags, room_types)
        subcategory:  e.g. 'desk', 'sofa', 'armchair', 'coffee_table', 'floor_lamp'
        style:        e.g. 'industrial', 'classic', 'mid-century', 'modern'
        room_type:    e.g. 'office', 'living_room', 'bedroom', 'kitchen'
        semantic_tag: e.g. 'work', 'rest', 'cozy', 'minimal'
        limit:        Max results to return
    """
    # Try with all filters first, then progressively relax them so the coach
    # never incorrectly reports an asset as missing just because room_type or
    # style doesn't match — mirrors the find_asset_for_slot fallback logic.
    results = catalog.search_assets(
        query=query,
        subcategory=subcategory,
        style=style,
        room_type=room_type,
        semantic_tag=semantic_tag,
        is_container_flag=False,
        limit=limit,
    )
    # Fallback 1: drop style
    if not results and style:
        results = catalog.search_assets(
            query=query, subcategory=subcategory,
            room_type=room_type, semantic_tag=semantic_tag,
            is_container_flag=False, limit=limit,
        )
    # Fallback 2: drop room_type (assets with empty room_types list = allowed everywhere)
    if not results and room_type:
        results = catalog.search_assets(
            query=query, subcategory=subcategory,
            semantic_tag=semantic_tag,
            is_container_flag=False, limit=limit,
        )
        # Keep only assets that are genuinely usable in any room (empty room_types)
        # OR the ones the caller explicitly asked for by subcategory/query
        if results and room_type:
            from mcp_server.tools.interior_design_tools import asset_allowed_in_room
            filtered = [a for a in results if asset_allowed_in_room(a, room_type)]
            if filtered:
                results = filtered
            # else: keep all results and note the room mismatch in output

    if not results:
        return (
            f"No assets found for subcategory={subcategory!r} room_type={room_type!r}. "
            "This subcategory has no catalog entries yet — add a model with add_asset.py."
        )
    lines = [f"Found {len(results)} asset(s):"]
    for a in results:
        dim = a.get("dimensions_m", {})
        rt = a.get("room_types", [])
        lines.append(
            f"  ID: {a['id']}"
            f"  |  {a['name']}"
            f"  |  {a.get('category')}/{a.get('subcategory')}"
            f"  |  {dim.get('width','?')}w × {dim.get('depth','?')}d × {dim.get('height','?')}h m"
            f"  |  rooms: {','.join(rt) if rt else 'all'}"
            f"  |  style: {', '.join(a.get('style', []))}"
        )
    return "\n".join(lines)


def get_asset_details(asset_id: str) -> str:
    """Get full details for a specific asset by ID."""
    asset = catalog.get_asset_by_id(asset_id)
    if not asset:
        return f"Asset '{asset_id}' not found. Use search_catalog to find valid IDs."
    dim = asset.get("dimensions_m", {})
    abs_file = catalog.resolve_file_path(asset["file"])
    fp = catalog.get_footprint(asset)
    fwd = catalog.get_forward_axis(asset)
    facing = catalog.get_facing_correction_z(asset)
    return (
        f"ID:            {asset['id']}\n"
        f"Name:          {asset['name']}\n"
        f"Category:      {asset.get('category')}/{asset.get('subcategory')}\n"
        f"Room types:    {', '.join(asset.get('room_types', [])) or '-'}\n"
        f"Semantic tags: {', '.join(asset.get('semantic_tags', [])) or '-'}\n"
        f"Compatible:    {', '.join(asset.get('compatible_with', [])) or '-'}\n"
        f"Style:         {', '.join(asset.get('style', []))}\n"
        f"Tags:          {', '.join(asset.get('tags', []))}\n"
        f"Dimensions:    {dim.get('width')}w × {dim.get('depth')}d × {dim.get('height')}h m\n"
        f"Footprint:     {fp['width_m']}w × {fp['depth_m']}d  |  front clr: {fp['clearance_front_m']}m  |  side clr: {fp['clearance_sides_m']}m\n"
        f"Forward axis:  {fwd}  (facing_correction_z = {facing}°)\n"
        f"Is container:  {catalog.is_container(asset)}\n"
        f"File:          {abs_file}\n"
        f"Exists:        {abs_file.exists()}"
    )


def list_all_categories() -> str:
    """List all available furniture categories and subcategories in the catalog."""
    cats = catalog.get_categories()
    if not cats:
        return "No categories found."
    lines = ["Available furniture categories:"]
    for cat_name, subs in cats.items():
        lines.append(f"  {cat_name}: {', '.join(subs)}")
    return "\n".join(lines)


def list_companions(asset_id: str) -> str:
    """List companion assets that pair well with the given asset.

    Uses the asset's `compatible_with` field. For a desk this typically returns
    office_chair candidates; for a sofa it returns coffee_table candidates, etc.

    Args:
        asset_id: The exact asset ID from the catalog (e.g. 'desk_metal_industrial_01')
    """
    base = catalog.get_asset_by_id(asset_id)
    if not base:
        return f"Asset '{asset_id}' not found."
    companions = catalog.list_companions(asset_id)
    if not companions:
        compat = base.get("compatible_with", [])
        if not compat:
            return f"Asset '{asset_id}' has no compatible_with list defined."
        return f"Asset '{asset_id}' lists {compat} as compatible, but no matching catalog assets were found."
    lines = [f"Companions for '{base['name']}' (compatible_with={base.get('compatible_with', [])}):"]
    for a in companions:
        lines.append(f"  {a['id']}  |  {a['name']}  |  {a.get('category')}/{a.get('subcategory')}")
    return "\n".join(lines)


def list_house_assets() -> str:
    """List all container/house assets available in the catalog."""
    results = catalog.search_assets(is_container_flag=True)
    if not results:
        return "No container/house assets found in catalog."
    lines = ["Available house/architectural models:"]
    for a in results:
        rooms = a.get("rooms", [])
        room_summary = ", ".join(r["room_name"] for r in rooms) if rooms else "no rooms defined"
        abs_file = catalog.resolve_file_path(a["file"])
        bbox = catalog.get_interior_bbox(a)
        interior = ""
        if bbox:
            interior = (
                f"\n  Interior bbox (local): "
                f"x[{bbox['min'][0]}..{bbox['max'][0]}]  "
                f"y[{bbox['min'][1]}..{bbox['max'][1]}]  "
                f"z[{bbox['min'][2]}..{bbox['max'][2]}]"
            )
        lines.append(
            f"  ID: {a['id']}\n"
            f"  Name: {a['name']}\n"
            f"  File: {abs_file}\n"
            f"  Rooms: {room_summary}"
            f"{interior}\n"
        )
    return "\n".join(lines)


def list_house_rooms(house_id: str) -> str:
    """List all rooms defined for a specific container asset.

    Args:
        house_id: The asset ID of the house (e.g. 'arch_res_modern_2f_01')
    """
    asset = catalog.get_asset_by_id(house_id)
    if not asset:
        return f"House '{house_id}' not found. Use list_house_assets() to see available houses."

    rooms = asset.get("rooms", [])
    if not rooms:
        return (
            f"House '{house_id}' has no rooms defined yet.\n"
            f"Add a 'rooms' array to Catalog.json for this asset."
        )

    lines = [f"Rooms in '{asset['name']}':"]
    for r in rooms:
        offset = r.get("origin_offset_m", [0, 0, 0])
        dim = r.get("dimensions_m", {})
        bbox = r.get("interior_bbox_local")
        bbox_str = ""
        if bbox:
            bbox_str = (
                f"\n  interior_bbox_local: "
                f"x[{bbox['min'][0]}..{bbox['max'][0]}]  "
                f"y[{bbox['min'][1]}..{bbox['max'][1]}]  "
                f"z[{bbox['min'][2]}..{bbox['max'][2]}]"
            )
        lines.append(
            f"  room_id: {r['room_id']}\n"
            f"  name: {r['room_name']}  (floor {r.get('floor', 1)})\n"
            f"  room_type: {r.get('room_type', '?')}\n"
            f"  origin_offset_m: {offset}\n"
            f"  dimensions: {dim.get('width','?')}w × {dim.get('depth','?')}d × {dim.get('height','?')}h m"
            f"{bbox_str}\n"
        )
    return "\n".join(lines)


def get_house_room(house_id: str, room_id: str) -> dict:
    """Return raw room metadata dict for a specific house+room (internal helper)."""
    asset = catalog.get_asset_by_id(house_id)
    if not asset:
        return {}
    for r in asset.get("rooms", []):
        if r["room_id"] == room_id:
            return r
    return {}


def get_room_preset(room_type: str) -> str:
    """Get the default furniture slots for a room type.

    Args:
        room_type: living_room | bedroom | office | dining_room | kitchen | bathroom
    """
    from mcp_server.tools.interior_design_tools import ROOM_PRESETS
    preset = ROOM_PRESETS.get(room_type.lower().replace(" ", "_"))
    if not preset:
        avail = ", ".join(ROOM_PRESETS.keys())
        return f"Unknown room type '{room_type}'. Available: {avail}"
    lines = [f"Default furniture slots for '{room_type}':"]
    for slot in preset:
        opt = " (optional)" if slot.get("optional") else " (required)"
        fb = f", fallback={slot['fallback']}" if slot.get("fallback") else ""
        face = f"  face={slot['face']}" if slot.get("face") else ""
        lines.append(
            f"  slot={slot['slot']:20s}  subcategory={slot['subcategory']:20s}"
            f"  placement={slot['placement']:30s}{face}  rot_z={slot.get('rot_z',0)}{opt}{fb}"
        )
    return "\n".join(lines)
