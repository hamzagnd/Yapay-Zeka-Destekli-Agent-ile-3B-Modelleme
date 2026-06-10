"""Blender tools for agno agents — sync HTTP calls to the Blender addon on port 8766."""
import json
import httpx

_BLENDER_URL = "http://localhost:8766"


def _call_blender(action: str, params: dict, timeout: float = 30.0) -> dict:
    with httpx.Client(timeout=timeout) as client:
        r = client.post(_BLENDER_URL, json={"action": action, "params": params})
        r.raise_for_status()
        result = r.json()
        if not result.get("success"):
            raise Exception(result.get("error", "Unknown Blender error"))
        return result.get("result", {})


def check_blender_connection() -> str:
    """Check if the Blender Asset Library addon is running on port 8766.

    Returns connection status. ALWAYS call this first before any Blender operations.
    """
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{_BLENDER_URL}/health")
            if r.status_code == 200:
                return "Blender addon is running on port 8766. Ready to receive commands."
    except Exception:
        pass
    return (
        "Blender addon is NOT running.\n"
        "To fix: Open Blender → press N → 'Asset Library' tab → click 'Start Server'."
    )


def create_room_in_blender(
    width: float,
    depth: float,
    height: float,
    wall_thickness: float = 0.15,
) -> str:
    """Create a room (floor + 4 walls) in the active Blender scene.

    Args:
        width: Room width in meters (X axis)
        depth: Room depth in meters (Y axis)
        height: Ceiling height in meters
        wall_thickness: Wall thickness in meters (default 0.15)
    """
    result = _call_blender("create_room", {
        "width": width,
        "depth": depth,
        "height": height,
        "wall_thickness": wall_thickness,
    })
    objs = result.get("created_objects", [])
    return (
        f"Room created successfully.\n"
        f"Objects: {', '.join(objs)}\n"
        f"Dimensions: {width}m wide × {depth}m deep × {height}m tall."
    )


def create_polygon_room_in_blender(
    points: list,
    height: float = 2.7,
    wall_thickness: float = 0.15,
) -> str:
    """Create a custom polygon-shaped room from wall corner coordinates.

    Args:
        points: List of [x, y] pairs in meters, already centered at origin.
        height: Ceiling height in meters.
        wall_thickness: Wall thickness in meters.
    """
    pts_repr = repr([[float(p[0]), float(p[1])] for p in points])
    script = f"""
import bpy, bmesh, math

pts = {pts_repr}
h = {float(height):.3f}
thick = {float(wall_thickness):.3f}
n = len(pts)

# Remove any existing Room_ objects
for obj in list(bpy.data.objects):
    if obj.name.startswith("Room_"):
        bpy.data.objects.remove(obj, do_unlink=True)

# Floor (polygon face) — data API, no operator context needed
me_fl = bpy.data.meshes.new("Room_Floor_Mesh")
bm = bmesh.new()
verts = [bm.verts.new((p[0], p[1], 0.0)) for p in pts]
try:
    face = bm.faces.new(verts)
    bmesh.ops.recalc_face_normals(bm, faces=[face])
except Exception:
    pass
bm.to_mesh(me_fl)
bm.free()
fl = bpy.data.objects.new("Room_Floor", me_fl)
bpy.context.collection.objects.link(fl)

# Walls — use data API to avoid bpy.ops context issues:
# primitive_cube_add(location=...) silently ignores location in HTTP addon context.
# Instead: create mesh via bmesh, scale vertices directly, set location on object.
for i in range(n):
    a = pts[i]
    b = pts[(i + 1) % n]
    dx = b[0] - a[0]; dy = b[1] - a[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 0.05:
        continue
    angle = math.atan2(dy, dx)
    cx = (a[0] + b[0]) / 2
    cy = (a[1] + b[1]) / 2

    me_w = bpy.data.meshes.new(f"Room_Wall_{{i+1:02d}}_Mesh")
    bm_w = bmesh.new()
    bmesh.ops.create_cube(bm_w, size=1.0)
    bm_w.to_mesh(me_w)
    bm_w.free()
    wall = bpy.data.objects.new(f"Room_Wall_{{i+1:02d}}", me_w)
    bpy.context.collection.objects.link(wall)

    # Scale vertices in mesh data (dims_m will report correct length/thick/h)
    for v in me_w.vertices:
        v.co.x *= length
        v.co.y *= thick
        v.co.z *= h
    # Set world position and rotation directly on object
    wall.location = (cx, cy, h / 2)
    wall.rotation_euler[2] = angle
"""
    result = _call_blender("run_python", {"script": script}, timeout=30.0)
    if result.get("error"):
        return f"Polygon room creation failed: {result['error']}"
    n = len(points)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    w = max(xs) - min(xs)
    d = max(ys) - min(ys)
    return (
        f"Polygon room created: floor + {n} walls.\n"
        f"Shape: {n}-corner polygon, bbox {w:.2f}×{d:.2f}m, height {height:.2f}m."
    )


def import_assets_to_blender(placement_json: str) -> str:
    """Import furniture into Blender based on a placement plan.

    Args:
        placement_json: JSON list from the Layout Designer, format:
            [{"slot":"desk", "asset_id":"...", "file_path":"C:/.../.blend",
              "location":[x,y,z], "rotation_z":180}, ...]
            Missing file_path / slot are recovered from asset_id when possible
            so a paraphrased LLM response still works.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from mcp_server import catalog as _catalog

    try:
        plan = json.loads(placement_json)
    except json.JSONDecodeError as e:
        return f"Invalid placement JSON: {e}"

    placed = []
    errors = []

    for piece in plan:
        # Identify the piece even if the LLM dropped 'slot'
        slot = piece.get("slot") or piece.get("name") or piece.get("asset_id") or "unknown"

        if piece.get("error"):
            errors.append(f"  {slot}: skipped — {piece['error']}")
            continue

        # Recover file_path from asset_id if the LLM stripped it
        file_path = piece.get("file_path")
        asset_id = piece.get("asset_id")
        asset = None
        if asset_id:
            asset = _catalog.get_asset_by_id(asset_id)
        if not file_path and asset:
            file_path = str(_catalog.resolve_file_path(asset["file"]))

        if not file_path:
            errors.append(f"  {slot}: missing file_path (asset_id={asset_id!r})")
            continue

        if not piece.get("file_exists", True):
            errors.append(f"  {slot}: file missing — {file_path}")
            continue

        location = piece.get("location") or [0.0, 0.0, 0.0]
        rotation_z = piece.get("rotation_z", 0.0)

        # ── Pull all correction values from catalog ──────────────────────
        explicit_scale = float(asset.get("import_scale", 1.0)) if asset else 1.0
        rot_corr = [0.0, 0.0, 0.0]
        catalog_dims = None
        if asset:
            rc = asset.get("rotation_correction", [0, 0, 0])
            rot_corr = [float(rc[0]), float(rc[1]), float(rc[2])]
            # NOTE: facing_correction_z is already baked into rotation_z by layout_tools.
            # Only rotation_correction (X/Y axis fix for sideways models) is applied here.
            # Prefer the layout piece's dims (already normalized to realistic size by
            # layout_tools) over the raw catalog dims, so the importer scales the mesh
            # to the consistent, room-aware target.
            dims = piece.get("dimensions_m") or asset.get("dimensions_m") or {}
            cw, cd, ch = dims.get("width"), dims.get("depth"), dims.get("height")
            if cw and cd and ch:
                catalog_dims = {"width": float(cw), "depth": float(cd), "height": float(ch)}

        # Final rotation: layout's rotation_z (already includes facing correction)
        # + model's axis correction (X/Y for sideways imports) + extra Z offset
        final_rotation = [
            rot_corr[0],
            rot_corr[1],
            rotation_z + rot_corr[2],
        ]

        room_h     = float(piece.get("room_height", 0))
        # Use the human-readable catalog name for the Blender object so users see
        # "Desk_Set" instead of "sf_f26030d09d73" in the outliner / scene tab.
        blender_name = (piece.get("name") or "").strip().replace(" ", "_") or slot
        try:
            result = _call_blender("import_blend_asset", {
                "file_path":   file_path,
                "location":    location,
                "rotation":    final_rotation,
                "scale":       explicit_scale,
                "name":        blender_name,
                "catalog_dims": catalog_dims,
                "room_height": room_h,
            })
            imported_name    = result.get("name", blender_name)
            # blend_import.py returns the ACTUAL Blender names after auto-suffixing.
            # Using these directly is far more reliable than prefix-based search,
            # because Blender appends ".001"/".002" when names collide.
            imported_objects = result.get("imported_objects", [imported_name])

            target_z       = float(location[2]) if location else 0.0
            obj_names_repr = repr(imported_objects)

            # run_python: floor-align ve oda yükseklik sınırı.
            # NOT: ref_h ölçeklemesi kaldırıldı — blend_import.py artık
            # catalog_dims + EMPTY transform baking ile boyutu doğru getiriyor.
            _scale_script = f"""
import bpy, mathutils

target_z = {target_z}
room_h   = {room_h}

# Objeyi bul (imported_objects listesi en güvenilir)
obj_names = {obj_names_repr}
asset_objs = [o for n in obj_names for o in [bpy.data.objects.get(n)] if o]
if not asset_objs:
    prefix = {blender_name!r}
    asset_objs = [o for o in bpy.data.objects
                  if o.name == prefix or o.name.startswith(prefix + '_') or o.name.startswith(prefix + '.')]
root_obj = bpy.data.objects.get({imported_name!r})
if not root_obj and asset_objs:
    root_obj = asset_objs[0]

if root_obj:
    mesh_objs = [o for o in asset_objs if o.type in ('MESH','CURVE','SURFACE')]
    targets   = mesh_objs or [root_obj]

    def _cur_h():
        try:
            dep = bpy.context.evaluated_depsgraph_get()
            zs = [(o.evaluated_get(dep).matrix_world @ mathutils.Vector(c)).z
                  for o in targets for c in o.bound_box]
            return max(zs) - min(zs) if zs else 0
        except Exception:
            v = [o.dimensions.z for o in targets if o.dimensions.z > 1e-6]
            return max(v) if v else 0

    def _scale(r):
        sx, sy, sz = root_obj.scale
        root_obj.scale = (sx * r, sy * r, sz * r)

    # 1) Oda yükseklik sınırı — nesne tavana çakmasın
    if room_h > 0.1:
        h = _cur_h()
        if h > room_h * 0.97 and h > 0:
            _scale((room_h * 0.96) / h)

    # 2) Floor alignment
    try:
        dep = bpy.context.evaluated_depsgraph_get()
        min_z = min((o.evaluated_get(dep).matrix_world @ mathutils.Vector(c)).z
                    for o in targets for c in o.bound_box)
    except Exception:
        min_z = min(o.location.z + min(c[2] for c in o.bound_box) * o.scale.z
                    for o in targets)
    if min_z < 1e9 and abs(min_z - target_z) > 0.005:
        dz = target_z - min_z
        aset = {{o.name for o in asset_objs}}
        for o in asset_objs:
            if o.parent is None or o.parent.name not in aset:
                o.location.z += dz
"""
            try:
                _call_blender("run_python", {"script": _scale_script}, timeout=20.0)
            except Exception:
                pass  # non-critical

            loc = result.get("location", location)
            placed.append(
                f"  {slot:20s}  {piece.get('name','')[:28]:28s}"
                f"  @ ({loc[0]:+.2f}, {loc[1]:+.2f}, {loc[2]:+.2f})"
            )
        except Exception as e:
            errors.append(f"  {slot}: import failed — {e}")

    lines = [f"Imported {len(placed)}/{len(plan)} furniture pieces:"]
    lines += placed
    if errors:
        lines.append("Issues:")
        lines += errors
    return "\n".join(lines)


def get_3d_cursor_position() -> str:
    """Read the current 3D cursor position from Blender.

    Use this to measure room origins inside a house model:
      1. Import the house in Blender
      2. Shift+Right Click to place cursor at room center
      3. Call this function to get the coordinates
      4. Use those as origin_offset_m for that room in Catalog.json
    """
    result = _call_blender("get_3d_cursor", {})
    loc = result.get("location", [0, 0, 0])
    copy = result.get("copy_paste", str(loc))
    return (
        f"3D Cursor position: {copy}\n"
        f"Use this as origin_offset_m for the room in Catalog.json."
    )


def test_asset_facing(asset_id: str) -> str:
    """Import an asset at the origin with zero rotation so you can see its default facing direction.

    After calling this, look at the object in Blender:
      - Numpad 7  = top view  (see which axis the 'front' faces)
      - Numpad 1  = front view (-Y direction is toward you)

    Use the result to set facing_correction_z in Catalog.json:
      desired_facing  | model_default  | correction
      south (-Y)      | south (-Y)     | 0
      south (-Y)      | north (+Y)     | 180
      south (-Y)      | east (+X)      | 270
      south (-Y)      | west (-X)      | 90

    Args:
        asset_id: Asset ID from catalog (e.g. 'desk_metal_industrial_01')
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from mcp_server import catalog

    asset = catalog.get_asset_by_id(asset_id)
    if not asset:
        return f"Asset '{asset_id}' not found."

    abs_file = catalog.resolve_file_path(asset["file"])
    if not abs_file.exists():
        return f"File not found: {abs_file}"

    # Apply rotation_correction so test import shows the model upright
    rc = asset.get("rotation_correction", [0, 0, 0])
    # For test import use facing_correction_z so it previews the corrected orientation
    facing_z = float(
        asset.get("facing_correction_z")
        or (asset.get("placement") or {}).get("facing_correction_z") or 0
    )
    test_rotation = [float(rc[0]), float(rc[1]), facing_z + float(rc[2])]
    imp_scale = float(asset.get("import_scale", 1.0))
    # Note: test_facing IS the one place we DO apply facing_z directly (no layout_tools involved)

    result = _call_blender("test_asset_facing", {
        "file_path": str(abs_file),
        "name": asset_id,
        "rotation": test_rotation,
        "scale": imp_scale,
    })

    # Apply scale correction so the test import also appears at the right size
    dims = asset.get("dimensions_m") or {}
    cw, cd, ch = dims.get("width"), dims.get("depth"), dims.get("height")
    if cw and cd and ch:
        cat_max = max(float(cw), float(cd), float(ch))
        _scale_script = f"""
import bpy
obj = bpy.data.objects.get({asset_id!r})
if not obj:
    for o in bpy.data.objects:
        if o.name.startswith({asset_id!r}):
            obj = o; break
if obj:
    actual_max = max(obj.dimensions.x, obj.dimensions.y, obj.dimensions.z)
    if actual_max > 1e-6:
        ratio = {cat_max} / actual_max
        if not (0.95 < ratio < 1.05):
            sx, sy, sz = obj.scale
            obj.scale = (sx*ratio, sy*ratio, sz*ratio)
"""
        try:
            _call_blender("run_python", {"script": _scale_script}, timeout=10.0)
        except Exception:
            pass

    return (
        f"Asset '{asset['name']}' imported at origin with rot_z=0.\n"
        f"Object name in Blender: {result.get('name')}\n"
        f"Hint: {result.get('hint', '')}\n\n"
        f"After inspecting, update Catalog.json:\n"
        f'  "{asset_id}": {{ "facing_correction_z": <value> }}'
    )


def get_blender_scene_state() -> str:
    """Get all mesh objects currently in the Blender scene with their positions and sizes."""
    result = _call_blender("list_scene_objects", {})
    objects = result.get("objects", [])
    if not objects:
        return "Blender scene is empty — no mesh objects found."
    lines = [f"Scene contains {result.get('count', len(objects))} object(s):"]
    for obj in objects:
        loc = obj["location"]
        dim = obj["dims_m"]
        vis = "" if obj.get("visible", True) else " [hidden]"
        lines.append(
            f"  {obj['name']:35s}"
            f"  pos({loc[0]:+.2f},{loc[1]:+.2f},{loc[2]:+.2f})"
            f"  {dim[0]:.2f}×{dim[1]:.2f}×{dim[2]:.2f}m{vis}"
        )
    return "\n".join(lines)
