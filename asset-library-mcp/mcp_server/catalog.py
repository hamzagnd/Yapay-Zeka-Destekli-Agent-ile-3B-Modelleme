"""Catalog reader — loads and queries Catalog.json from the asset library.

v2 schema adds: semantic_tags, room_types, is_container, footprint, placement block,
compatible_with, scale_class, container_meta. Legacy fields (dimensions_m, origin,
facing_correction_z) are still accepted and surfaced via normalized helpers.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Resolve the library root: env-var override, else sibling of this package
_ENV_KEY = "ASSET_LIBRARY_DIR"
_DEFAULT_DIR = Path(__file__).parent.parent.parent  # …/asset_library/


def _library_root() -> Path:
    env = os.environ.get(_ENV_KEY)
    return Path(env) if env else _DEFAULT_DIR


def _catalog_path() -> Path:
    return _library_root() / "Catalog.json"


def load_catalog() -> Dict[str, Any]:
    """Read Catalog.json from disk on every call so edits are picked up immediately."""
    path = _catalog_path()
    if not path.exists():
        raise FileNotFoundError(f"Catalog.json not found at {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def reload_catalog() -> Dict[str, Any]:
    return load_catalog()


def get_all_assets() -> List[Dict[str, Any]]:
    return load_catalog().get("assets", [])


def get_asset_by_id(asset_id: str) -> Optional[Dict[str, Any]]:
    for asset in get_all_assets():
        if asset.get("id") == asset_id:
            return asset
    return None


def get_categories() -> Dict[str, List[str]]:
    return load_catalog().get("categories_taxonomy", {})


def resolve_file_path(relative_path: str) -> Path:
    """Convert a catalog-relative file path to an absolute Path."""
    return _library_root() / relative_path


# ── v2 normalization helpers ─────────────────────────────────────────────

def get_forward_axis(asset: Dict[str, Any]) -> str:
    """Return the forward axis for an asset, accepting both v2 and legacy shape."""
    p = asset.get("placement") or {}
    return p.get("forward_axis", "+Y")


_FORWARD_AXIS_TO_CORRECTION_Z = {"+Y": 0.0, "-Y": 180.0, "+X": 270.0, "-X": 90.0}


def get_facing_correction_z(asset: Dict[str, Any]) -> float:
    """Return Z rotation correction (degrees), derived from forward_axis.

    forward_axis is the single source of truth for which way the model points;
    the correction needed to make it face +Y in world space follows directly.
    The written facing_correction_z field is ignored to prevent drift between
    the two values when one is edited and the other isn't.
    """
    return _FORWARD_AXIS_TO_CORRECTION_Z.get(get_forward_axis(asset), 0.0)


def get_footprint(asset: Dict[str, Any]) -> Dict[str, float]:
    """Return footprint dims with sensible defaults. v2 reads asset['footprint'],
    falls back to dimensions_m."""
    fp = asset.get("footprint")
    if fp:
        return {
            "width_m":  float(fp.get("width_m", 1.0)),
            "depth_m":  float(fp.get("depth_m", 0.8)),
            "height_m": float(fp.get("height_m", 0.8)),
            "clearance_front_m": float(fp.get("clearance_front_m", 0.0)),
            "clearance_sides_m": float(fp.get("clearance_sides_m", 0.0)),
        }
    dim = asset.get("dimensions_m", {})
    return {
        "width_m":  float(dim.get("width", 1.0)),
        "depth_m":  float(dim.get("depth", 0.8)),
        "height_m": float(dim.get("height", 0.8)),
        "clearance_front_m": 0.0,
        "clearance_sides_m": 0.0,
    }


def is_container(asset: Dict[str, Any]) -> bool:
    if asset.get("is_container"):
        return True
    # Legacy detection: architecture category with rooms[]
    return asset.get("category") == "architecture" and bool(asset.get("rooms"))


def get_interior_bbox(asset: Dict[str, Any]) -> Optional[Dict[str, List[float]]]:
    """Return interior_bbox_local for a container asset, or None."""
    cm = asset.get("container_meta") or {}
    bbox = cm.get("interior_bbox_local")
    if bbox and "min" in bbox and "max" in bbox:
        return bbox
    return None


def get_room_interior_bbox(asset: Dict[str, Any], room_id: str) -> Optional[Dict[str, List[float]]]:
    """Return interior_bbox_local for a specific room, falling back to container bbox."""
    for r in asset.get("rooms", []):
        if r.get("room_id") == room_id:
            bbox = r.get("interior_bbox_local")
            if bbox:
                return bbox
            break
    return get_interior_bbox(asset)


def search_assets(
    query: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    style: Optional[str] = None,
    tags: Optional[List[str]] = None,
    semantic_tag: Optional[str] = None,
    room_type: Optional[str] = None,
    is_container_flag: Optional[bool] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Filter catalog assets by any combination of criteria.

    v2 additions:
        semantic_tag: matches semantic_tags[]
        room_type:    matches room_types[]
        is_container_flag: True/False to filter only containers / only furniture
    """
    results = get_all_assets()

    if category:
        results = [a for a in results if a.get("category", "").lower() == category.lower()]

    if subcategory:
        results = [a for a in results if a.get("subcategory", "").lower() == subcategory.lower()]

    if style:
        style_low = style.lower()
        results = [
            a for a in results
            if any(style_low in s.lower() for s in a.get("style", []))
        ]

    if tags:
        tags_low = [t.lower() for t in tags]
        results = [
            a for a in results
            if any(t in [x.lower() for x in a.get("tags", [])] for t in tags_low)
        ]

    if semantic_tag:
        st_low = semantic_tag.lower()
        results = [
            a for a in results
            if any(st_low == t.lower() for t in a.get("semantic_tags", []))
        ]

    if room_type:
        rt_low = room_type.lower()
        results = [
            a for a in results
            # Empty room_types = allowed in any room (don't exclude these)
            if not a.get("room_types")
            or any(rt_low == r.lower() for r in a.get("room_types", []))
        ]

    if is_container_flag is not None:
        results = [a for a in results if is_container(a) == is_container_flag]

    if query:
        q = query.lower()
        results = [
            a for a in results
            if (
                q in a.get("name", "").lower()
                or q in a.get("id", "").lower()
                or q in a.get("category", "").lower()
                or q in a.get("subcategory", "").lower()
                or any(q in s.lower() for s in a.get("style", []))
                or any(q in t.lower() for t in a.get("tags", []))
                or any(q in t.lower() for t in a.get("semantic_tags", []))
                or any(q in r.lower() for r in a.get("room_types", []))
            )
        ]

    return results[:limit]


def list_companions(asset_id: str) -> List[Dict[str, Any]]:
    """For asset X, find assets whose subcategory is in X.compatible_with[]."""
    a = get_asset_by_id(asset_id)
    if not a:
        return []
    companions: List[Dict[str, Any]] = []
    for subcat in a.get("compatible_with", []):
        companions.extend(search_assets(subcategory=subcat, limit=3))
    return companions
