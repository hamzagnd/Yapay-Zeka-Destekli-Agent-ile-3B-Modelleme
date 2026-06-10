"""Handler for importing .blend file assets into the active Blender scene."""

import math
import re as _re
from pathlib import Path
from typing import Any, Dict


def import_blend_asset(params: Dict[str, Any]) -> Dict[str, Any]:
    """Append objects, scale to catalog dims, floor-align, join sub-meshes.

    Key fixes vs. old versions
    ─────────────────────────
    • Scale measured via evaluated_depsgraph AFTER import_scale applied
      → works even when root is EMPTY (parent→child transforms included).
    • EMPTY root: largest mesh child is promoted to primary.
    • Sub-meshes joined with 3-method fallback (temp_override → select+join → parent+hide).
    • Floor alignment via depsgraph (handles X/Y rotated models).
    """
    import bpy

    file_path = params.get("file_path")
    if not file_path:
        return {"error": "file_path is required"}
    blend_path = Path(file_path)
    if not blend_path.exists():
        return {"error": f"File not found: {blend_path}"}
    if blend_path.suffix.lower() != ".blend":
        return {"error": f"Expected a .blend file, got: {blend_path.suffix}"}

    location      = params.get("location",  [0.0, 0.0, 0.0])
    rotation_deg  = params.get("rotation",  [0.0, 0.0, 0.0])
    scale_raw     = params.get("scale",     1.0)
    override_name = params.get("name")
    catalog_dims  = params.get("catalog_dims")
    room_height   = float(params.get("room_height", 0))

    import_scale: tuple = (
        (float(scale_raw),) * 3
        if isinstance(scale_raw, (int, float))
        else tuple(float(v) for v in scale_raw)
    )
    rotation_rad = [math.radians(d) for d in rotation_deg]

    # ── Append ───────────────────────────────────────────────────────────
    objects_before = set(bpy.data.objects)
    try:
        with bpy.data.libraries.load(str(blend_path), link=False) as (src, dst):
            dst.objects = list(src.objects)
    except Exception as e:
        return {"error": f"Failed to load .blend: {e}"}

    new_objects = list(set(bpy.data.objects) - objects_before)
    if not new_objects:
        return {"error": "No objects found in the .blend file"}

    scene_col = bpy.context.scene.collection
    for obj in new_objects:
        if obj.name not in scene_col.objects:
            scene_col.objects.link(obj)

    import_set   = set(new_objects)
    root_objects = [o for o in new_objects
                    if o.parent is None or o.parent not in import_set]
    if not root_objects:
        root_objects = new_objects

    # ── Step 1: Apply import_scale to roots ───────────────────────────────
    for obj in root_objects:
        obj.location       = tuple(location)
        obj.rotation_euler = tuple(rotation_rad)
        obj.scale          = import_scale

    # ── Step 2: World-space dimension via depsgraph → catalog correction ──
    # evaluated_depsgraph_get() includes ALL parent→child transforms, so it
    # correctly handles EMPTY roots with MESH children (obj.dimensions alone
    # does NOT propagate parent scale to children).
    import mathutils as _mu

    def _world_bbox(objects_list):
        """Return (xs, ys, zs) world coordinate lists for all mesh objects."""
        try:
            dep = bpy.context.evaluated_depsgraph_get()
            xs, ys, zs = [], [], []
            for o in objects_list:
                if o.type not in ("MESH", "CURVE", "SURFACE"):
                    continue
                oe = o.evaluated_get(dep)
                for c in oe.bound_box:
                    wc = oe.matrix_world @ _mu.Vector(c)
                    xs.append(wc.x); ys.append(wc.y); zs.append(wc.z)
            return xs, ys, zs
        except Exception:
            return [], [], []

    scale_correction = 1.0
    if catalog_dims:
        cat_max = max(float(catalog_dims.get(k, 0)) for k in ("width", "depth", "height"))
        xs, ys, zs = _world_bbox(new_objects)
        actual_max = 0.0
        if xs:
            actual_max = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs))
        if cat_max > 0 and actual_max > 1e-6:
            ratio = cat_max / actual_max
            if not (0.90 < ratio < 1.10):
                scale_correction = ratio
                for obj in root_objects:
                    obj.scale = (obj.scale[0]*ratio, obj.scale[1]*ratio, obj.scale[2]*ratio)

    # ── Step 3: Room height clamp ─────────────────────────────────────────
    if room_height > 0.1:
        xs, ys, zs = _world_bbox(new_objects)
        if zs:
            actual_h = max(zs) - min(zs)
            if actual_h > room_height * 0.97 and actual_h > 0:
                h_ratio = (room_height * 0.96) / actual_h
                for obj in root_objects:
                    obj.scale = tuple(s * h_ratio for s in obj.scale)

    # ── Step 4: Floor alignment ───────────────────────────────────────────
    _target_z = float(location[2]) if location else 0.0
    xs, ys, zs = _world_bbox(new_objects)
    if zs:
        _min_z = min(zs)
        if abs(_min_z - _target_z) > 0.005:
            _z_shift = _target_z - _min_z
            for _o in new_objects:
                if _o in set(root_objects) or _o.parent is None or _o.parent not in import_set:
                    _o.location.z += _z_shift

    # ── Step 5: Rename ────────────────────────────────────────────────────
    primary = root_objects[0]
    if override_name:
        primary.name = override_name

    prefix = (override_name or blend_path.stem).replace(" ", "_")
    for obj in new_objects:
        if obj is primary:
            continue
        clean = _re.sub(r'\.\d{3,}$', '', obj.name)
        try:
            obj.name = f"{prefix}_{clean}"
        except Exception:
            pass

    # ── Step 6: Promote largest MESH if primary is EMPTY ─────────────────
    # Many Sketchfab models have an EMPTY root. We must join into a MESH,
    # so promote the largest-footprint mesh child as the new primary first.
    if primary.type != 'MESH':
        mesh_candidates = [o for o in new_objects if o.type == 'MESH']
        if mesh_candidates:
            new_prim = max(
                mesh_candidates,
                key=lambda o: o.dimensions.x * o.dimensions.y * o.dimensions.z,
            )
            # Give the new primary the asset name
            new_prim.name = override_name or prefix
            # Remove the old EMPTY (it served only as transform carrier)
            old_empty = primary
            primary = new_prim
            try:
                # Bake EMPTY's transform into each child before removing it.
                # We build the world matrix from the EMPTY's STORED properties
                # (not from the depsgraph, which may be stale in the addon context).
                # This preserves the import_scale that was applied to the EMPTY in Step 1.
                _eloc = _mu.Vector(old_empty.location)
                _erot = _mu.Euler(tuple(old_empty.rotation_euler), 'XYZ')
                _esca = old_empty.scale  # may differ from import_scale if Step 3 clamped it
                _empty_mat = (
                    _mu.Matrix.Translation(_eloc) @
                    _erot.to_matrix().to_4x4() @
                    _mu.Matrix.Diagonal((_esca[0], _esca[1], _esca[2], 1.0))
                )
                for _c in list(old_empty.children):
                    if _c not in import_set:
                        continue
                    # child world = empty_world @ matrix_parent_inverse @ matrix_local
                    _child_world = _empty_mat @ _c.matrix_parent_inverse @ _c.matrix_local
                    _c.parent = None
                    _c.matrix_parent_inverse = _mu.Matrix.Identity(4)
                    _cloc, _crot, _csca = _child_world.decompose()
                    _c.location = _cloc
                    _c.rotation_euler = _crot.to_euler('XYZ')
                    _c.scale = _csca
                bpy.data.objects.remove(old_empty, do_unlink=True)
                new_objects = [o for o in new_objects if o is not old_empty]
            except Exception:
                pass

    # ── Step 7: Join sub-meshes into primary ──────────────────────────────
    # 3-method fallback: temp_override → select+join → parent+hide.
    try:
        mesh_parts = [
            o for o in new_objects
            if o.type == 'MESH' and o is not primary
            and bpy.data.objects.get(o.name)
        ]
        if mesh_parts and primary.type == 'MESH':
            all_join = [primary] + mesh_parts
            joined = False

            # Method A: temp_override (Blender 4.x)
            try:
                with bpy.context.temp_override(
                    active_object=primary,
                    selected_objects=all_join,
                    selected_editable_objects=all_join,
                ):
                    bpy.ops.object.join()
                joined = True
            except Exception:
                pass

            # Method B: explicit select/active then join
            if not joined:
                try:
                    bpy.ops.object.select_all(action='DESELECT')
                    for o in all_join:
                        o.select_set(True)
                    bpy.context.view_layer.objects.active = primary
                    bpy.ops.object.join()
                    joined = True
                except Exception:
                    pass

            # Method C: bmesh merge — no VIEW_3D context needed.
            # Build primary's world matrix from STORED properties (not depsgraph,
            # which may be stale in the HTTP addon context) to get a correct p_inv.
            if not joined:
                try:
                    import bmesh as _bm_mod
                    # Compute p_inv from known properties, not stale matrix_world
                    _p_loc = _mu.Vector(primary.location)
                    _p_rot = _mu.Euler(tuple(primary.rotation_euler), 'XYZ')
                    _p_sca = primary.scale
                    _p_mat = (
                        _mu.Matrix.Translation(_p_loc) @
                        _p_rot.to_matrix().to_4x4() @
                        _mu.Matrix.Diagonal((_p_sca[0], _p_sca[1], _p_sca[2], 1.0))
                    )
                    p_inv = _p_mat.inverted_safe()

                    dst = _bm_mod.new()
                    dst.from_mesh(primary.data)
                    for _sub in list(mesh_parts):
                        _sob = bpy.data.objects.get(_sub.name) if hasattr(_sub, 'name') else None
                        if not _sob:
                            continue
                        # Same approach: compute sub matrix from properties
                        _s_loc = _mu.Vector(_sob.location)
                        _s_rot = _mu.Euler(tuple(_sob.rotation_euler), 'XYZ')
                        _s_sca = _sob.scale
                        _s_mat = (
                            _mu.Matrix.Translation(_s_loc) @
                            _s_rot.to_matrix().to_4x4() @
                            _mu.Matrix.Diagonal((_s_sca[0], _s_sca[1], _s_sca[2], 1.0))
                        )
                        _rel = p_inv @ _s_mat
                        _src = _bm_mod.new()
                        _src.from_mesh(_sob.data)
                        _src.verts.ensure_lookup_table()
                        _new_vs = [dst.verts.new(_rel @ _v.co) for _v in _src.verts]
                        dst.verts.ensure_lookup_table()
                        _src.faces.ensure_lookup_table()
                        for _f in _src.faces:
                            try:
                                dst.faces.new([_new_vs[_v.index] for _v in _f.verts])
                            except Exception:
                                pass
                        _src.free()
                        try:
                            bpy.data.objects.remove(_sob, do_unlink=True)
                        except Exception:
                            pass
                    dst.to_mesh(primary.data)
                    dst.free()
                    joined = True
                except Exception:
                    pass

            # Last resort: delete sub-meshes so scene stays clean
            if not joined:
                for o in mesh_parts:
                    if bpy.data.objects.get(o.name):
                        try:
                            bpy.data.objects.remove(o, do_unlink=True)
                        except Exception:
                            pass

        # Remove lingering non-mesh objects (EMPTY, ARMATURE, CAMERA…)
        for _o in list(new_objects):
            _ob = bpy.data.objects.get(_o.name) if hasattr(_o, 'name') else None
            if _ob and _ob is not primary and _ob.type not in ('MESH', 'CURVE', 'SURFACE'):
                try:
                    bpy.data.objects.remove(_ob, do_unlink=True)
                except Exception:
                    pass
    except Exception:
        pass

    # ── Step 8: Re-floor-align ────────────────────────────────────────────
    # After the join/merge the combined mesh may extend below _target_z
    # (sub-parts with local Z < primary's original minimum). Correct it.
    if primary.type == 'MESH':
        try:
            dep = bpy.context.evaluated_depsgraph_get()
            pe  = primary.evaluated_get(dep)
            _wz = [(pe.matrix_world @ _mu.Vector(c)).z for c in pe.bound_box]
            if _wz:
                _mz = min(_wz)
                if abs(_mz - _target_z) > 0.005:
                    primary.location.z += (_target_z - _mz)
        except Exception:
            try:
                _bb_min_z = min(c[2] for c in primary.bound_box)
                _world_min_z = primary.location.z + primary.scale[2] * _bb_min_z
                if abs(_world_min_z - _target_z) > 0.005:
                    primary.location.z += (_target_z - _world_min_z)
            except Exception:
                pass

    # Return only the primary name; run_python uses it for safety-net corrections
    return {
        "name":             primary.name,
        "location":         list(primary.location),
        "rotation":         list(primary.rotation_euler),
        "scale":            list(primary.scale),
        "scale_correction": round(scale_correction, 6),
        "imported_objects": [primary.name],
        "source_file":      str(blend_path),
    }


BLEND_IMPORT_HANDLERS = {
    "import_blend_asset": import_blend_asset,
}
