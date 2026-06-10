"""Interior design tools — create a room and furnish it from the local catalog.

Everything runs through the Asset Library addon on port 8766.
Actions used:
  create_room         → floor + 4 walls (bpy)
  import_blend_asset  → appends .blend asset at a given location/rotation
  list_scene_objects  → returns all objects for the summary

Coordinate system:
  Origin at room floor-center.
  X = west(−) / east(+),  Y = south(−) / north(+),  Z = up.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .. import catalog as cat


# ---------------------------------------------------------------------------
# Furniture placement presets  (per room type)
#
#   slot         – unique name used for cross-references
#   subcategory  – primary catalog search term
#   fallback     – alternative subcategories if primary has no match
#   placement    – where to put the piece (see calculate_position)
#   rot_z        – Z-rotation in degrees at import time (0 = default model facing)
#   optional     – if True, silently skip when catalog has no match
# ---------------------------------------------------------------------------
ROOM_PRESETS: Dict[str, List[Dict[str, Any]]] = {
    "living_room": [
        {"slot": "sofa",         "subcategory": "sofa",         "placement": "south_wall",       "face": "room_center"},
        {"slot": "coffee_table", "subcategory": "coffee_table",  "placement": "in_front_of:sofa", "face": "sofa", "optional": True},
        {"slot": "armchair",     "subcategory": "armchair",      "placement": "beside:sofa:right","face": "coffee_table", "optional": True},
        {"slot": "side_table",   "subcategory": "side_table",    "placement": "beside:sofa:left", "optional": True},
        {"slot": "floor_lamp",   "subcategory": "floor_lamp",    "placement": "corner_sw",        "rot_z": 0,   "optional": True},
    ],
    "bedroom": [
        {"slot": "bed",          "subcategory": "double_bed",    "placement": "north_wall",       "face": "room_center",
         "fallback": ["queen_bed", "king_bed", "single_bed"]},
        {"slot": "nightstand_l", "subcategory": "nightstand",    "placement": "beside:bed:left",  "rot_z": 0,   "optional": True},
        {"slot": "nightstand_r", "subcategory": "nightstand",    "placement": "beside:bed:right", "rot_z": 0,   "optional": True},
        {"slot": "wardrobe",     "subcategory": "wardrobe",      "placement": "east_wall",        "face": "room_center", "optional": True},
        {"slot": "floor_lamp",   "subcategory": "floor_lamp",    "placement": "corner_ne",        "rot_z": 0,   "optional": True},
    ],
    "office": [
        {"slot": "desk",         "subcategory": "desk",          "placement": "north_wall",       "face": "room_center"},
        {"slot": "chair",        "subcategory": "armchair",      "placement": "in_front_of:desk", "face": "desk",
         "fallback": ["dining_chair"]},
        {"slot": "bookshelf",    "subcategory": "bookshelf",     "placement": "east_wall",        "face": "room_center", "optional": True},
        {"slot": "floor_lamp",   "subcategory": "floor_lamp",    "placement": "corner_nw",        "rot_z": 0,   "optional": True},
    ],
    "dining_room": [
        {"slot": "dining_table", "subcategory": "dining_table",  "placement": "center",           "rot_z": 0},
        {"slot": "chair_n",      "subcategory": "dining_chair",  "placement": "table_side:n",     "face": "dining_table"},
        {"slot": "chair_s",      "subcategory": "dining_chair",  "placement": "table_side:s",     "face": "dining_table"},
        {"slot": "chair_e",      "subcategory": "dining_chair",  "placement": "table_side:e",     "face": "dining_table", "optional": True},
        {"slot": "chair_w",      "subcategory": "dining_chair",  "placement": "table_side:w",     "face": "dining_table", "optional": True},
    ],
    "kitchen": [
        {"slot": "counter",      "subcategory": "kitchen_counter","placement": "north_wall",      "face": "room_center"},
        {"slot": "cabinet",      "subcategory": "kitchen_cabinet","placement": "east_wall",       "face": "room_center", "optional": True},
        {"slot": "stool",        "subcategory": "bar_stool",      "placement": "in_front_of:counter","face":"counter","optional": True},
    ],
    "bathroom": [
        {"slot": "bathtub",      "subcategory": "bathtub",        "placement": "north_wall",      "face": "room_center"},
        {"slot": "toilet",       "subcategory": "toilet",         "placement": "east_wall",       "face": "room_center"},
        {"slot": "cabinet",      "subcategory": "bathroom_cabinet","placement": "west_wall",      "face": "room_center", "optional": True},
    ],
}

_WALL_THICKNESS = 0.15
_WALL_GAP       = 0.08   # gap between furniture and wall inner face


def _footprint(asset: Dict) -> Tuple[float, float, float, float, float]:
    """Return (width, depth, height, clearance_front, clearance_sides).

    Reads asset.footprint when present, else falls back to dimensions_m.
    """
    fp = asset.get("footprint")
    if fp:
        return (
            float(fp.get("width_m", 1.0)),
            float(fp.get("depth_m", 0.8)),
            float(fp.get("height_m", 0.8)),
            float(fp.get("clearance_front_m", 0.0)),
            float(fp.get("clearance_sides_m", 0.0)),
        )
    d = asset.get("dimensions_m", {})
    return (
        float(d.get("width", 1.0)),
        float(d.get("depth", 0.8)),
        float(d.get("height", 0.8)),
        0.0,
        0.0,
    )


def _dims(asset: Dict) -> Tuple[float, float, float]:
    w, d, h, _, _ = _footprint(asset)
    return w, d, h


def _norm_room_type(room_type: Optional[str]) -> str:
    return (room_type or "").strip().lower().replace(" ", "_")


def asset_allowed_in_room(asset: Dict, room_type: Optional[str]) -> bool:
    """Return False for clear mismatches, e.g. bed in living_room."""
    rt = _norm_room_type(room_type)
    if not rt:
        return True
    if cat.is_container(asset):
        return False
    room_types = [str(r).lower() for r in asset.get("room_types", [])]
    if not room_types:
        return True
    return rt in room_types


def room_mismatch_reason(asset: Dict, room_type: Optional[str]) -> str:
    rt = _norm_room_type(room_type) or "unknown_room"
    rooms = ", ".join(asset.get("room_types", [])) or "no room metadata"
    return (
        f"asset '{asset.get('id', '?')}' is tagged for [{rooms}], "
        f"not '{rt}'"
    )


def room_type_for_container_room(container_asset: Optional[Dict], room_id: str) -> str:
    if not container_asset or not room_id:
        return ""
    for room in container_asset.get("rooms", []):
        if room.get("room_id") == room_id:
            return _norm_room_type(room.get("room_type", ""))
    return ""


def _aabb(location: List[float], asset: Dict) -> Tuple[float, float, float, float]:
    w, d, _, _, _ = _footprint(asset)
    x, y = float(location[0]), float(location[1])
    return (x - w / 2, x + w / 2, y - d / 2, y + d / 2)


def overlaps_placed(location: List[float], asset: Dict, placed: Dict[str, Dict]) -> Optional[str]:
    """Simple top-down footprint overlap check."""
    ax0, ax1, ay0, ay1 = _aabb(location, asset)
    for slot, info in placed.items():
        bx0, bx1, by0, by1 = _aabb(info["location"], info["asset"])
        if ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0:
            return slot
    return None


def _inner(half: float) -> float:
    return half - _WALL_THICKNESS - _WALL_GAP


def calculate_position(
    placement: str,
    asset: Dict,
    room: Dict,
    placed: Dict[str, Dict],
) -> List[float]:
    W, D = room["width"], room["depth"]
    aw, ad, _, a_clear_front, a_clear_sides = _footprint(asset)
    xi, yi = _inner(W / 2), _inner(D / 2)

    if placement == "south_wall":
        return [0.0, -(yi - ad / 2), 0.0]
    if placement == "north_wall":
        return [0.0,  yi - ad / 2,  0.0]
    if placement == "east_wall":
        return [ xi - ad / 2,  0.0, 0.0]
    if placement == "west_wall":
        return [-(xi - ad / 2), 0.0, 0.0]
    if placement == "center":
        return [0.0, 0.0, 0.0]
    if placement == "corner_sw":
        return [-(xi - aw / 2), -(yi - ad / 2), 0.0]
    if placement == "corner_se":
        return [ xi - aw / 2,  -(yi - ad / 2), 0.0]
    if placement == "corner_nw":
        return [-(xi - aw / 2),  yi - ad / 2,  0.0]
    if placement == "corner_ne":
        return [ xi - aw / 2,   yi - ad / 2,  0.0]

    if placement.startswith("in_front_of:"):
        ref = placed.get(placement.split(":")[1])
        if ref:
            rw, rd, _, r_clear_front, _ = _footprint(ref["asset"])
            rx, ry, _ = ref["location"]
            sign = 1 if ry <= 0 else -1
            # Use the *larger* of the two assets' front clearance, with a sensible floor
            gap = max(r_clear_front, a_clear_front, 0.3)
            return [rx, ry + sign * (rd / 2 + gap + ad / 2), 0.0]
        return [0.0, 0.0, 0.0]

    if placement.startswith("beside:"):
        _, ref_slot, side = placement.split(":")
        ref = placed.get(ref_slot)
        if ref:
            rw, _, _, _, r_clear_sides = _footprint(ref["asset"])
            rx, ry, _ = ref["location"]
            gap = max(r_clear_sides, a_clear_sides, 0.1)
            if side == "right":
                return [rx + rw / 2 + gap + aw / 2, ry, 0.0]
            else:
                return [rx - rw / 2 - gap - aw / 2, ry, 0.0]
        return [0.0, 0.0, 0.0]

    if placement.startswith("table_side:"):
        side = placement.split(":")[1]
        ref = placed.get("dining_table")
        if ref:
            rw, rd, _, r_clear_front, r_clear_sides = _footprint(ref["asset"])
            rx, ry, _ = ref["location"]
            gap_long = max(r_clear_front, 0.15)
            gap_side = max(r_clear_sides, 0.15)
            if side == "n": return [rx, ry + rd / 2 + gap_long + ad / 2, 0.0]
            if side == "s": return [rx, ry - rd / 2 - gap_long - ad / 2, 0.0]
            if side == "e": return [rx + rw / 2 + gap_side + aw / 2, ry, 0.0]
            if side == "w": return [rx - rw / 2 - gap_side - aw / 2, ry, 0.0]

    return [0.0, 0.0, 0.0]


def clamp_to_interior_bbox(
    location: List[float],
    asset: Dict,
    interior_bbox: Dict[str, List[float]] | None,
) -> List[float]:
    """Clamp a world-space location so the asset's footprint stays inside `interior_bbox`.

    interior_bbox is in the same coordinate space as `location` (i.e. already offset
    if the bbox was given in container-local coords). Returns the clamped [x,y,z].
    """
    if not interior_bbox:
        return location
    bmin = interior_bbox.get("min", [-1e9, -1e9, -1e9])
    bmax = interior_bbox.get("max", [1e9, 1e9, 1e9])
    w, d, _, _, _ = _footprint(asset)
    half_w, half_d = w / 2, d / 2
    x = max(bmin[0] + half_w, min(bmax[0] - half_w, location[0]))
    y = max(bmin[1] + half_d, min(bmax[1] - half_d, location[1]))
    z = max(bmin[2], min(bmax[2], location[2]))
    return [round(x, 3), round(y, 3), round(z, 3)]


def relative_facing_rot_z(reference_asset: Dict, placement: str) -> float:
    """Compute the extra Z rotation (deg) so that THIS asset's front faces the reference.

    Used by `in_front_of:<slot>` and `table_side:<side>`. Returns 0 if the placement
    isn't directional. Assumes both assets use forward_axis=+Y by default; the
    per-asset `facing_correction_z` is added separately in layout_tools.

    `placement` is the slot's placement string, e.g. "in_front_of:desk".
    """
    if placement.startswith("in_front_of:"):
        # Reference is at (rx, ry); we're placed on the side away from origin.
        # For a desk against +Y wall, the chair sits at lower Y → chair must face +Y
        # i.e. rotate 180 from default (+Y forward) to face the desk.
        ry = reference_asset.get("location", [0, 0, 0])[1]
        # If reference is on +Y side, we're on -Y side and face +Y → 180
        # If reference is on -Y side, we're on +Y side and face -Y → 0
        return 180.0 if ry >= 0 else 0.0
    if placement.startswith("table_side:"):
        side = placement.split(":")[1]
        # Each chair faces the table center
        return {"n": 180.0, "s": 0.0, "e": 90.0, "w": 270.0}.get(side, 0.0)
    return 0.0


def _rot_z_to_face(source: List[float], target: List[float]) -> float:
    dx = float(target[0]) - float(source[0])
    dy = float(target[1]) - float(source[1])
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return 0.0
    # Project convention: 0 faces +Y, 180 faces -Y, 270 faces +X, 90 faces -X.
    return math.degrees(math.atan2(-dx, dy)) % 360


def calculate_facing_rot_z(
    placement: str,
    location: List[float],
    placed: Dict[str, Dict],
    room: Dict,
    spec: Optional[Dict] = None,
) -> float:
    """Derive rotation from intent: face room center, a reference slot, or a table."""
    spec = spec or {}
    face = str(spec.get("face", "")).strip()

    if face and face not in {"none", "default"}:
        if face == "room_center":
            return _rot_z_to_face(location, [0.0, 0.0, 0.0])
        ref = placed.get(face)
        if ref:
            return _rot_z_to_face(location, ref["location"])

    if placement.startswith("in_front_of:"):
        ref = placed.get(placement.split(":")[1])
        if ref:
            return _rot_z_to_face(location, ref["location"])

    if placement.startswith("table_side:"):
        ref = placed.get("dining_table")
        if ref:
            return _rot_z_to_face(location, ref["location"])

    if placement.startswith("beside:"):
        return _rot_z_to_face(location, [0.0, 0.0, 0.0])

    if placement.endswith("_wall") or placement.startswith("corner_"):
        return _rot_z_to_face(location, [0.0, 0.0, 0.0])

    return float(spec.get("rot_z", 0.0))


def find_asset_for_slot(slot_def: Dict, style: Optional[str], room_type: Optional[str] = None) -> Optional[Dict]:
    subcats = [slot_def["subcategory"]] + slot_def.get("fallback", [])
    for subcat in subcats:
        results = cat.search_assets(subcategory=subcat, room_type=_norm_room_type(room_type), style=style, limit=5)
        if not results:
            results = cat.search_assets(subcategory=subcat, room_type=_norm_room_type(room_type), limit=5)
        if not results:
            # Last resort: ignore room_type — coach already validated appropriateness
            results = cat.search_assets(subcategory=subcat, limit=5)
        if results:
            return results[0]
    return None


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_tools(mcp, client):

    @mcp.tool()
    async def suggest_furniture_plan(
        room_type: str,
        style: Optional[str] = None,
    ) -> str:
        """Suggest furniture from the catalog for a room — no Blender connection needed.

        Use this to preview what will be placed before calling design_interior.

        Args:
            room_type: living_room | bedroom | office | dining_room | kitchen | bathroom
            style: Style keyword (e.g. industrial, classic, mid-century)
        """
        room_type = room_type.lower().replace(" ", "_")
        preset = ROOM_PRESETS.get(room_type)
        if not preset:
            return f"Unknown room type. Available: {', '.join(ROOM_PRESETS)}"

        title = room_type.replace("_", " ").title()
        style_note = f" ({style} style)" if style else ""
        lines = [f"Furniture plan — {title}{style_note}", "=" * 50, ""]

        found = 0
        for slot_def in preset:
            asset = find_asset_for_slot(slot_def, style, room_type)
            label = slot_def["slot"].replace("_", " ").title()
            if asset:
                aw, ad, ah = _dims(asset)
                lines.append(f"  {label:22s}  {asset['id']}")
                lines.append(f"    {asset['name']}")
                lines.append(f"    {aw:.2f}w × {ad:.2f}d × {ah:.2f}h m  |  {asset.get('poly_count','?')} polys")
                found += 1
            else:
                note = "(optional — none found)" if slot_def.get("optional") else "NOT FOUND in catalog"
                lines.append(f"  {label:22s}  {note}")
            lines.append("")

        lines.append(f"Matched {found}/{len(preset)} slots.")
        lines.append("Run design_interior(...) to build and furnish the room.")
        return "\n".join(lines)

    @mcp.tool()
    async def design_interior(
        room_type: str,
        width_m: float,
        depth_m: float,
        height_m: float = 2.7,
        style: Optional[str] = None,
        wall_thickness: float = 0.15,
    ) -> str:
        """Create a furnished room from the local asset catalog.

        Requires the Asset Library Blender addon to be running on port 8766.
        (N panel → Asset Library tab → Start Server)

        Steps:
          1. Builds floor + 4 walls
          2. Searches catalog for matching furniture (style-aware)
          3. Imports each .blend asset at its calculated position

        Args:
            room_type:      living_room | bedroom | office | dining_room | kitchen | bathroom
            width_m:        Room width in meters  (X axis)
            depth_m:        Room depth in meters  (Y axis)
            height_m:       Ceiling height in meters (default 2.7)
            style:          Style keyword (e.g. industrial, classic, mid-century)
            wall_thickness: Wall thickness in meters (default 0.15)
        """
        room_type = room_type.lower().replace(" ", "_")
        preset = ROOM_PRESETS.get(room_type)
        if not preset:
            return f"Unknown room type. Available: {', '.join(ROOM_PRESETS)}"

        # ── connection check ──────────────────────────────────────────────
        if not await client.health_check():
            return (
                "Asset Library addon is NOT running (port 8766).\n"
                "In Blender: press N → 'Asset Library' tab → 'Start Server'."
            )

        title = room_type.replace("_", " ").title()
        style_note = f" | {style}" if style else ""
        log: List[str] = [
            f"Interior Design: {title}{style_note}  ({width_m}m × {depth_m}m × {height_m}m)",
            "=" * 60,
        ]

        room_info = {"width": width_m, "depth": depth_m, "height": height_m}

        # ── 1. Create room ────────────────────────────────────────────────
        log.append("\n[1/3] Creating room geometry...")
        try:
            await client.execute("create_room", {
                "width": width_m, "depth": depth_m,
                "height": height_m, "wall_thickness": wall_thickness,
            })
            log.append(f"  Floor + 4 walls created.")
        except Exception as e:
            log.append(f"  WARNING: {e}")

        # ── 2. Import furniture ───────────────────────────────────────────
        log.append("\n[2/3] Importing furniture...")
        placed: Dict[str, Dict] = {}

        for slot_def in preset:
            label = slot_def["slot"].replace("_", " ").title()
            asset = find_asset_for_slot(slot_def, style, room_type)

            if not asset:
                note = "skipped (optional)" if slot_def.get("optional") else "NOT FOUND"
                log.append(f"  {label:22s}  {note}")
                continue

            if not asset_allowed_in_room(asset, room_type):
                log.append(f"  {label:22s}  skipped: {room_mismatch_reason(asset, room_type)}")
                continue

            abs_file = cat.resolve_file_path(asset["file"])
            if not abs_file.exists():
                log.append(f"  {label:22s}  file missing: {abs_file.name}")
                continue

            pos = calculate_position(slot_def["placement"], asset, room_info, placed)
            overlapping = overlaps_placed(pos, asset, placed)
            if overlapping:
                log.append(f"  {label:22s}  skipped: footprint overlaps '{overlapping}'")
                continue

            slot_rot_z = calculate_facing_rot_z(slot_def["placement"], pos, placed, room_info, slot_def)
            total_rot_z = (slot_rot_z + cat.get_facing_correction_z(asset)) % 360

            try:
                result = await client.execute("import_blend_asset", {
                    "file_path": str(abs_file),
                    "location":  pos,
                    "rotation":  [0.0, 0.0, total_rot_z],
                    "scale":     1.0,
                    "name":      slot_def["slot"],
                })
                obj_name = result.get("name", slot_def["slot"])
                loc = result.get("location", pos)
                log.append(
                    f"  {label:22s}  {asset['name'][:28]:28s}"
                    f"  @ ({loc[0]:.2f}, {loc[1]:.2f}, {loc[2]:.2f})"
                )
                placed[slot_def["slot"]] = {"asset": asset, "location": pos, "obj_name": obj_name}
            except Exception as e:
                log.append(f"  {label:22s}  import failed: {e}")

        # ── 3. Summary ────────────────────────────────────────────────────
        log.append(f"\n[3/3] Summary")
        log.append(f"  Placed {len(placed)}/{len(preset)} furniture pieces.")

        if placed:
            log.append("\nObject positions (meters from room center):")
            for slot, info in placed.items():
                x, y, z = info["location"]
                log.append(f"  {info['obj_name']:30s}  ({x:+.2f}, {y:+.2f}, {z:+.2f})")
            log.append("\nTip: select an object in Blender and use G to move, R to rotate.")

        return "\n".join(log)
