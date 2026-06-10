"""Layout calculation tools for agno agents.

v2 changes:
  - Reads asset.footprint (with clearance) instead of bare dimensions_m
  - Honors asset.placement.forward_axis + facing_correction_z
  - Computes RELATIVE facing for in_front_of / table_side / beside placements so
    e.g. a chair's back faces the desk
  - Optional container_id + room_id clamp the world position to interior_bbox_local
    so furniture cannot land outside a house's interior shell
"""
import json
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_server import catalog
from mcp_server.tools.interior_design_tools import (
    _WALL_GAP,
    _WALL_THICKNESS,
    _footprint,
    asset_allowed_in_room,
    calculate_facing_rot_z,
    calculate_position,
    clamp_to_interior_bbox,
    overlaps_placed,
    room_mismatch_reason,
    room_type_for_container_room,
)


def calculate_furniture_layout(
    room_width: float,
    room_depth: float,
    room_height: float,
    furniture_json: str,
    origin_offset: str = "[0.0, 0.0, 0.0]",
    container_id: str = "",
    room_id: str = "",
    room_type: str = "",
) -> str:
    """Calculate exact 3D positions for furniture in a room.

    Args:
        room_width:     Room width in meters (X axis)
        room_depth:     Room depth in meters (Y axis)
        room_height:    Ceiling height in meters
        furniture_json: JSON list of furniture slots:
            [
              {"slot":"desk",  "asset_id":"desk_metal_industrial_01", "placement":"north_wall",       "rot_z":180},
              {"slot":"chair", "asset_id":"armchair_lounge_leather_01","placement":"in_front_of:desk","rot_z":0}
            ]
            Valid placements: north_wall, south_wall, east_wall, west_wall, center,
            corner_nw, corner_ne, corner_sw, corner_se,
            in_front_of:<slot>, beside:<slot>:left, beside:<slot>:right,
            table_side:n, table_side:s, table_side:e, table_side:w
        origin_offset:  JSON [x,y,z] — world-space offset of the room center.
                        For from-scratch rooms: "[0,0,0]".
                        For house rooms: the room's `origin_offset_m` from Catalog.json.
        container_id:   Optional asset ID of the container house. When given, furniture
                        positions are clamped to the container's interior_bbox_local.
        room_id:        Optional room ID inside the container. Uses room-level
                        interior_bbox_local when present, else falls back to container bbox.
        room_type:      Optional room type guard for from-scratch rooms. If omitted
                        and container_id+room_id are present, read it from Catalog.json.

    Returns JSON with file_path and calculated [x,y,z] location for each piece.
    """
    try:
        specs = json.loads(furniture_json)
    except json.JSONDecodeError as e:
        return f"Invalid furniture_json: {e}"

    try:
        offset = json.loads(origin_offset) if isinstance(origin_offset, str) else list(origin_offset)
        if len(offset) < 3:
            offset = [0.0, 0.0, 0.0]
    except Exception:
        offset = [0.0, 0.0, 0.0]

    # ── Resolve container interior bbox in world space (if any) ──────────
    interior_bbox_world = None
    container_asset = None
    active_room_type = room_type.lower().replace(" ", "_") if room_type else ""
    if container_id:
        container_asset = catalog.get_asset_by_id(container_id)
        if container_asset:
            active_room_type = active_room_type or room_type_for_container_room(container_asset, room_id)
            local_bbox = catalog.get_room_interior_bbox(container_asset, room_id) \
                if room_id else catalog.get_interior_bbox(container_asset)
            if local_bbox:
                # Container itself is imported at world origin with rot_z=0 (Workflow B),
                # so local == world for the bbox.
                interior_bbox_world = {
                    "min": list(local_bbox["min"]),
                    "max": list(local_bbox["max"]),
                }

    # ── Workflow A: synthesize an interior bbox from room dimensions ──────
    # Same clamping logic protects from-scratch rooms; previously only
    # Workflow B (house container) had a bbox, so beside:/in_front_of:
    # placements could push furniture through the walls.
    if interior_bbox_world is None:
        margin = _WALL_THICKNESS + _WALL_GAP
        interior_bbox_world = {
            "min": [-(room_width / 2) + margin, -(room_depth / 2) + margin, 0.0],
            "max": [ (room_width / 2) - margin,  (room_depth / 2) - margin, room_height],
        }

    room = {"width": room_width, "depth": room_depth, "height": room_height}
    placed: Dict[str, Dict] = {}
    result = []

    # Subcategories a seat naturally faces, in priority order
    _SEAT_FOCAL_SUBCATS = ("desk", "dining_table", "coffee_table")

    # ── on_surface: Z height from parent's top surface ────────────────
    def _surface_z(spec: Dict, placed_map: Dict) -> float | None:
        parent_slot = spec.get("on_surface")
        if not parent_slot or parent_slot not in placed_map:
            return None
        parent = placed_map[parent_slot]
        pa = parent["asset"]
        h = (pa.get("footprint") or {}).get("height_m") \
            or (pa.get("dimensions_m") or {}).get("height", 0.0)
        return round(parent["location"][2] + float(h or 0.0), 3)

    # ── Rotation-aware footprint helpers ──────────────────────────────
    # When an asset is placed against the east or west wall it stands perpendicular
    # to the wall, so its X and Y extents swap. The bare _footprint(asset) always
    # returns the model's default (Y-forward) width/depth, which would over-report
    # the X extent for wall-hugging assets and cause false-positive overlaps.
    # An explicit rotation_override (from the SVG yapboz UI) takes precedence
    # over the placement-based heuristic — the user may have rotated freely.
    def _effective_wd(asset: Dict, placement: str, rotation_override=None):
        w, d, _, _, _ = _footprint(asset)
        if rotation_override is not None:
            rot = float(rotation_override) % 180
            if 45 < rot < 135:
                return d, w
            return w, d
        if placement in ("east_wall", "west_wall"):
            return d, w
        return w, d

    def _aabb_rot(location, asset, placement, rotation_override=None):
        ew, ed = _effective_wd(asset, placement, rotation_override)
        x, y = float(location[0]), float(location[1])
        return (x - ew / 2, x + ew / 2, y - ed / 2, y + ed / 2)

    def _overlaps_rot(location, asset, placement, placed_map, rotation_override=None):
        ax0, ax1, ay0, ay1 = _aabb_rot(location, asset, placement, rotation_override)
        for slot_name, info in placed_map.items():
            bp = info.get("placement", "")
            br = info.get("rotation_override")
            bx0, bx1, by0, by1 = _aabb_rot(info["location"], info["asset"], bp, br)
            if ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0:
                return slot_name
        return None

    def _clamp_rot(location, asset, placement, bbox, rotation_override=None):
        ew, ed = _effective_wd(asset, placement, rotation_override)
        bmin = bbox.get("min", [-1e9, -1e9, -1e9])
        bmax = bbox.get("max", [ 1e9,  1e9,  1e9])
        x = max(bmin[0] + ew / 2, min(bmax[0] - ew / 2, location[0]))
        y = max(bmin[1] + ed / 2, min(bmax[1] - ed / 2, location[1]))
        z = max(bmin[2], min(bmax[2], location[2]))
        return [round(x, 3), round(y, 3), round(z, 3)]

    # Process order:
    #   0) focal anchors (desk, dining_table, coffee_table) — seats reference them
    #   1) relative placements (in_front_of:, beside:, table_side:) — settle near
    #      the focal piece into the room's interior
    #   2) wall fillers (north/south/east/west_wall, corners, center) LAST so they
    #      slide around the already-placed central pieces; the wall-rotation
    #      fallback below can then move them to an empty wall when they collide.
    def _spec_priority(s: Dict) -> int:
        p = (s.get("placement") or "center").lower()
        a = catalog.get_asset_by_id(s.get("asset_id", ""))
        if a and a.get("subcategory", "") in _SEAT_FOCAL_SUBCATS:
            return 0
        if p.startswith("in_front_of:") or p.startswith("beside:") or p.startswith("table_side:"):
            return 1
        if s.get("on_surface"):
            return 3  # process after parent surface is placed
        return 2

    specs = sorted(specs, key=_spec_priority)

    for spec in specs:
        asset_id = spec.get("asset_id")
        slot = spec.get("slot", asset_id)

        if not asset_id:
            result.append({"slot": slot, "error": "missing asset_id"})
            continue

        asset = catalog.get_asset_by_id(asset_id)
        if not asset:
            result.append({"slot": slot, "error": f"asset '{asset_id}' not found in catalog"})
            continue

        spec_room_type = spec.get("room_type") or active_room_type
        allow_mismatch = bool(spec.get("allow_room_mismatch", False))
        if spec_room_type and not allow_mismatch and not asset_allowed_in_room(asset, spec_room_type):
            result.append({"slot": slot, "asset_id": asset_id, "error": room_mismatch_reason(asset, spec_room_type)})
            continue

        placement = spec.get("placement", "center")

        # ── User overrides from the SVG yapboz UI ─────────────────────────
        # If the user dragged the asset on the 2D plan, the spec carries an
        # explicit location_override [x,y,z] (and possibly rotation_override).
        # Skip auto-placement entirely; trust the human's coordinates.
        loc_override = spec.get("location_override")
        if loc_override is not None and len(loc_override) >= 2:
            pos = [float(loc_override[0]), float(loc_override[1]),
                   float(loc_override[2]) if len(loc_override) > 2 else 0.0]
        else:
            pos = calculate_position(placement, asset, room, placed)

        # ── Surface relationship: Z = parent top surface height ───────────
        # on_surface:"desk" → lamp placed at desk.height above the floor.
        # X,Y: keep the user's drag position if available; otherwise center on parent.
        surface_z = _surface_z(spec, placed)
        is_on_surface = surface_z is not None
        if is_on_surface:
            pos[2] = surface_z
            if loc_override is None:
                parent_slot = spec["on_surface"]
                parent_loc = placed[parent_slot]["location"]
                pos[0] = parent_loc[0]
                pos[1] = parent_loc[1]

        has_loc_override = loc_override is not None and len(loc_override) >= 2

        # Smart wall snap: a `beside:<ref>:right` that pushes the asset past the
        # east wall is almost certainly a sign the user really wanted the asset
        # against the wall (rooms aren't always wide enough to fit a sofa next
        # to a desk). Swap to east_wall / west_wall so the asset hugs the wall
        # and the auto-face logic still turns it toward room_center / the desk.
        # Skip when the user manually placed the asset via the SVG yapboz.
        if not has_loc_override and placement.startswith("beside:"):
            parts = placement.split(":")
            if len(parts) == 3:
                side = parts[2]
                aw, _, _, _, _ = _footprint(asset)
                x_max = interior_bbox_world["max"][0] - aw / 2
                x_min = interior_bbox_world["min"][0] + aw / 2
                snap_to = None
                if side == "right" and pos[0] > x_max:
                    snap_to = "east_wall"
                elif side == "left" and pos[0] < x_min:
                    snap_to = "west_wall"
                if snap_to:
                    placement = snap_to
                    spec["placement"] = snap_to
                    pos = calculate_position(snap_to, asset, room, placed)

        # Clamp the room-local position to the interior bbox (Workflow A uses a
        # synthesized bbox; Workflow B uses the container's). Rotation-aware so
        # wall-hugging assets keep their effective X/Y extents.
        # Surface-mounted items (on_surface) are skipped: they live on top of a
        # parent object, not on the floor, so floor-bbox clamping and floor-level
        # overlap checks don't apply to them.
        rot_override_for_geom = spec.get("rotation_override")
        if is_on_surface:
            clamped_local = [round(pos[0], 3), round(pos[1], 3), round(pos[2], 3)]
            overlapping = None
        else:
            world_check = [pos[i] + float(offset[i]) for i in range(3)]
            world_clamped = _clamp_rot(world_check, asset, placement, interior_bbox_world,
                                       rotation_override=rot_override_for_geom)
            clamped_local = [round(world_clamped[i] - float(offset[i]), 3) for i in range(3)]

            # Manual placements bypass overlap/wall-fallback: the user dragged this
            # to a specific spot and we should trust them. Only auto-computed
            # positions get the collision rescue.
            overlapping = None if has_loc_override else _overlaps_rot(
                clamped_local, asset, placement, placed, rotation_override=rot_override_for_geom)

        # If a placement collides with something already placed, try walls then
        # corners before giving up. This covers both wall placements AND "center"
        # placements (items added via catalog picker default to "center").
        # (is_on_surface items have overlapping=None so this block is skipped)
        _ALL_FALLBACKS = [
            "east_wall", "west_wall", "south_wall", "north_wall",
            "corner_ne", "corner_nw", "corner_se", "corner_sw",
        ]
        if overlapping and placement in ("north_wall", "south_wall", "east_wall",
                                         "west_wall", "center",
                                         "corner_ne", "corner_nw", "corner_se", "corner_sw"):
            alternatives = [w for w in _ALL_FALLBACKS if w != placement]
            for alt in alternatives:
                alt_pos = calculate_position(alt, asset, room, placed)
                alt_world = [alt_pos[i] + float(offset[i]) for i in range(3)]
                alt_clamped_world = _clamp_rot(alt_world, asset, alt, interior_bbox_world,
                                               rotation_override=rot_override_for_geom)
                alt_clamped_local = [round(alt_clamped_world[i] - float(offset[i]), 3) for i in range(3)]
                if not _overlaps_rot(alt_clamped_local, asset, alt, placed,
                                     rotation_override=rot_override_for_geom):
                    placement = alt
                    spec["placement"] = alt  # downstream face/rotation reads this
                    pos = alt_pos
                    clamped_local = alt_clamped_local
                    overlapping = None
                    break

        if overlapping:
            result.append({
                "slot": slot,
                "asset_id": asset_id,
                "error": f"footprint overlaps '{overlapping}'",
            })
            continue

        placed[slot] = {"asset": asset, "location": clamped_local, "placement": placement,
                        "rotation_override": rot_override_for_geom}

        abs_file = catalog.resolve_file_path(asset["file"])
        dim = asset.get("dimensions_m", {})

        # Auto-face fallback: a seat without an explicit face turns toward the
        # most relevant already-placed focal asset (desk > dining_table > coffee_table),
        # so a "sofa" custom slot in an office faces the desk instead of the wall.
        if not spec.get("face") and asset.get("category") == "seating":
            for target_sub in _SEAT_FOCAL_SUBCATS:
                target_slot = next(
                    (s for s, info in placed.items()
                     if s != slot and info["asset"].get("subcategory") == target_sub),
                    None,
                )
                if target_slot:
                    spec["face"] = target_slot
                    break

        # ── Rotation: user override > intent-based facing + asset correction ─
        rot_override = spec.get("rotation_override")
        if rot_override is not None:
            total_rot_z = float(rot_override) % 360
        else:
            slot_rot_z = calculate_facing_rot_z(placement, clamped_local, placed, room, spec)
            correction = catalog.get_facing_correction_z(asset)
            total_rot_z = (slot_rot_z + correction) % 360

        # ── World position uses the already-clamped local position ──
        world_pos = [round(clamped_local[i] + float(offset[i]), 3) for i in range(3)]

        entry: Dict = {
            "slot":               slot,
            "asset_id":           asset_id,
            "name":               asset["name"],
            "file_path":          str(abs_file),
            "location":           world_pos,
            "rotation_z":         total_rot_z,
            "facing_correction_z": int(correction % 360),
            "file_exists":        abs_file.exists(),
            "dimensions_m":       dim,
            "room_height":        room_height,
        }
        if spec.get("on_surface"):
            entry["on_surface"] = spec["on_surface"]
            entry["surface_z_m"] = world_pos[2]
        result.append(entry)

    return json.dumps(result, indent=2)
