"""Handler for creating room geometry (floor + 4 walls) via bpy."""

import bpy
import math
from typing import Any, Dict


def create_room(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a rectangular room: floor plane + 4 wall cubes.

    Args:
        params:
            width          – room width in meters (X axis)
            depth          – room depth in meters (Y axis)
            height         – ceiling height in meters (default 2.7)
            wall_thickness – wall thickness in meters (default 0.15)
            name_prefix    – prefix for created objects (default "Room")
    """
    width     = float(params.get("width",  5.0))
    depth     = float(params.get("depth",  4.0))
    height    = float(params.get("height", 2.7))
    thick     = float(params.get("wall_thickness", 0.15))
    prefix    = params.get("name_prefix", "Room")

    created = []

    def _make_box(name, loc, sx, sy, sz):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
        obj = bpy.context.active_object
        obj.name = f"{prefix}_{name}"
        obj.scale = (sx, sy, sz)
        bpy.ops.object.transform_apply(scale=True)
        created.append(obj.name)
        return obj

    # Floor — thin slab at z = 0
    _make_box("Floor",      (0, 0, -0.025),   width, depth, 0.05)

    # North wall  (+Y side)
    _make_box("Wall_North", (0,  depth / 2 - thick / 2, height / 2), width, thick, height)

    # South wall  (−Y side)
    _make_box("Wall_South", (0, -depth / 2 + thick / 2, height / 2), width, thick, height)

    # East wall   (+X side)
    _make_box("Wall_East",  ( width / 2 - thick / 2, 0, height / 2), thick, depth, height)

    # West wall   (−X side)
    _make_box("Wall_West",  (-width / 2 + thick / 2, 0, height / 2), thick, depth, height)

    bpy.ops.object.select_all(action="DESELECT")

    return {
        "created_objects": created,
        "width": width,
        "depth": depth,
        "height": height,
        "wall_thickness": thick,
    }


def list_scene_objects(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return all mesh objects in the scene with their positions and dimensions."""
    objects = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        bb = obj.bound_box  # 8 corners in local space
        local_dims = [
            max(c[i] for c in bb) - min(c[i] for c in bb)
            for i in range(3)
        ]
        # Scale to world dimensions
        dims = [local_dims[i] * abs(obj.scale[i]) for i in range(3)]
        wm   = obj.matrix_world
        wloc = wm.translation
        wrot = wm.to_euler('XYZ')
        objects.append({
            "name":          obj.name,
            "location":      [round(wloc.x, 3), round(wloc.y, 3), round(wloc.z, 3)],
            "dims_m":        [round(v, 3) for v in dims],
            "visible":       not obj.hide_viewport,
            "rotation_euler": [round(math.degrees(v), 1) for v in wrot],
        })
    return {"objects": objects, "count": len(objects)}


def test_asset_facing(params: Dict[str, Any]) -> Dict[str, Any]:
    """Import an asset at origin with ZERO rotation so you can inspect its default facing.

    Use this to calibrate facing_correction_z in Catalog.json:
      1. Call this with a file_path
      2. Look at the object in Blender (Numpad 7 = top view, Numpad 1 = front view)
      3. Note which direction the 'front' faces:
         - Faces toward you in front view (−Y) → default_facing = south
         - Faces away from you (+Y)            → default_facing = north
         - Faces right (+X)                    → default_facing = east
         - Faces left (−X)                     → default_facing = west
      4. Desired facing for placements:
         - north_wall → front should face south  → correction = 0   if south, 180 if north
         - south_wall → front should face north  → correction = 180 if south, 0   if north
         - east_wall  → front should face west   → correction = 90  if south, 270 if north
         - west_wall  → front should face east   → correction = 270 if south, 90  if north

    Args:
        params:
            file_path – absolute path to the .blend file
            name      – optional label prefix (default: "FACING_TEST")
    """
    from .blend_import import import_blend_asset

    label    = params.get("name", "asset")
    rotation = params.get("rotation", [0.0, 0.0, 0.0])
    scale    = params.get("scale", 1.0)
    result = import_blend_asset({
        "file_path": params.get("file_path", ""),
        "location":  [0.0, 0.0, 0.0],
        "rotation":  rotation,
        "scale":     scale,
        "name":      f"FACING_TEST_{label}",
    })
    result["hint"] = (
        "Object imported at origin with rot=0. "
        "In Blender: press Numpad 7 (top) or Numpad 1 (front) to inspect facing direction."
    )
    return result


def get_3d_cursor(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return the current 3D cursor position in world space.

    Use this to measure room origins inside a house model:
      1. Import the house model in Blender
      2. Shift+Right Click to place the 3D cursor at the room center
      3. Call get_3d_cursor to read the coordinates
      4. Save those as origin_offset_m in Catalog.json for that room
    """
    import bpy
    loc = bpy.context.scene.cursor.location
    return {
        "location": [round(loc.x, 3), round(loc.y, 3), round(loc.z, 3)],
        "copy_paste": f"[{loc.x:.3f}, {loc.y:.3f}, {loc.z:.3f}]",
    }


def delete_objects(params: Dict[str, Any]) -> Dict[str, Any]:
    """Delete Blender objects by name.

    Args:
        params:
            names – list of object names to delete
    """
    import bpy
    names = params.get("names", [])
    removed = []
    not_found = []
    for name in names:
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
            removed.append(name)
        else:
            not_found.append(name)
    return {"removed": removed, "count": len(removed), "not_found": not_found}


def rotate_objects(params: Dict[str, Any]) -> Dict[str, Any]:
    """Rotate objects around Z axis by a delta angle.

    Args:
        params:
            names   – list of object names to rotate
            delta_z – degrees to add to current Z rotation (can be negative)
    """
    names   = params.get("names", [])
    delta_z = float(params.get("delta_z", 90.0))

    rotated = []
    seen_roots: set = set()

    for name in names:
        if name not in bpy.data.objects:
            continue
        obj = bpy.data.objects[name]
        # Walk up to the topmost parent so the whole asset moves together
        root = obj
        while root.parent is not None:
            root = root.parent
        if root.name in seen_roots:
            continue
        seen_roots.add(root.name)
        root.rotation_euler[2] += math.radians(delta_z)
        rotated.append(root.name)

    return {"rotated": rotated, "delta_z": delta_z}


ROOM_HANDLERS = {
    "create_room":         create_room,
    "list_scene_objects":  list_scene_objects,
    "test_asset_facing":   test_asset_facing,
    "get_3d_cursor":       get_3d_cursor,
    "delete_objects":      delete_objects,
    "rotate_objects":      rotate_objects,
}
