"""FastAPI server — exposes the Interior Architect Team via HTTP for the HTML UI."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Asset Library Interior Design API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_VIEWS_DIR     = Path(__file__).parent.parent / "generated_views"
_VIEWS_CATALOG = _VIEWS_DIR / "catalog.json"
_VIEWS_DIR.mkdir(exist_ok=True)
app.mount("/generated_views", StaticFiles(directory=str(_VIEWS_DIR)), name="generated_views")

_THUMBS_DIR = Path(__file__).parent.parent / "thumbnails"
_THUMBS_DIR.mkdir(exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=str(_THUMBS_DIR)), name="thumbnails")

_UI_DIR = Path(__file__).parent.parent / "ui"
_UI_DIR.mkdir(exist_ok=True)
app.mount("/ui", StaticFiles(directory=str(_UI_DIR)), name="ui")

# ── Asset Manager paths ───────────────────────────────────────────
# api.py lives at  asset-library-mcp/agents/api.py
# asset_library root is two levels up: parent.parent.parent
_ASSET_LIB_DIR    = Path(__file__).parent.parent.parent   # …/asset_library/
_ZIP_DIR          = _ASSET_LIB_DIR / "zip"
_CATALOG_PATH     = _ASSET_LIB_DIR / "Catalog.json"
_ADD_ASSET_SCRIPT = _ASSET_LIB_DIR / "add_asset.py"

# In-memory job registry: job_id -> { status, lines, error }
_am_jobs: dict = {}
_am_jobs_lock = __import__("threading").Lock()

import threading as _threading
_catalog_lock = _threading.Lock()

def _catalog_read():
    import json as _j
    if not _VIEWS_CATALOG.exists():
        return []
    try:
        return _j.loads(_VIEWS_CATALOG.read_text(encoding="utf-8"))
    except Exception:
        return []

def _catalog_append(entry: dict):
    import json as _j
    with _catalog_lock:
        data = _catalog_read()
        data.append(entry)
        _VIEWS_CATALOG.write_text(
            _j.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


@app.get("/asset-manager")
@app.get("/asset-manager.html", response_class=HTMLResponse)
def get_asset_manager():
    p = _UI_DIR / "asset-manager.html"
    if p.exists():
        return FileResponse(p)
    return HTMLResponse("asset-manager.html not found", status_code=404)


@app.get("/asset-manager/zips")
def list_zips():
    """Return all .zip files in the zip/ directory with quick metadata."""
    import zipfile as _zf, re as _re
    if not _ZIP_DIR.exists():
        return {"zips": []}
    result = []
    for z in sorted(_ZIP_DIR.glob("*.zip")):
        try:
            with _zf.ZipFile(z) as zf:
                names    = zf.namelist()
                blends   = [n for n in names if n.endswith(".blend")]
                textures = [n for n in names if _re.search(r"\.(jpg|jpeg|png|exr|hdr|tiff?|tga|bmp)$", n, _re.I)]
                size_mb  = round(z.stat().st_size / 1_048_576, 1)
            result.append({
                "filename":   z.name,
                "filepath":   str(z),
                "size_mb":    size_mb,
                "blend_count": len(blends),
                "tex_count":   len(textures),
                "blends":      blends,
            })
        except Exception as e:
            result.append({"filename": z.name, "filepath": str(z), "error": str(e)})
    return {"zips": result}


@app.post("/asset-manager/zip/preview")
def preview_zip(body: dict):
    """List contents of a zip file."""
    import zipfile as _zf, re as _re
    filepath = (body.get("filepath") or "").strip()
    if not filepath or not Path(filepath).exists():
        return {"error": "Dosya bulunamadı"}
    try:
        with _zf.ZipFile(filepath) as zf:
            names    = zf.namelist()
            blends   = [n for n in names if n.endswith(".blend")]
            textures = [n for n in names if _re.search(r"\.(jpg|jpeg|png|exr|hdr|tiff?|tga|bmp)$", n, _re.I)]
            others   = [n for n in names if not n.endswith("/") and n not in blends + textures]
        stem = Path(blends[0]).stem if blends else Path(filepath).stem
        import re as _re2
        base_id = _re2.sub(r"[_\-]?\d+k$", "", stem, flags=_re2.I).lower()
        default_name = stem.replace("_", " ").title()
        return {
            "blends":       blends,
            "textures":     textures,
            "others":       others,
            "default_name": default_name,
            "default_id":   base_id,
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/asset-manager/add")
def start_add_asset(body: dict):
    """Start add_asset.py as a background subprocess. Returns job_id for polling."""
    import subprocess, sys, uuid, threading

    filepath  = (body.get("filepath") or "").strip()
    name      = (body.get("name") or "").strip()
    asset_id  = (body.get("id")   or "").strip()
    use_llm   = body.get("use_llm", True)

    if not filepath or not Path(filepath).exists():
        return {"error": "Zip dosyası bulunamadı"}

    job_id = str(uuid.uuid4())[:8]
    with _am_jobs_lock:
        _am_jobs[job_id] = {"status": "running", "lines": [], "error": None}

    cmd = [sys.executable, str(_ADD_ASSET_SCRIPT), filepath, "--quick"]
    if name:
        cmd += ["--name", name]
    if asset_id:
        cmd += ["--id", asset_id]
    if not use_llm:
        cmd.append("--no-llm")

    def _run():
        try:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env, cwd=str(_ASSET_LIB_DIR),
            )
            for raw_line in proc.stdout:
                line = raw_line.rstrip()
                with _am_jobs_lock:
                    _am_jobs[job_id]["lines"].append(line)
            proc.wait()
            ok = proc.returncode == 0
            with _am_jobs_lock:
                _am_jobs[job_id]["status"] = "done" if ok else "error"
            if ok:
                # Flush catalog cache so next API call sees the new asset
                try:
                    from mcp_server import catalog as _cat
                    _cat.reload_catalog()
                except Exception:
                    pass
        except Exception as e:
            with _am_jobs_lock:
                _am_jobs[job_id]["status"] = "error"
                _am_jobs[job_id]["error"]  = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}


@app.get("/asset-manager/job/{job_id}")
def get_job(job_id: str):
    """Poll job status and streamed output."""
    with _am_jobs_lock:
        job = _am_jobs.get(job_id)
    if not job:
        return {"error": "Job bulunamadı"}
    return {
        "status":   job["status"],
        "output":   "\n".join(job["lines"]),
        "error":    job["error"],
        "asset_id": job.get("asset_id"),
    }


@app.get("/asset-manager/catalog")
def get_catalog_assets():
    """Return all assets from Catalog.json (id, name, category, subcategory, dimensions)."""
    if not _CATALOG_PATH.exists():
        return {"assets": []}
    import json as _j
    try:
        content = _CATALOG_PATH.read_text(encoding="utf-8").strip()
        if not content:
            return {"error": "Catalog.json dosyası boş", "assets": []}
        data   = _j.loads(content)
        assets = data.get("assets", data) if isinstance(data, dict) else data
        slim   = [
            {
                "id":          a.get("id"),
                "name":        a.get("name"),
                "category":    a.get("category"),
                "subcategory": a.get("subcategory"),
                "style":       a.get("style", []),
                "dimensions":  a.get("dimensions_m", {}),
                "file":        a.get("file", ""),
                "file_exists": (_ASSET_LIB_DIR / a.get("file", "")).exists() if a.get("file") else False,
                "proportion_warning": bool(a.get("proportion_warning", False)),
                "room_types":  a.get("room_types", []),
            }
            for a in assets if isinstance(a, dict)
        ]
        return {"assets": slim, "count": len(slim)}
    except _j.JSONDecodeError as je:
        return {"error": f"Catalog.json ayrıştırma hatası: {str(je)} (Dosya içeriği bozuk olabilir)"}
    except Exception as e:
        return {"error": f"Katalog okuma hatası: {str(e)}"}


@app.get("/")
@app.get("/prompt_builder.html", response_class=HTMLResponse)
def get_ui():
    """Serve the UI — new split version from ui/index.html, falling back to prompt_builder.html."""
    new_path = Path(__file__).parent.parent / "ui" / "index.html"
    if new_path.exists():
        return FileResponse(new_path)
    # Fallback to legacy monolithic file
    html_path = Path(__file__).parent.parent / "prompt_builder.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("prompt_builder.html not found", status_code=404)


class DesignRequest(BaseModel):
    prompt: str
    llm: str = "gemini"
    floor_plan_image: Optional[str] = None  # base64 PNG of the yapboz canvas


class DesignResponse(BaseModel):
    result: str
    llm_used: str
    error: Optional[str] = None


@app.get("/health")
def health():
    from .tools.blender_tools import check_blender_connection
    blender_ok = "running" in check_blender_connection()
    models = []
    if os.getenv("GOOGLE_API_KEY"):
        models.append("gemini")
    if os.getenv("ANTHROPIC_API_KEY"):
        models.append("claude")
    return {
        "status": "ok",
        "blender_connected": blender_ok,
        "available_models": models,
    }


@app.get("/catalog/houses")
def get_houses():
    """List all architectural/house assets in the catalog."""
    from .tools.catalog_tools import list_house_assets
    return {"houses": list_house_assets()}


@app.get("/catalog/house/{house_id}/rooms")
def get_house_rooms(house_id: str):
    """List all rooms defined for a house asset."""
    from .tools.catalog_tools import list_house_rooms
    return {"rooms": list_house_rooms(house_id)}


@app.get("/blender/cursor")
def read_3d_cursor():
    """Read the current 3D cursor position from Blender."""
    from .tools.blender_tools import get_3d_cursor_position
    return {"result": get_3d_cursor_position()}


@app.get("/blender/scene")
def get_blender_scene():
    """List all mesh objects in the Blender scene with positions and dimensions."""
    import httpx
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.post("http://localhost:8766",
                            json={"action": "list_scene_objects", "params": {}})
            r.raise_for_status()
            result = r.json()
            if not result.get("success"):
                return {"error": result.get("error", "Blender error"), "objects": [], "count": 0}
            return result.get("result", {"objects": [], "count": 0})
    except Exception as e:
        return {"error": str(e), "objects": [], "count": 0}


@app.get("/blender/scene/analyze")
def analyze_blender_scene():
    """Fetch scene objects, cluster by asset using spatial+name algorithm, return grouped structure."""
    import httpx, re, json as _json, math

    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.post("http://localhost:8766",
                            json={"action": "list_scene_objects", "params": {}})
            r.raise_for_status()
            result = r.json()
            if not result.get("success"):
                return {"error": result.get("error", "Blender error"),
                        "groups": [], "objects": [], "count": 0, "analysis": ""}
            objects = result.get("result", {}).get("objects", [])
    except Exception as e:
        return {"error": str(e), "groups": [], "objects": [], "count": 0, "analysis": ""}

    visible = [o for o in objects if o.get("visible", True)]
    if not visible:
        return {"groups": [], "objects": objects, "count": 0, "analysis": "Sahne boş."}

    all_names = [o["name"] for o in visible]

    # ── Helper: parse Blender's .NNN duplicate suffix ─────────────
    # "metal_office_desk.001" → base="metal_office_desk", inst=1
    # "metal_office_desk"     → base="metal_office_desk", inst=0
    # Two objects with the same inst share the same import batch;
    # objects with different inst values are SEPARATE physical instances.
    def _parse(name: str):
        m = re.match(r'^(.*?)(?:\.(\d{3}))?$', name)
        return m.group(1), (int(m.group(2)) if m.group(2) else 0)

    def _dist2d(a: dict, b: dict) -> float:
        dx = a["location"][0] - b["location"][0]
        dy = a["location"][1] - b["location"][1]
        return math.sqrt(dx * dx + dy * dy)

    # ── Separate Room objects from furniture ──────────────────────
    room_objs = [o for o in visible if re.match(r'^Room_', o["name"], re.I)]
    furn_objs = [o for o in visible if not re.match(r'^Room_', o["name"], re.I)]

    # ── Spatial + name clustering for furniture ───────────────────
    # Two objects are in the same group iff ALL three conditions hold:
    #   1. Same Blender instance number (same .NNN suffix, or both have none)
    #   2. Name prefix relationship: one base is a prefix of the other (sub-parts)
    #      — allows both "_" and " " (space) as sub-part boundary separators
    #      — "desk" ≠ prefix of "desk_lamp" (different word after boundary)
    #   3. Their centers are within EPS meters (physically part of the same object)
    #
    # EPS is kept tight (0.25m) so only mesh parts that are literally co-located
    # (sub-meshes, LODs, baked duplicates of the SAME import) get merged.
    # Two separately-placed objects of the same model will be ≥ their own footprint
    # apart and will correctly remain as separate groups.
    EPS = 0.25  # meters — tighter than before to avoid cross-object merging
    n = len(furn_objs)
    parsed = [_parse(o["name"]) for o in furn_objs]

    uf = list(range(n))
    def _find(x):
        while uf[x] != x:
            uf[x] = uf[uf[x]]
            x = uf[x]
        return x
    def _union(a, b):
        uf[_find(a)] = _find(b)

    for i in range(n):
        base_i, inst_i = parsed[i]
        for j in range(i + 1, n):
            base_j, inst_j = parsed[j]
            # Different Blender import instances → always separate groups
            if inst_i != inst_j:
                continue
            # Prefix check: allow both underscore and space as sub-part separator
            # so Sketchfab models with space-separated names also cluster correctly
            short = base_i if len(base_i) <= len(base_j) else base_j
            long  = base_j if len(base_i) <= len(base_j) else base_i
            is_subpart = (
                long == short
                or long.startswith(short + "_")
                or long.startswith(short + " ")
            )
            if not is_subpart:
                continue
            # Spatial proximity guard: sub-parts of the same object are co-located
            if _dist2d(furn_objs[i], furn_objs[j]) > EPS:
                continue
            _union(i, j)

    clusters: dict = {}
    for i, obj in enumerate(furn_objs):
        clusters.setdefault(_find(i), []).append(obj)

    furniture_groups = []
    for members in clusters.values():
        members.sort(key=lambda o: len(o["name"]))  # shortest name = root object
        root_base, _ = _parse(members[0]["name"])
        display = root_base.replace("_", " ").title()
        furniture_groups.append({
            "display_name": display,
            "count":        len(members),
            "items":        members,
        })

    room_groups = []
    if room_objs:
        room_groups = [{"display_name": "Oda Yapısı", "count": len(room_objs), "items": room_objs}]

    groups = room_groups + furniture_groups

    # ── Gemini: analysis text only (no grouping) ──────────────────
    analysis_text = ""
    gemini_key = os.getenv("GOOGLE_API_KEY")
    if gemini_key and visible:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(
                "gemini-2.0-flash-lite",
                generation_config={"temperature": 0, "response_mime_type": "application/json"},
            )
            resp = model.generate_content(
                "Sen bir iç tasarım yapay zekasısın. Blender sahnesinde şu nesneler var:\n"
                f"{_json.dumps(all_names, ensure_ascii=False)}\n\n"
                "2-3 cümleyle sahnedeki mobilyaları ve tarzı Türkçe değerlendir.\n"
                'Return ONLY valid JSON: {"analysis":"<Turkish text>"}'
            )
            analysis_text = _json.loads(resp.text).get("analysis", "")
        except Exception:
            pass

    # ── Spatial merge: only absorb when center is clearly inside parent footprint
    #    AND the parent is substantially larger (5× area, raised from 3×) —
    #    prevents same-size objects (two fridges, two desks) from absorbing each other.
    def _primary(g):
        return max(g["items"], key=lambda o: o["dims_m"][0] * o["dims_m"][1])

    def _center_inside(child_obj, parent_obj):
        cx, cy = child_obj["location"][0], child_obj["location"][1]
        px, py = parent_obj["location"][0], parent_obj["location"][1]
        hw = parent_obj["dims_m"][0] / 2
        hd = parent_obj["dims_m"][1] / 2
        return abs(cx - px) <= hw and abs(cy - py) <= hd

    changed = True
    while changed:
        changed = False
        absorbed = [False] * len(furniture_groups)
        for i, gi in enumerate(furniture_groups):
            if absorbed[i]:
                continue
            pi = _primary(gi)
            ai = pi["dims_m"][0] * pi["dims_m"][1]
            for j, gj in enumerate(furniture_groups):
                if i == j or absorbed[j]:
                    continue
                pj = _primary(gj)
                aj = pj["dims_m"][0] * pj["dims_m"][1]
                # Parent must be at least 5× bigger (raised from 3×) — same-size
                # objects like two fridges should never absorb each other.
                if ai >= aj * 5 and _center_inside(pj, pi):
                    gi["items"].extend(gj["items"])
                    gi["count"] = len(gi["items"])
                    absorbed[j] = True
                    changed = True
                elif aj >= ai * 5 and _center_inside(pi, pj):
                    gj["items"].extend(gi["items"])
                    gj["count"] = len(gj["items"])
                    absorbed[i] = True
                    changed = True
                    break
        furniture_groups = [g for k, g in enumerate(furniture_groups) if not absorbed[k]]

    groups = room_groups + furniture_groups

    # Tag each item so the UI knows which is the primary mesh
    for g in groups:
        if not g["items"]:
            continue
        prim_name = _primary(g)["name"]
        for item in g["items"]:
            item["is_primary"] = (item["name"] == prim_name)

    return {
        "groups":   groups,
        "objects":  objects,
        "count":    len(objects),
        "analysis": analysis_text,
    }


class RoomOriginUpdate(BaseModel):
    origin_offset_m: list
    dimensions_m: dict = None


@app.patch("/catalog/house/{house_id}/room/{room_id}")
def update_room_origin(house_id: str, room_id: str, body: RoomOriginUpdate):
    """Update origin_offset_m (and optionally dimensions_m) for a room in Catalog.json."""
    import json, os
    catalog_path = os.path.join(
        os.environ.get("ASSET_LIBRARY_DIR", ""),
        "Catalog.json"
    )
    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)

    house_found = False
    room_found = False
    for asset in data.get("assets", []):
        if asset["id"] == house_id:
            house_found = True
            for room in asset.get("rooms", []):
                if room["room_id"] == room_id:
                    room["origin_offset_m"] = body.origin_offset_m
                    if body.dimensions_m:
                        room["dimensions_m"] = body.dimensions_m
                    room_found = True
                    break
            break

    if not house_found:
        return {"error": f"House '{house_id}' not found"}
    if not room_found:
        return {"error": f"Room '{room_id}' not found in house '{house_id}'"}

    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    try:
        from mcp_server import catalog as cat_module
        cat_module._catalog_cache = None
    except Exception:
        pass

    return {
        "ok": True,
        "house_id": house_id,
        "room_id": room_id,
        "origin_offset_m": body.origin_offset_m,
    }


@app.get("/catalog/categories")
def get_categories():
    from .tools.catalog_tools import list_all_categories
    return {"categories": list_all_categories()}


@app.post("/catalog/reload")
def reload_catalog():
    """Flush the in-memory catalog cache so the next read picks up disk changes."""
    from mcp_server import catalog as _cat
    _cat.reload_catalog()
    count = len(_cat.get_all_assets())
    return {"ok": True, "asset_count": count}


@app.get("/catalog/search")
def search_assets(
    query: Optional[str] = None,
    subcategory: Optional[str] = None,
    style: Optional[str] = None,
):
    from .tools.catalog_tools import search_catalog
    return {"results": search_catalog(query=query, subcategory=subcategory, style=style)}


class FacingUpdate(BaseModel):
    facing_correction_z: float


@app.get("/catalog/assets")
def list_catalog_assets():
    from .tools.catalog_tools import search_catalog
    return {"assets": search_catalog(limit=100)}


@app.get("/catalog/asset/{asset_id}")
def get_catalog_asset(asset_id: str):
    """Return full JSON metadata for a single asset (for the yapboz canvas)."""
    from mcp_server import catalog
    asset = catalog.get_asset_by_id(asset_id)
    if not asset:
        return {"error": f"Asset '{asset_id}' not found"}
    return {"asset": asset}


_CORRECTION_TO_FORWARD_AXIS = {0: "+Y", 90: "-X", 180: "-Y", 270: "+X"}


@app.patch("/catalog/asset/{asset_id}/metadata")
def update_asset_metadata(asset_id: str, body: dict):
    """Update an asset's subcategory and/or room_types in Catalog.json.

    Lets the user fix models that get flagged "eksik" during design because
    their room_types are too restrictive (e.g. a desk tagged office-only that
    the user wants to use in a living room). An empty room_types list means
    "allowed in any room" (asset_allowed_in_room returns True when empty).
    """
    import json, os
    catalog_path = os.path.join(
        os.environ.get("ASSET_LIBRARY_DIR", ""),
        "Catalog.json"
    )
    if not os.path.isfile(catalog_path):
        # Fallback to repo-relative path
        catalog_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "Catalog.json"))

    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)

    assets = data.get("assets", data) if isinstance(data, dict) else data

    found = False
    for asset in assets:
        if asset.get("id") == asset_id:
            if "subcategory" in body and body["subcategory"] is not None:
                asset["subcategory"] = str(body["subcategory"]).strip()
            if "room_types" in body and body["room_types"] is not None:
                rts = body["room_types"]
                if isinstance(rts, list):
                    asset["room_types"] = [str(r).strip().lower().replace(" ", "_") for r in rts if str(r).strip()]
            found = True
            break

    if not found:
        return {"error": f"Asset '{asset_id}' not found"}

    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    try:
        from mcp_server import catalog as cat_module
        cat_module._catalog_cache = None
    except Exception:
        pass

    saved = next((a for a in assets if a.get("id") == asset_id), {})
    return {
        "ok": True,
        "asset_id": asset_id,
        "subcategory": saved.get("subcategory", ""),
        "room_types": saved.get("room_types", []),
    }


@app.patch("/catalog/asset/{asset_id}/facing")
def update_facing(asset_id: str, body: FacingUpdate):
    """Update facing direction for an asset in Catalog.json.

    Writes both placement.forward_axis (the single source of truth used by
    get_facing_correction_z) and the legacy root-level facing_correction_z
    so older code paths stay consistent.
    """
    import json, os
    catalog_path = os.path.join(
        os.environ.get("ASSET_LIBRARY_DIR", ""),
        "Catalog.json"
    )
    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)

    found = False
    correction = int(body.facing_correction_z) % 360
    forward_axis = _CORRECTION_TO_FORWARD_AXIS.get(correction, "+Y")
    for asset in data.get("assets", []):
        if asset["id"] == asset_id:
            asset["facing_correction_z"] = body.facing_correction_z
            if "placement" not in asset or not isinstance(asset["placement"], dict):
                asset["placement"] = {}
            asset["placement"]["forward_axis"] = forward_axis
            found = True
            break

    if not found:
        return {"error": f"Asset '{asset_id}' not found"}

    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    try:
        from mcp_server import catalog as cat_module
        cat_module._catalog_cache = None
    except Exception:
        pass

    return {
        "ok": True,
        "asset_id": asset_id,
        "facing_correction_z": body.facing_correction_z,
        "forward_axis": forward_axis,
    }


@app.patch("/catalog/asset/{asset_id}/rotation-correction")
def update_rotation_correction(asset_id: str, body: dict):
    """Save rotation_correction [rx, ry, rz] degrees to Catalog.json.

    Used to fix models that import sideways (lying on side).
    rx=90 stands up a model that came in lying flat on its back.
    """
    import json, os

    rx = float(body.get("rx", 0))
    ry = float(body.get("ry", 0))
    rz = float(body.get("rz", 0))

    catalog_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "Catalog.json"
    )
    catalog_path = os.path.normpath(catalog_path)

    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)

    assets = data.get("assets", data) if isinstance(data, dict) else data
    found = False
    for asset in assets:
        if isinstance(asset, dict) and asset.get("id") == asset_id:
            asset["rotation_correction"] = [rx, ry, rz]
            found = True
            break

    if not found:
        return {"error": f"Asset '{asset_id}' not found"}

    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    try:
        from mcp_server import catalog as _cat
        _cat.reload_catalog()
    except Exception:
        pass

    return {"ok": True, "asset_id": asset_id, "rotation_correction": [rx, ry, rz]}


@app.delete("/catalog/asset/{asset_id}")
def delete_catalog_asset(asset_id: str):
    """Katalogdan bir asset kaydını siler. Fiziksel dosyaya dokunmaz."""
    import json as _j

    if not _CATALOG_PATH.exists():
        return {"error": "Catalog.json bulunamadı"}

    data   = _j.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    assets = data.get("assets", []) if isinstance(data, dict) else data
    before = len(assets)

    if isinstance(data, dict):
        data["assets"] = [a for a in assets if a.get("id") != asset_id]
        after = len(data["assets"])
    else:
        data  = [a for a in data if a.get("id") != asset_id]
        after = len(data)

    if after == before:
        return {"error": f"'{asset_id}' katalogda bulunamadı"}

    _CATALOG_PATH.write_text(_j.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        from mcp_server import catalog as _cat
        _cat.reload_catalog()
    except Exception:
        pass

    return {"ok": True, "deleted": asset_id}


@app.patch("/catalog/asset/{asset_id}/rename")
def rename_asset(asset_id: str, body: dict):
    """Update name and/or id of a catalog asset.

    Body: { new_name (opt), new_id (opt) }
    """
    import json, re as _re

    new_name = (body.get("new_name") or "").strip()
    new_id   = (body.get("new_id")   or "").strip()

    if not new_name and not new_id:
        return {"error": "new_name veya new_id gerekli"}

    if new_id and not _re.fullmatch(r"[a-z0-9_]+", new_id):
        return {"error": "ID sadece küçük harf, rakam ve alt çizgi içerebilir"}

    if not _CATALOG_PATH.exists():
        return {"error": "Catalog.json bulunamadı"}

    data   = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    assets = data.get("assets", []) if isinstance(data, dict) else data
    entry  = next((a for a in assets if isinstance(a, dict) and a.get("id") == asset_id), None)

    if not entry:
        return {"error": f"'{asset_id}' katalogda bulunamadı"}

    old_id   = entry["id"]
    old_name = entry.get("name", old_id)

    # Apply changes
    if new_name:
        entry["name"] = new_name

    id_changed = False
    if new_id and new_id != old_id:
        if any(a.get("id") == new_id for a in assets if a is not entry):
            return {"error": f"'{new_id}' ID'si zaten kullanımda"}
        entry["id"] = new_id
        id_changed = True

        # Rename thumbnail if it exists
        for ext in ("jpg", "jpeg", "png", "webp"):
            old_t = _THUMBS_DIR / f"{old_id}.{ext}"
            if old_t.exists():
                old_t.rename(_THUMBS_DIR / f"{new_id}.{ext}")
                break

    # Write back
    _CATALOG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Flush cache
    try:
        from mcp_server import catalog as _cat
        _cat.reload_catalog()
    except Exception:
        pass

    return {
        "ok":         True,
        "old_id":     old_id,
        "new_id":     entry["id"],
        "old_name":   old_name,
        "new_name":   entry.get("name", old_name),
        "id_changed": id_changed,
    }


@app.post("/blender/generate-in-area")
def generate_in_area(body: dict):
    """Ask Gemini or Claude to generate a Blender Python script for a described object,
    place it inside the selected canvas area, and execute it in Blender."""
    import httpx, json as _json, re as _re

    prompt   = (body.get("prompt") or "").strip()
    area     = body.get("area") or {}
    llm      = body.get("llm", "gemini")
    ax       = float(area.get("x",     0))
    ay       = float(area.get("y",     0))
    aw       = float(area.get("width", 1))
    ad       = float(area.get("depth", 1))

    if not prompt:
        return {"error": "prompt boş olamaz"}

    obj_name = f"AI_{_re.sub(r'[^a-z0-9]', '_', prompt[:24].lower())}"
    bpy_prompt = f"""You are a Blender 4.x Python expert for interior design.
Generate a bpy script that creates a 3D mesh object described as: "{prompt}"

Constraints:
- World position: x={ax:.3f}, y={ay:.3f}, z=0.0
- Available footprint: {aw:.2f}m wide (X) × {ad:.2f}m deep (Y)  — object may be smaller
- Use only bpy built-ins (bpy.ops, bpy.data, mathutils); no external imports
- Name the final object: "{obj_name}"
- Apply a Principled BSDF material with a fitting base color
- End with bpy.ops.object.select_all(action='DESELECT')
- Must run without errors in Blender 4.x

Return ONLY the raw Python code — no markdown, no explanations."""

    script = None

    if llm == "claude":
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            return {"error": "ANTHROPIC_API_KEY .env dosyasında eksik"}
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": bpy_prompt}],
            )
            script = msg.content[0].text.strip()
        except Exception as e:
            return {"error": f"Claude hatası: {e}"}
    else:
        gemini_key = os.getenv("GOOGLE_API_KEY")
        if not gemini_key:
            return {"error": "GOOGLE_API_KEY .env dosyasında eksik"}
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            resp   = model.generate_content(bpy_prompt)
            script = resp.text.strip()
        except Exception as e:
            return {"error": f"Gemini hatası: {e}"}

    script = _re.sub(r"^```[a-z]*\n?", "", script, flags=_re.MULTILINE)
    script = script.replace("```", "").strip()

    # Execute the script in Blender
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post("http://localhost:8766",
                            json={"action": "run_python", "params": {"script": script}})
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        return {"error": f"Blender bağlantı hatası: {e}", "script": script}

    if not result.get("success"):
        err = result.get("result", {}).get("error") or result.get("error", "Bilinmeyen hata")
        return {"error": err, "script": script}

    return {
        "ok":      True,
        "message": f"'{prompt}' oluşturuldu → {obj_name}",
        "script":  script,
    }


@app.post("/blender/save-generated-model")
def save_generated_model(body: dict):
    """Export a GM_* object from Blender to a .blend file and add it to Catalog.json.

    Body: { obj_name, prompt, category (opt), subcategory (opt) }
    """
    import httpx, json as _j, re as _re, time as _time
    from datetime import date as _date

    obj_name   = (body.get("obj_name") or "").strip()
    prompt     = (body.get("prompt")   or "").strip()
    user_cat   = (body.get("category") or "").strip()
    user_sub   = (body.get("subcategory") or "").strip()

    if not obj_name:
        return {"error": "obj_name gerekli"}

    # ── Derive a clean asset ID ───────────────────────────────────────
    slug = _re.sub(r"[^a-z0-9]+", "_", obj_name.lower()).strip("_")
    asset_id  = slug[:40]
    save_dir  = _ASSET_LIB_DIR / "models" / "generated" / asset_id
    save_path = save_dir / f"{asset_id}.blend"
    save_dir.mkdir(parents=True, exist_ok=True)

    # ── Blender script: get dims + export to .blend ───────────────────
    sp_escaped = str(save_path).replace("\\", "/")
    script = f"""
import bpy, os

obj = bpy.data.objects.get({obj_name!r})
if not obj:
    for o in bpy.data.objects:
        if o.name.startswith("GM_"):
            obj = o
            break

if not obj:
    _result = {{"error": "Object '{obj_name}' not found in scene"}}
else:
    dims = {{
        "width":  round(obj.dimensions.x, 4),
        "depth":  round(obj.dimensions.y, 4),
        "height": round(obj.dimensions.z, 4),
    }}
    loc  = [round(v, 3) for v in obj.location]

    # Collect object + children data blocks
    data_blocks = {{obj}}
    for child in obj.children_recursive:
        data_blocks.add(child)

    # Internal proportion check: if one mesh child is dramatically larger
    # than the others, the model has broken internal proportions that a single
    # uniform scale can't fix — flag it for the UI.
    _meshes = [o for o in ([obj] + list(obj.children_recursive)) if o.type == 'MESH']
    _maxdims = sorted(max(o.dimensions.x, o.dimensions.y, o.dimensions.z) for o in _meshes)
    _proportion_warning = False
    if len(_maxdims) >= 3:
        _median = _maxdims[len(_maxdims) // 2]
        if _median > 1e-6 and _maxdims[-1] > _median * 4.0:
            _proportion_warning = True

    os.makedirs(os.path.dirname({sp_escaped!r}), exist_ok=True)
    bpy.data.libraries.write({sp_escaped!r}, data_blocks,
                              fake_user=True, compress=False)
    _result = {{
        "ok":       True,
        "obj_name": obj.name,
        "dims":     dims,
        "location": loc,
        "proportion_warning": _proportion_warning,
    }}
"""

    try:
        with httpx.Client(timeout=20.0) as c:
            r = c.post("http://localhost:8766",
                       json={"action": "run_python", "params": {"script": script}})
            r.raise_for_status()
            res = r.json()
    except Exception as e:
        return {"error": f"Blender bağlantı hatası: {e}"}

    if not res.get("success"):
        return {"error": (res.get("result") or {}).get("error") or res.get("error", "Blender hatası")}

    inner = res.get("result") or {}
    if inner.get("error"):
        return {"error": inner["error"]}

    measured = inner.get("dims") or {"width": 0.5, "depth": 0.5, "height": 0.5}
    proportion_warning = bool(inner.get("proportion_warning"))

    # ── Subcategory + silent size normalization to realistic scale ────
    from mcp_server.tools.size_reference import guess_subcategory, normalize_dims
    cat = user_cat or "generated"
    sub = user_sub or guess_subcategory(prompt)

    dims, _scale_ratio = normalize_dims(measured, sub)
    # import_scale lets future imports rescale the raw mesh to the normalized size
    import_scale = round(_scale_ratio, 6) if _scale_ratio else 1.0

    file_rel = f"models/generated/{asset_id}/{asset_id}.blend"

    entry = {
        "id":          asset_id,
        "name":        prompt[:60] if prompt else obj_name,
        "category":    cat,
        "subcategory": sub,
        "style":       [],
        "tags":        ["ai-generated"],
        "semantic_tags": ["generated", "custom"],
        "room_types":  [],
        "is_container": False,
        "scale_class": "human",
        "compatible_with": [],
        "import_scale": import_scale,
        "proportion_warning": proportion_warning,
        "footprint": {
            "width_m":           dims["width"],
            "depth_m":           dims["depth"],
            "height_m":          dims["height"],
            "clearance_front_m": 0.5,
            "clearance_sides_m": 0.1,
        },
        "placement": {
            "rules": ["floor", "center_ok"],
            "anchor": "floor_center",
            "forward_axis": "+Y",
            "facing_correction_z": 0,
            "confidence": 1.0,
        },
        "file":         file_rel,
        "dimensions_m": dims,
        "origin":       "floor_center",
        "facing_correction_z": 0,
        "poly_count":   0,
        "added_at":     str(_date.today()),
        "source":       "ai-generated",
        "prompt":       prompt,
    }

    # ── Append to Catalog.json ────────────────────────────────────────
    if _CATALOG_PATH.exists():
        catalog_data = _j.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    else:
        catalog_data = {"assets": []}

    assets = catalog_data.get("assets", catalog_data) if isinstance(catalog_data, dict) else catalog_data

    # Remove duplicate if re-saving same id
    if isinstance(catalog_data, dict):
        catalog_data["assets"] = [a for a in assets if a.get("id") != asset_id]
        catalog_data["assets"].append(entry)
    else:
        catalog_data = [a for a in catalog_data if a.get("id") != asset_id]
        catalog_data.append(entry)

    _CATALOG_PATH.write_text(_j.dumps(catalog_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Flush server-side catalog cache
    try:
        from mcp_server import catalog as _cat
        _cat.reload_catalog()
    except Exception:
        pass

    return {
        "ok":       True,
        "asset_id": asset_id,
        "file":     file_rel,
        "dims":     dims,
        "entry":    entry,
    }


@app.post("/blender/import-model")
def import_model_by_id(body: dict):
    """Import a catalog asset into Blender by asset_id.
    Applies import_scale and rotation_correction from catalog automatically.
    """
    import httpx, json as _j

    asset_id = (body.get("asset_id") or "").strip()
    location = body.get("location", [0.0, 0.0, 0.0])

    if not asset_id:
        return {"error": "asset_id gerekli"}

    from mcp_server import catalog as _cat
    asset = _cat.get_asset_by_id(asset_id)
    if not asset:
        return {"error": f"'{asset_id}' katalogda bulunamadı"}

    abs_file = _cat.resolve_file_path(asset["file"])
    if not abs_file.exists():
        return {"error": f"Dosya bulunamadı: {abs_file}"}

    imp_scale = float(asset.get("import_scale", 1.0))
    rc        = asset.get("rotation_correction", [0, 0, 0])
    facing_z  = float(
        asset.get("facing_correction_z")
        or (asset.get("placement") or {}).get("facing_correction_z") or 0
    )
    rotation = [float(rc[0]), float(rc[1]), facing_z + float(rc[2])]

    dims = asset.get("dimensions_m") or {}
    catalog_dims = None
    if dims.get("width") and dims.get("depth") and dims.get("height"):
        catalog_dims = {k: float(v) for k, v in dims.items() if k in ("width", "depth", "height")}

    try:
        with httpx.Client(timeout=20.0) as c:
            r = c.post("http://localhost:8766",
                       json={"action": "import_blend_asset", "params": {
                           "file_path":    str(abs_file),
                           "location":     location,
                           "rotation":     rotation,
                           "scale":        imp_scale,
                           "name":         asset_id,
                           "catalog_dims": catalog_dims,
                       }})
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        return {"error": f"Blender bağlantı hatası: {e}"}

    if not result.get("success"):
        err = (result.get("result") or {}).get("error") or result.get("error", "Hata")
        return {"error": err}

    res = result.get("result", {})
    return {
        "ok":       True,
        "obj_name": res.get("name", asset_id),
        "location": res.get("location", location),
        "asset_id": asset_id,
    }


@app.post("/blender/run-script")
def run_blender_script(body: dict):
    """Execute an arbitrary Python script in Blender via the addon HTTP server."""
    import httpx
    script = (body.get("script") or "").strip()
    if not script:
        return {"error": "script boş olamaz"}
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post("http://localhost:8766",
                       json={"action": "run_python", "params": {"script": script}})
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        return {"error": f"Blender bağlantı hatası: {e}"}
    if not result.get("success"):
        err = (result.get("result") or {}).get("error") or result.get("error", "Hata")
        return {"error": err}
    return {"ok": True}


@app.post("/blender/generate-model")
def generate_model(body: dict):
    """Ask Gemini or Claude to create a free-form 3D mesh in Blender at the cursor position."""
    import httpx, re as _re

    prompt   = (body.get("prompt") or "").strip()
    llm      = body.get("llm", "gemini")
    pos      = body.get("position") or [0.0, 0.0, 0.0]  # world XYZ

    if not prompt:
        return {"error": "prompt boş olamaz"}

    obj_name  = "GM_" + _re.sub(r"[^a-z0-9]", "_", prompt[:28].lower()).strip("_")

    # Inject expected real-world size for the detected furniture type so the
    # model comes out at a consistent scale from the start.
    from mcp_server.tools.size_reference import guess_subcategory, expected_dims
    _sub = guess_subcategory(prompt)
    _ref = expected_dims(_sub)
    _size_hint = (f"about {_ref['w']}×{_ref['d']}×{_ref['h']} m "
                  f"(width×depth×height) for a typical {_sub}")

    bpy_prompt = f"""You are a Blender 4.x Python expert. Create a realistic, detailed 3D mesh object described as:

"{prompt}"

Rules:
- Place the object at world position x={pos[0]:.3f}, y={pos[1]:.3f}, z={pos[2]:.3f}
- Target real-world size: {_size_hint}. Build it at this scale.
- Use only bpy, bmesh, mathutils — no external imports
- Name the final object exactly: "{obj_name}"
- Apply a Principled BSDF material with a fitting base color
- Use bevels and subdivisions for realistic curves
- End with bpy.ops.object.select_all(action='DESELECT')
- Must run without errors in Blender 4.x

Return ONLY raw Python code — no markdown, no explanations."""

    script = None
    if llm == "claude":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            return {"error": "ANTHROPIC_API_KEY eksik"}
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            msg    = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=3000,
                messages=[{"role": "user", "content": bpy_prompt}],
            )
            script = msg.content[0].text.strip()
        except Exception as e:
            return {"error": f"Claude hatası: {e}"}
    else:
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            return {"error": "GOOGLE_API_KEY eksik"}
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            resp   = genai.GenerativeModel("gemini-2.5-flash").generate_content(bpy_prompt)
            script = resp.text.strip()
        except Exception as e:
            return {"error": f"Gemini hatası: {e}"}

    script = _re.sub(r"^```[a-z]*\n?", "", script, flags=_re.MULTILINE)
    script = script.replace("```", "").strip()

    try:
        with httpx.Client(timeout=25.0) as c:
            r = c.post("http://localhost:8766",
                       json={"action": "run_python", "params": {"script": script}})
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        return {"error": f"Blender bağlantı hatası: {e}", "script": script}

    if not result.get("success"):
        err = (result.get("result") or {}).get("error") or result.get("error", "Bilinmeyen hata")
        return {"error": err, "script": script}

    return {"ok": True, "obj_name": obj_name, "message": f"'{prompt}' oluşturuldu", "script": script}


@app.post("/blender/rotate-objects")
def rotate_objects_endpoint(body: dict):
    """Rotate Blender objects around Z axis by a delta angle (degrees)."""
    import httpx
    names   = body.get("names", [])
    delta_z = float(body.get("delta_z", 90.0))
    if not names:
        return {"error": "names listesi boş olamaz"}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post("http://localhost:8766",
                            json={"action": "rotate_objects",
                                  "params": {"names": names, "delta_z": delta_z}})
            r.raise_for_status()
            result = r.json()
            if not result.get("success"):
                return {"error": result.get("error", "Blender hatası")}
            return result.get("result", {})
    except Exception as e:
        return {"error": str(e)}


import json as _json
from pathlib import Path as _Path

_PRESETS_FILE       = _Path(__file__).parent.parent / "material_presets.json"
_AGENT_PROMPTS_FILE = _Path(__file__).parent.parent / "agent_prompts.json"
_prompts_lock       = __import__("threading").Lock()

def _read_presets():
    if _PRESETS_FILE.exists():
        return _json.loads(_PRESETS_FILE.read_text(encoding="utf-8"))
    return []

def _write_presets(presets):
    _PRESETS_FILE.write_text(_json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/materials/presets")
def get_presets():
    """Return all saved material presets from material_presets.json."""
    return _read_presets()


@app.post("/materials/presets")
def save_preset(body: dict):
    """Upsert a named material preset."""
    name = (body.get("name") or "").strip()
    mat  = body.get("mat")
    if not name or mat is None:
        return {"error": "name ve mat gerekli"}
    presets = _read_presets()
    idx = next((i for i, p in enumerate(presets) if p["name"] == name), -1)
    if idx >= 0:
        presets[idx]["mat"] = mat
    else:
        presets.append({"name": name, "mat": mat})
    _write_presets(presets)
    return {"ok": True, "count": len(presets)}


@app.post("/materials/presets/rename")
def rename_preset(body: dict):
    """Rename a preset in-place (preserves order and mat data)."""
    old_name = (body.get("old_name") or "").strip()
    new_name = (body.get("new_name") or "").strip()
    if not old_name or not new_name:
        return {"error": "old_name ve new_name gerekli"}
    presets = _read_presets()
    for p in presets:
        if p["name"] == old_name:
            p["name"] = new_name
            break
    _write_presets(presets)
    return {"ok": True}


@app.delete("/materials/presets/{preset_name:path}")
def delete_preset(preset_name: str):
    """Delete a preset by name."""
    presets = [p for p in _read_presets() if p["name"] != preset_name]
    _write_presets(presets)
    return {"ok": True, "count": len(presets)}


@app.post("/materials/generate-texture-image")
def start_generate_texture_image(body: dict):
    """Generate a PNG texture image with gemini-2.5-flash-preview-image-generation.
    Returns a job_id for polling. On completion: {status:'done', path, thumbnail}."""
    import threading, uuid, re as _re2, base64, io

    prompt   = (body.get("prompt") or "").strip()
    llm_pref = body.get("llm", "gemini")
    if not prompt:
        return {"error": "prompt gerekli"}

    job_id = f"mattex_{uuid.uuid4().hex[:8]}"
    with _am_jobs_lock:
        _am_jobs[job_id] = {"status": "running", "output": "Başlatılıyor...", "path": None, "thumbnail": None}

    lib_dir  = os.environ.get("ASSET_LIBRARY_DIR", "")
    dest_dir = Path(lib_dir) / "models" / "ai_textures"
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe     = _re2.sub(r"[^\w]", "_", prompt.lower())[:28]
    out_path = dest_dir / f"{safe}_{uuid.uuid4().hex[:6]}.png"

    def _log(msg):
        with _am_jobs_lock:
            _am_jobs[job_id]["output"] = msg

    def _run():
        try:
            gemini_key = os.getenv("GOOGLE_API_KEY")
            if not gemini_key:
                raise Exception("GOOGLE_API_KEY bulunamadı")

            import google.generativeai as genai2
            genai2.configure(api_key=gemini_key)

            _log("gemini-2.5-flash-preview-image-generation ile resim üretiliyor...")
            img_model = genai2.GenerativeModel("gemini-2.5-flash-image")

            img_prompt = (
                f"Create a seamless, tileable material texture image. "
                f"Style: {prompt}. "
                "Requirements: photorealistic, high detail, uniform repeat pattern, "
                "no text, no watermarks, square format."
            )
            img_resp = img_model.generate_content(
                img_prompt,
                generation_config={"response_modalities": ["IMAGE"]},
            )

            img_bytes = None
            for part in img_resp.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    raw = part.inline_data.data
                    # SDK may return raw bytes OR base64 string — handle both
                    if isinstance(raw, (bytes, bytearray)):
                        img_bytes = bytes(raw)
                    else:
                        img_bytes = base64.b64decode(raw + "==")
                    break

            if not img_bytes:
                raise Exception("Model görsel döndürmedi")

            # Open from memory buffer (no extension confusion), save as JPEG
            from PIL import Image as _PIL_Im
            _log("Resim işleniyor...")
            pil_img = _PIL_Im.open(io.BytesIO(img_bytes)).convert("RGB")

            # Always save as JPEG regardless of model output format
            save_path = out_path.with_suffix(".jpg")
            pil_img.save(str(save_path), "JPEG", quality=92)

            # Build thumbnail
            _log("Thumbnail oluşturuluyor...")
            thumb_img = pil_img.copy()
            thumb_img.thumbnail((64, 64))
            buf = io.BytesIO()
            thumb_img.save(buf, "JPEG", quality=75)
            thumb_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

            _log("Tamamlandı!")
            with _am_jobs_lock:
                _am_jobs[job_id]["status"]    = "done"
                _am_jobs[job_id]["path"]      = str(save_path).replace("\\", "/")
                _am_jobs[job_id]["thumbnail"] = thumb_b64

        except Exception as exc:
            _log(f"HATA: {exc}")
            with _am_jobs_lock:
                _am_jobs[job_id]["status"] = "error"
                _am_jobs[job_id]["error"]  = str(exc)

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}


@app.get("/materials/generate-texture-image/{job_id}")
def poll_generate_texture(job_id: str):
    """Poll texture generation job status."""
    with _am_jobs_lock:
        job = _am_jobs.get(job_id)
    if not job:
        return {"status": "error", "error": "job bulunamadı"}
    return job


@app.get("/files/textures")
def list_textures():
    """Return all image texture files found under ASSET_LIBRARY_DIR/models/."""
    import pathlib
    lib_dir = os.environ.get("ASSET_LIBRARY_DIR", "")
    models_dir = pathlib.Path(lib_dir) / "models"
    if not models_dir.exists():
        return {"textures": [], "error": "models/ klasörü bulunamadı"}
    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".exr", ".hdr"}
    textures = []
    for p in sorted(models_dir.rglob("*")):
        if p.suffix.lower() in IMAGE_EXTS and p.is_file():
            textures.append({
                "name": p.name,
                "path": str(p).replace("\\", "/"),
                "rel":  str(p.relative_to(models_dir)).replace("\\", "/"),
            })
    return {"textures": textures}


@app.post("/files/upload-texture")
async def upload_texture(file: UploadFile):
    """Save an uploaded image as a user texture in models/user_textures/."""
    import pathlib, shutil, uuid
    lib_dir = os.environ.get("ASSET_LIBRARY_DIR", "")
    dest_dir = pathlib.Path(lib_dir) / "models" / "user_textures"
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext   = pathlib.Path(file.filename).suffix.lower() or ".jpg"
    stem  = pathlib.Path(file.filename).stem[:40].replace(" ", "_")
    fname = f"{stem}{ext}"
    dest  = dest_dir / fname
    # avoid overwrite
    if dest.exists():
        dest = dest_dir / f"{stem}_{uuid.uuid4().hex[:6]}{ext}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "path": str(dest).replace("\\", "/"), "name": dest.name}


@app.get("/files/texture-image")
def serve_texture_image(path: str):
    """Serve a texture image file for browser preview (jpg/png only)."""
    import pathlib
    p = pathlib.Path(path)
    if p.exists() and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
        return FileResponse(str(p))
    from fastapi.responses import Response
    return Response(status_code=404)


@app.post("/blender/apply-material")
def apply_material(body: dict):
    """Apply a material to Blender objects — from a texture file or AI-generated."""
    import httpx, re as _re

    object_names = body.get("object_names", [])
    mode         = body.get("mode", "ai")          # "file" | "pbr" | "ai"
    texture_path = body.get("texture_path", "")
    diff_path    = body.get("diff_path", "")
    rough_path   = body.get("rough_path") or ""
    normal_path  = body.get("normal_path") or ""
    prompt       = (body.get("prompt") or "").strip()
    llm          = body.get("llm", "gemini")

    if not object_names:
        return {"error": "object_names boş olamaz"}

    # Build one script that applies the material to ALL requested objects
    targets_py = repr(object_names)

    if mode == "pbr":
        if not diff_path:
            return {"error": "PBR modu için en az diff_path gerekli"}

        rough_block = ""
        if rough_path:
            rough_block = f"""
    rough = nodes.new('ShaderNodeTexImage')
    rough.image = bpy.data.images.load(r"{rough_path}", check_existing=True)
    rough.image.colorspace_settings.name = 'Non-Color'
    rough.location = (-200, 0)
    links.new(mapping.outputs['Vector'], rough.inputs['Vector'])
    links.new(rough.outputs['Color'], bsdf.inputs['Roughness'])"""

        normal_block = ""
        if normal_path:
            normal_block = f"""
    nor_tex = nodes.new('ShaderNodeTexImage')
    nor_tex.image = bpy.data.images.load(r"{normal_path}", check_existing=True)
    nor_tex.image.colorspace_settings.name = 'Non-Color'
    nor_tex.location = (-200, -300)
    nor_map = nodes.new('ShaderNodeNormalMap')
    nor_map.location = (0, -300)
    links.new(mapping.outputs['Vector'], nor_tex.inputs['Vector'])
    links.new(nor_tex.outputs['Color'], nor_map.inputs['Color'])
    links.new(nor_map.outputs['Normal'], bsdf.inputs['Normal'])"""

        script = f"""
import bpy

def ensure_uvs(obj):
    if obj.type == 'MESH' and not obj.data.uv_layers:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.01)
        bpy.ops.object.mode_set(mode='OBJECT')

for obj_name in {targets_py}:
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != 'MESH':
        continue
    
    ensure_uvs(obj)
    
    mat_name = "Mat_PBR_" + obj_name
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    output = nodes.new('ShaderNodeOutputMaterial')
    bsdf   = nodes.new('ShaderNodeBsdfPrincipled')
    output.location = (600, 0)
    bsdf.location   = (300, 0)
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    
    uv      = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    uv.location      = (-700, 0)
    mapping.location = (-500, 0)
    links.new(uv.outputs['UV'], mapping.inputs['Vector'])
    
    diff = nodes.new('ShaderNodeTexImage')
    diff.image = bpy.data.images.load(r"{diff_path}", check_existing=True)
    diff.image.colorspace_settings.name = 'sRGB'
    diff.location = (-200, 300)
    links.new(mapping.outputs['Vector'], diff.inputs['Vector'])
    links.new(diff.outputs['Color'], bsdf.inputs['Base Color']){rough_block}{normal_block}
    
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

# Switch to Material Preview
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.shading.type = 'MATERIAL'
""".strip()

    elif mode == "file":
        if not texture_path:
            return {"error": "Dosya modu için texture_path gerekli"}
        script = f"""
import bpy

def ensure_uvs(obj):
    if obj.type == 'MESH' and not obj.data.uv_layers:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.01)
        bpy.ops.object.mode_set(mode='OBJECT')

tex_path = r"{texture_path}"
for obj_name in {targets_py}:
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != 'MESH':
        continue
        
    ensure_uvs(obj)
    
    mat_name = "Mat_Tex_" + obj_name
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    output   = nodes.new('ShaderNodeOutputMaterial')
    bsdf     = nodes.new('ShaderNodeBsdfPrincipled')
    uv       = nodes.new('ShaderNodeTexCoord')
    mapping  = nodes.new('ShaderNodeMapping')
    tex_node = nodes.new('ShaderNodeTexImage')
    
    output.location   = (600, 0)
    bsdf.location     = (300, 0)
    tex_node.location = (0, 0)
    mapping.location  = (-300, 0)
    uv.location       = (-500, 0)
    
    tex_node.image = bpy.data.images.load(tex_path, check_existing=True)
    tex_node.image.colorspace_settings.name = 'sRGB'
    
    links.new(uv.outputs['UV'], mapping.inputs['Vector'])
    links.new(mapping.outputs['Vector'], tex_node.inputs['Vector'])
    links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

# Switch to Material Preview
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.shading.type = 'MATERIAL'
""".strip()

    else:  # ai mode
        if not prompt:
            return {"error": "AI modu için prompt gerekli"}
        target_name = object_names[0]
        bpy_prompt = f"""Sen Blender 4.x Python uzmanısın. Aşağıdaki tarzda detaylı bir materyal oluştur ve "{target_name}" nesnesine uygula:

Materyal tarifi: "{prompt}"

Kurallar:
- Sadece bpy built-in modüller kullan (bpy, mathutils)
- Harici dosya/texture yok — tamamen prosedürel (Noise, Voronoi, Wave vs. shader node'larıyla)
- Principled BSDF kullan; roughness, metallic ve base color kanallarını node'larla detaylandır.
- Nesne adı: "{target_name}" — bpy.data.objects.get() ile eriş.
- Eğer nesnenin UV haritası yoksa, bpy.ops.uv.smart_project() ile oluştur.
- Script sonunda Blender viewport'unu 'MATERIAL' (Material Preview) moduna geçir.
- Script Blender 4.x'te hatasız çalışmalı.

Sadece Python kodu döndür, açıklama veya markdown yok."""

        script = None
        if llm == "claude":
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")
            if not anthropic_key:
                return {"error": "ANTHROPIC_API_KEY eksik"}
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=anthropic_key)
                msg = client.messages.create(
                    model="claude-sonnet-4-6", max_tokens=2048,
                    messages=[{"role": "user", "content": bpy_prompt}],
                )
                script = msg.content[0].text.strip()
            except Exception as e:
                return {"error": f"Claude hatası: {e}"}
        else:
            gemini_key = os.getenv("GOOGLE_API_KEY")
            if not gemini_key:
                return {"error": "GOOGLE_API_KEY eksik"}
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel("gemini-2.5-flash")
                script = model.generate_content(bpy_prompt).text.strip()
            except Exception as e:
                return {"error": f"Gemini hatası: {e}"}

        script = _re.sub(r"^```[a-z]*\n?", "", script, flags=_re.MULTILINE)
        script = script.replace("```", "").strip()

    # Execute in Blender
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post("http://localhost:8766",
                            json={"action": "run_python", "params": {"script": script}})
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        return {"error": f"Blender bağlantı hatası: {e}"}

    if not result.get("success"):
        err = result.get("result", {}).get("error") or result.get("error", "Bilinmeyen hata")
        return {"error": err, "script": script}

    # run_python catches script exceptions and returns {"error": ...} inside result
    inner = result.get("result") or {}
    if inner.get("error"):
        return {"error": inner["error"], "script": script}

    return {"ok": True, "message": f"Materyal uygulandı → {', '.join(object_names)}",
            "mode": mode, "script": script if mode == "ai" else None}


@app.post("/blender/delete-objects")
def delete_objects_endpoint(body: dict):
    """Delete Blender objects by name."""
    import httpx
    names = body.get("names", [])
    if not names:
        return {"error": "names listesi boş olamaz"}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post("http://localhost:8766",
                            json={"action": "delete_objects", "params": {"names": names}})
            r.raise_for_status()
            result = r.json()
            if not result.get("success"):
                return {"error": result.get("error", "Blender hatası")}
            return result.get("result", {})
    except Exception as e:
        return {"error": str(e)}


@app.post("/blender/modify-object")
def modify_object(body: dict):
    """Use Gemini or Claude to generate a bpy script that modifies the selected object(s)."""
    import httpx, re as _re

    object_names = body.get("object_names", [])
    group_name   = body.get("group_name", "")
    prompt       = (body.get("prompt") or "").strip()
    llm          = body.get("llm", "gemini")

    if not prompt:
        return {"error": "prompt boş olamaz"}
    if not object_names:
        return {"error": "object_names boş olamaz"}

    object_data = body.get("object_data", [])
    obj_context = ""
    for od in object_data:
        rot_z = (od.get("rotation_euler") or [0, 0, 0])[2]
        obj_context += (f"\n  {od['name']}: location={od.get('location')}, "
                        f"dims_m={od.get('dims_m')} (length×thickness×height), "
                        f"rotation_z={rot_z}°")

    bpy_prompt = f"""You are a Blender 4.x Python expert for interior design.
The user wants to modify these already-existing Blender objects: {object_names}
Their display name / asset type: "{group_name}"
{f"Actual measured data from the scene:{obj_context}" if obj_context else ""}

User's instruction: "{prompt}"

Generate a bpy Python script that applies the requested change to the named object(s).

Rules:
- Access objects with bpy.data.objects["name"]  (they already exist in the scene)
- For walls (Room_Wall_*): mesh local-space X=length, Y=thickness, Z=height; object rotation_euler[2] = angle
- To cut a hole: use bmesh.ops.bisect_plane() 4 times then delete inner faces
- Use only bpy/bmesh/mathutils; no external imports
- Handle missing objects: wrap in try/except
- The script must run without errors in Blender 4.x
- End with bpy.ops.object.select_all(action='DESELECT')

Return ONLY the raw Python code — no markdown, no explanations."""

    script = None
    llm_used = llm

    if llm == "claude":
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            return {"error": "ANTHROPIC_API_KEY .env dosyasında eksik"}
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": bpy_prompt}],
            )
            script = msg.content[0].text.strip()
        except Exception as e:
            return {"error": f"Claude hatası: {e}"}
    else:
        gemini_key = os.getenv("GOOGLE_API_KEY")
        if not gemini_key:
            return {"error": "GOOGLE_API_KEY .env dosyasında eksik"}
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            resp   = model.generate_content(bpy_prompt)
            script = resp.text.strip()
        except Exception as e:
            return {"error": f"Gemini hatası: {e}"}

    script = _re.sub(r"^```[a-z]*\n?", "", script, flags=_re.MULTILINE)
    script = script.replace("```", "").strip()

    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post("http://localhost:8766",
                            json={"action": "run_python", "params": {"script": script}})
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        return {"error": f"Blender bağlantı hatası: {e}", "script": script}

    if not result.get("success"):
        err = result.get("result", {}).get("error") or result.get("error", "Bilinmeyen hata")
        return {"error": err, "script": script}

    return {"ok": True, "message": f"'{group_name}' güncellendi", "script": script}


def _get_glass_groups(scene_objects=None):
    """Return {wall_name: {"glass_names": [...], "wall_obj": {...}|None}} for Win_*_Glass* objects."""
    import re as _re, httpx as _httpx
    if scene_objects is None:
        try:
            with _httpx.Client(timeout=8.0) as c:
                r = c.post("http://localhost:8766",
                           json={"action": "list_scene_objects", "params": {}})
                r.raise_for_status()
                res = r.json()
                if not res.get("success"):
                    return {}
                scene_objects = res.get("result", {}).get("objects", [])
        except Exception:
            return {}

    by_name = {o["name"]: o for o in scene_objects}
    PAT = _re.compile(r'^Win_(.+?)_Glass\d*$', _re.IGNORECASE)
    groups: dict = {}
    for obj in scene_objects:
        m = PAT.match(obj["name"])
        if not m:
            continue
        key = m.group(1)
        if key not in groups:
            groups[key] = {"glass_names": [], "wall_obj": by_name.get(key)}
        groups[key]["glass_names"].append(obj["name"])
    return groups


def _get_compass_direction(wall_obj: dict) -> str:
    """Compute the outward-facing compass direction for a wall scene object."""
    import math as _math
    if not wall_obj:
        return "north"
    rot_z = _math.radians(wall_obj.get("rotation_euler", [0, 0, 0])[2])
    ly_x = -_math.sin(rot_z)
    ly_y =  _math.cos(rot_z)
    cx, cy = wall_obj["location"][0], wall_obj["location"][1]
    sign = 1.0 if (cx * ly_x + cy * ly_y) >= 0 else -1.0
    nx, ny = sign * ly_x, sign * ly_y
    if   ny < -0.5: return "north"
    elif ny >  0.5: return "south"
    elif nx >  0.5: return "east"
    elif nx < -0.5: return "west"
    else:
        return ("north" if ny < 0 else "south") + "-" + ("east" if nx > 0 else "west")


def _generate_view_image(prompt: str, wall_name: str):
    """Call Gemini/Imagen image generation. Returns (Path, None) on success or (None, error_str)."""
    import base64, time
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None, "GOOGLE_API_KEY eksik"
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in wall_name)
    out = _VIEWS_DIR / f"{safe}_{int(time.time())}.png"
    try:
        from google import genai as _g
        from google.genai import types as _gt
        client = _g.Client(api_key=api_key)

        # ── gemini-3.1-flash-image ───────────────────────────────────
        resp = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=prompt,
            config=_gt.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        img_data = None
        for cand in resp.candidates:
            for part in cand.content.parts:
                if getattr(part, "inline_data", None) is not None:
                    img_data = part.inline_data.data
                    break
            if img_data:
                break
        if not img_data:
            return None, "Gemini görsel üretmedi (her iki model de çalışmadı)"
        raw = base64.b64decode(img_data) if isinstance(img_data, str) else img_data
        out.write_bytes(raw)
        return out, None
    except Exception as e:
        return None, str(e)


def _apply_glass_view(wall_name: str, glass_names: list, wall_obj: dict, image_path):
    """Send Blender script to apply panoramic image with UV splitting. Returns None or error str."""
    import httpx as _httpx
    img_fwd = str(image_path).replace("\\", "/")
    script = f"""
import bpy, math

wall_name   = {wall_name!r}
glass_names = {glass_names!r}
image_path  = {img_fwd!r}
N = len(glass_names)
if N == 0:
    raise Exception("glass_names empty")

wall_obj = bpy.data.objects.get(wall_name)
if wall_obj:
    rot_z = wall_obj.rotation_euler[2]
    cos_r, sin_r = math.cos(rot_z), math.sin(rot_z)
    wx, wy = wall_obj.location.x, wall_obj.location.y
else:
    rot_z = cos_r = 1.0; sin_r = wx = wy = 0.0

def local_x_of(name):
    obj = bpy.data.objects.get(name)
    if not obj: return 0.0
    return (obj.location.x - wx) * cos_r + (obj.location.y - wy) * sin_r

sorted_panes = sorted(glass_names, key=local_x_of)
img = bpy.data.images.load(image_path, check_existing=False)

for i, pane_name in enumerate(sorted_panes):
    pane = bpy.data.objects.get(pane_name)
    if not pane: continue
    u_offset = i / N
    u_scale  = 1.0 / N

    mat_name = f"WinView_{{wall_name}}_{{i}}"
    old = bpy.data.materials.get(mat_name)
    if old: bpy.data.materials.remove(old)
    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out_n = nodes.new("ShaderNodeOutputMaterial")
    emit  = nodes.new("ShaderNodeEmission")
    tex   = nodes.new("ShaderNodeTexImage")
    sep   = nodes.new("ShaderNodeSeparateXYZ")
    comb  = nodes.new("ShaderNodeCombineXYZ")
    mapp  = nodes.new("ShaderNodeMapping")
    uvc   = nodes.new("ShaderNodeTexCoord")

    tex.image = img
    emit.inputs["Strength"].default_value = 2.0
    mapp.inputs["Location"].default_value[0] = u_offset
    mapp.inputs["Scale"].default_value[0]    = u_scale
    mapp.inputs["Scale"].default_value[1]    = 1.0

    links.new(uvc.outputs["Generated"],  sep.inputs["Vector"])
    links.new(sep.outputs["X"],          comb.inputs["X"])
    links.new(sep.outputs["Z"],          comb.inputs["Y"])
    links.new(comb.outputs["Vector"],    mapp.inputs["Vector"])
    links.new(mapp.outputs["Vector"],    tex.inputs["Vector"])
    links.new(tex.outputs["Color"],      emit.inputs["Color"])
    links.new(emit.outputs["Emission"],  out_n.inputs["Surface"])

    pane.data.materials.clear()
    pane.data.materials.append(mat)
"""
    try:
        with _httpx.Client(timeout=20.0) as c:
            r = c.post("http://localhost:8766",
                       json={"action": "run_python", "params": {"script": script}})
            r.raise_for_status()
            res = r.json()
    except Exception as e:
        return f"Blender bağlantı hatası: {e}"
    if not res.get("success"):
        return res.get("error", "Bilinmeyen Blender hatası")
    return (res.get("result") or {}).get("error")


@app.get("/blender/windows")
def get_window_groups():
    """List Win_*_Glass* objects grouped by wall, with pane counts."""
    groups = _get_glass_groups()
    walls = [
        {"wall_name": k, "pane_count": len(v["glass_names"]), "glass_names": v["glass_names"]}
        for k, v in groups.items()
    ]
    return {"walls": walls, "total_panes": sum(w["pane_count"] for w in walls)}


@app.get("/blender/window-views/catalog")
def get_window_views_catalog():
    """Return all saved window view image entries (newest first)."""
    entries = list(reversed(_catalog_read()))
    return {"entries": entries, "count": len(entries)}


@app.post("/blender/apply-window-view")
def apply_window_view(body: dict):
    """Apply a previously generated image (from catalog) to a wall's glass panes."""
    wall_name = (body.get("wall_name") or "").strip()
    filename  = (body.get("filename")  or "").strip()
    if not wall_name or not filename:
        return {"error": "wall_name ve filename gerekli"}
    img_path = _VIEWS_DIR / filename
    if not img_path.exists():
        return {"error": f"Dosya bulunamadı: {filename}"}
    groups = _get_glass_groups()
    pane_data = groups.get(wall_name)
    if not pane_data:
        return {"error": f"Sahnede '{wall_name}' için cam bulunamadı — sahneyi tazele"}
    err = _apply_glass_view(wall_name, pane_data["glass_names"], pane_data["wall_obj"], img_path)
    if err:
        return {"error": err}
    return {"ok": True, "wall_name": wall_name, "filename": filename}


@app.post("/blender/generate-window-views")
def generate_window_views(body: dict):
    """Generate a Gemini panoramic image per window-wall and apply it to the glass panes."""
    import concurrent.futures

    atmosphere  = (body.get("atmosphere") or "").strip()
    wall_filter = body.get("wall_names")

    if not atmosphere:
        return {"error": "atmosphere boş olamaz"}

    groups = _get_glass_groups()
    if not groups:
        return {"error": "Sahnede Win_*_Glass* nesnesi bulunamadı — önce pencere ekleyin."}

    if wall_filter:
        groups = {k: v for k, v in groups.items() if k in wall_filter}

    def _process_wall(wall_name, pane_data):
        glass_names = pane_data["glass_names"]
        wall_obj    = pane_data["wall_obj"]
        compass     = _get_compass_direction(wall_obj)
        full_prompt = (
            f"Photorealistic architectural window exterior view: {atmosphere}. "
            f"Wide panoramic view facing {compass}. "
            "Consistent lighting and atmosphere. Wide horizontal format, 2:1 aspect ratio. "
            "No window frame or interior elements — pure outdoor scene."
        )
        img_path, err = _generate_view_image(full_prompt, wall_name)
        if err:
            return {"wall_name": wall_name, "error": err}
        apply_err = _apply_glass_view(wall_name, glass_names, wall_obj, img_path)
        import datetime as _dt
        _catalog_append({
            "filename":   img_path.name,
            "url":        f"/generated_views/{img_path.name}",
            "atmosphere": atmosphere,
            "compass":    compass,
            "wall_name":  wall_name,
            "pane_count": len(glass_names),
            "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        })
        return {
            "wall_name":  wall_name,
            "pane_count": len(glass_names),
            "image_path": str(img_path),
            "image_url":  f"/generated_views/{img_path.name}",
            "applied":    apply_err is None,
            "error":      apply_err,
        }

    walls_out = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(groups)) as ex:
        futures = {ex.submit(_process_wall, k, v): k for k, v in groups.items()}
        for fut in concurrent.futures.as_completed(futures):
            try:
                walls_out.append(fut.result())
            except Exception as e:
                walls_out.append({"wall_name": futures[fut], "error": str(e)})

    return {"ok": True, "walls": walls_out}


@app.post("/blender/set-world-hdri")
def set_world_hdri(body: dict):
    """Set an HDRI image as the Blender world background and switch viewport to Material Preview."""
    import httpx

    hdri_path = body.get("hdri_path", "").strip()
    strength  = float(body.get("strength",  1.0))
    rotation  = float(body.get("rotation",  0.0))   # degrees

    if not hdri_path:
        return {"error": "hdri_path gerekli"}

    script = f"""
import bpy, math

HDRI_PATH = {hdri_path!r}
STRENGTH  = {strength:.2f}
ROTATION  = math.radians({rotation:.1f})

world = bpy.context.scene.world
if not world:
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
world.use_nodes = True

nodes = world.node_tree.nodes
links = world.node_tree.links
nodes.clear()

output   = nodes.new("ShaderNodeOutputWorld")
bg       = nodes.new("ShaderNodeBackground")
env      = nodes.new("ShaderNodeTexEnvironment")
mapping  = nodes.new("ShaderNodeMapping")
texcoord = nodes.new("ShaderNodeTexCoord")

try:
    img = bpy.data.images.load(HDRI_PATH, check_existing=True)
    env.image = img
    # Colorspace: try common names for HDR/EXR linear images
    for cs in ('Linear Rec.709', 'Linear', 'Non-Color', 'Raw'):
        try:
            img.colorspace_settings.name = cs
            break
        except Exception:
            continue
except Exception as e:
    raise Exception(f"HDRI yuklenemedi: {{e}}")

bg.inputs["Strength"].default_value = STRENGTH
mapping.inputs["Rotation"].default_value[2] = ROTATION

links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
links.new(mapping.outputs["Vector"],     env.inputs["Vector"])
links.new(env.outputs["Color"],          bg.inputs["Color"])
links.new(bg.outputs["Background"],      output.inputs["Surface"])

# Blender 4.2+: EEVEE_NEXT, older: BLENDER_EEVEE
for engine in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
    try:
        bpy.context.scene.render.engine = engine
        break
    except Exception:
        continue

# Switch all 3D viewports to Material Preview
try:
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'
except Exception:
    pass
"""

    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post("http://localhost:8766",
                            json={"action": "run_python", "params": {"script": script}})
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        return {"error": f"Blender bağlantı hatası: {e}"}

    if not result.get("success"):
        return {"error": result.get("error", "Bilinmeyen hata")}

    script_err = (result.get("result") or {}).get("error")
    if script_err:
        return {"error": script_err}

    return {"ok": True, "message": f"HDRI dünya arka planı ayarlandı. Blender viewport → Material Preview moduna geçti."}


@app.post("/blender/add-window")
def add_window(body: dict):
    """Cut window opening(s) into a wall and place simple frames.

    Supports count > 1 (equally-spaced) and full_width (88% of wall width).
    """
    import httpx

    wall_name  = body.get("wall_name", "")
    win_w      = float(body.get("width",       1.0))
    win_h      = float(body.get("height",      1.2))
    sill_z     = float(body.get("sill_height", 0.9))
    count      = max(1, int(body.get("count",  1)))
    full_width = bool(body.get("full_width",   False))

    if not wall_name:
        return {"error": "wall_name gerekli"}

    script = f"""
import bpy, bmesh, math

wall_name  = {wall_name!r}
WIN_W      = {win_w:.3f}
WIN_H      = {win_h:.3f}
SILL_Z     = {sill_z:.3f}
COUNT      = {count}
FULL_WIDTH = {str(full_width)}
FRAME_T    = 0.05

if wall_name not in bpy.data.objects:
    raise Exception(f"Duvar '{{wall_name}}' sahnede bulunamadi")

wall = bpy.data.objects[wall_name]

xs = [v.co.x for v in wall.data.vertices]
ys = [v.co.y for v in wall.data.vertices]
zs = [v.co.z for v in wall.data.vertices]
wall_len = max(xs) - min(xs)
wall_t   = max(ys) - min(ys)
wall_h   = max(zs) - min(zs)

# Height clamp
win_h_c = min(WIN_H, wall_h - SILL_Z - 0.1)
if win_h_c < 0.2:
    raise Exception(f"Duvar yukseklik icin yetersiz: {{wall_h:.2f}}m")

# ── Compute per-window widths and offsets ──────────────────────
MARGIN = max(0.12, wall_len * 0.04)   # 4% min 12cm on each side
avail  = wall_len - 2 * MARGIN

if FULL_WIDTH:
    # Each window takes its equal share of the wall, 88% filled
    win_w_each = (avail / COUNT) * 0.88
else:
    win_w_each = min(WIN_W, avail)

# Ensure windows fit with at least 5cm gap between them
min_gap   = 0.05
total_gap = avail - win_w_each * COUNT
if total_gap < min_gap * (COUNT + 1):
    # Shrink windows to fit
    win_w_each = (avail - min_gap * (COUNT + 1)) / COUNT

gap = (avail - win_w_each * COUNT) / (COUNT + 1)

# Center X of first window (local coords, wall center = 0)
x0 = -wall_len / 2 + MARGIN + gap + win_w_each / 2
offsets = [x0 + i * (win_w_each + gap) for i in range(COUNT)]

# ── Shared Z coords ────────────────────────────────────────────
loc_z  = wall.location.z   # world Z of wall center = wall_h / 2
lz_bot = SILL_Z - loc_z
lz_top = lz_bot + win_h_c

# ── World helpers ──────────────────────────────────────────────
rot_z = wall.rotation_euler[2]
cos_r = math.cos(rot_z)
sin_r = math.sin(rot_z)
wx, wy = wall.location.x, wall.location.y

def world_xy(lx):
    return wx + cos_r * lx, wy + sin_r * lx

frame_mat = bpy.data.materials.new(f"WinFrame_{{wall_name}}")
frame_mat.diffuse_color = (0.82, 0.80, 0.74, 1.0)

def make_bar(tag, lx_c, wz_c, bw, bh):
    me  = bpy.data.meshes.new("WinBar_Mesh")
    bm2 = bmesh.new()
    bmesh.ops.create_cube(bm2, size=1.0)
    bm2.to_mesh(me)
    bm2.free()
    bar = bpy.data.objects.new(f"Win_{{wall_name}}_{{tag}}", me)
    bpy.context.collection.objects.link(bar)
    for v in me.vertices:
        v.co.x *= bw
        v.co.y *= wall_t + 0.01
        v.co.z *= bh
    bwx, bwy = world_xy(lx_c)
    bar.location = (bwx, bwy, wz_c)
    bar.rotation_euler[2] = rot_z
    me.materials.append(frame_mat)

# ── Open mesh once, cut all windows ────────────────────────────
bm = bmesh.new()
bm.from_mesh(wall.data)

# Z cuts are shared across all windows (same sill/top height)
for co, no in [
    ((0, 0, lz_bot), (0, 0,  1)),
    ((0, 0, lz_top), (0, 0, -1)),
]:
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:]+bm.edges[:]+bm.faces[:],
                           plane_co=co, plane_no=no,
                           use_snap_center=False, clear_outer=False, clear_inner=False)

# X cuts per window
for ox in offsets:
    lx_l = ox - win_w_each / 2
    lx_r = ox + win_w_each / 2
    for co, no in [
        ((lx_l, 0, 0), ( 1, 0, 0)),
        ((lx_r, 0, 0), (-1, 0, 0)),
    ]:
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:]+bm.edges[:]+bm.faces[:],
                               plane_co=co, plane_no=no,
                               use_snap_center=False, clear_outer=False, clear_inner=False)

# Delete faces inside any window region
bm.faces.ensure_lookup_table()
eps = 1e-3
to_del = []
for f in bm.faces:
    c = f.calc_center_median()
    if not (lz_bot + eps < c.z < lz_top - eps):
        continue
    for ox in offsets:
        lx_l = ox - win_w_each / 2
        lx_r = ox + win_w_each / 2
        if lx_l + eps < c.x < lx_r - eps:
            to_del.append(f)
            break

bmesh.ops.delete(bm, geom=to_del, context='FACES')
bm.to_mesh(wall.data)
wall.data.update()
bm.free()

# ── Shared glass material ───────────────────────────────────────
glass_mat = bpy.data.materials.new("WinGlass")
glass_mat.use_nodes = True
try: glass_mat.blend_method  = 'BLEND'
except Exception: pass
try: glass_mat.shadow_method = 'NONE'
except Exception: pass
bsdf_g = glass_mat.node_tree.nodes.get("Principled BSDF")
if bsdf_g:
    bsdf_g.inputs["Base Color"].default_value = (0.82, 0.92, 1.0, 1.0)
    bsdf_g.inputs["Roughness"].default_value  = 0.04
    bsdf_g.inputs["IOR"].default_value        = 1.45
    bsdf_g.inputs["Alpha"].default_value      = 0.08
    try:
        bsdf_g.inputs["Transmission Weight"].default_value = 0.95  # Blender 4.x
    except KeyError:
        try:
            bsdf_g.inputs["Transmission"].default_value = 0.95     # Blender 3.x
        except KeyError:
            pass

# ── Frames + glass panes ────────────────────────────────────────
wz_c = SILL_Z + win_h_c / 2
for i, ox in enumerate(offsets):
    lx_l = ox - win_w_each / 2
    lx_r = ox + win_w_each / 2
    sfx  = str(i + 1) if COUNT > 1 else ""
    make_bar(f"Top{{sfx}}",    ox,              SILL_Z + win_h_c - FRAME_T/2, win_w_each, FRAME_T)
    make_bar(f"Bottom{{sfx}}", ox,              SILL_Z + FRAME_T/2,            win_w_each, FRAME_T)
    make_bar(f"Left{{sfx}}",   lx_l+FRAME_T/2, wz_c,                          FRAME_T, win_h_c)
    make_bar(f"Right{{sfx}}",  lx_r-FRAME_T/2, wz_c,                          FRAME_T, win_h_c)

    # Glass pane — flat plane scaled to inner opening size
    me_g  = bpy.data.meshes.new("WinGlass_Mesh")
    bm_g  = bmesh.new()
    hw    = (win_w_each - FRAME_T) / 2
    hh    = (win_h_c   - FRAME_T) / 2
    for vx, vz in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
        bm_g.verts.new((vx, 0, vz))
    bm_g.verts.ensure_lookup_table()
    bm_g.faces.new(bm_g.verts)
    bm_g.to_mesh(me_g)
    bm_g.free()
    glass_obj = bpy.data.objects.new(f"Win_{{wall_name}}_Glass{{sfx}}", me_g)
    bpy.context.collection.objects.link(glass_obj)
    # Position at center of this window opening
    gwx, gwy = world_xy(ox)
    glass_obj.location      = (gwx, gwy, wz_c)
    glass_obj.rotation_euler[2] = rot_z
    me_g.materials.append(glass_mat)
"""

    try:
        with httpx.Client(timeout=25.0) as client:
            r = client.post("http://localhost:8766",
                            json={"action": "run_python", "params": {"script": script}})
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        return {"error": f"Blender bağlantı hatası: {e}"}

    if not result.get("success"):
        err = result.get("error", "Bilinmeyen hata")
        return {"error": err}

    script_err = (result.get("result") or {}).get("error")
    if script_err:
        return {"error": script_err}

    return {
        "ok": True,
        "message": f"'{wall_name}' duvarına {win_w:.1f}×{win_h:.1f}m pencere açıldı, çerçeve oluşturuldu",
    }


@app.post("/test-facing")
def test_facing(body: dict):
    """Import an asset at origin with rot=0 for direction inspection in Blender."""
    from .tools.blender_tools import test_asset_facing
    asset_id = body.get("asset_id", "")
    return {"result": test_asset_facing(asset_id)}


@app.post("/design", response_model=DesignResponse)
def design(request: DesignRequest):
    from .team import run_team
    try:
        result = run_team(request.prompt, llm=request.llm, floor_plan_image=request.floor_plan_image)
        return DesignResponse(result=result, llm_used=request.llm)
    except Exception as e:
        return DesignResponse(result="", llm_used=request.llm, error=str(e))


class CoachRequest(BaseModel):
    prompt: str
    llm: str = "gemini"


class CoachResponse(BaseModel):
    refined_prompt: str
    rationale: str = ""
    warnings: list = []
    room: dict = {}
    specs: list = []
    house: Optional[dict] = None
    llm_used: str
    error: Optional[str] = None


@app.post("/coach", response_model=CoachResponse)
def coach(request: CoachRequest):
    """Rewrite a rough user prompt as a clean one the design team can execute.
    Catalog-aware: fills defaults, normalizes Turkish direction words, flags gaps."""
    from .prompt_coach import run_prompt_coach
    try:
        out = run_prompt_coach(request.prompt, llm=request.llm)
        return CoachResponse(
            refined_prompt=out["refined_prompt"],
            rationale=out["rationale"],
            warnings=out["warnings"],
            room=out["room"],
            specs=out["specs"],
            house=out["house"],
            llm_used=request.llm,
        )
    except Exception as e:
        return CoachResponse(
            refined_prompt="",
            rationale="",
            warnings=[],
            room={},
            specs=[],
            house=None,
            llm_used=request.llm,
            error=str(e),
        )


class CoachExecRequest(BaseModel):
    room: dict
    specs: list
    house: Optional[dict] = None
    drawn_room: Optional[dict] = None   # custom polygon from "Oda Çiz" tab
    floor_plan_image: Optional[str] = None  # base64 PNG, reserved for future LLM use


class CoachExecResponse(BaseModel):
    result: str
    placed: list = []
    skipped: list = []
    error: Optional[str] = None


class CoachPreviewResponse(BaseModel):
    room: dict
    placed: list = []
    skipped: list = []
    error: Optional[str] = None


def _resolve_specs_for_layout(specs_in, style, room_type):
    """Shared with /coach-preview and /design-from-coach: turn coach specs into
    layout-ready specs (asset_id resolved), returning (resolved, skipped).

    Specs that already carry asset_id (manually added via the yapboz catalog picker)
    are passed through without a catalog lookup.
    """
    from mcp_server.tools.interior_design_tools import find_asset_for_slot
    resolved = []
    skipped = []
    for spec in specs_in:
        if spec.get("asset_id"):
            # asset_id was explicitly set (user picked from catalog or Sketchfab download),
            # so we trust the user's choice and bypass room_type mismatch checks.
            entry = {
                "slot":                spec.get("slot", spec["asset_id"]),
                "asset_id":            spec["asset_id"],
                "placement":           spec.get("placement", "center"),
                "face":                spec.get("face", "default"),
                "room_type":           room_type,
                "location_override":   spec.get("location_override"),
                "rotation_override":   spec.get("rotation_override"),
                "allow_room_mismatch": True,
            }
            if spec.get("on_surface"):
                entry["on_surface"] = spec["on_surface"]
            resolved.append(entry)
            continue
        sub = spec.get("subcategory", "")
        slot_def = {"subcategory": sub, "fallback": []}
        asset = find_asset_for_slot(slot_def, style, room_type)
        if not asset:
            skipped.append(f"{spec.get('slot', sub)} (no catalog match for subcategory={sub})")
            continue
        entry = {
            "slot":               spec.get("slot", sub),
            "asset_id":           asset["id"],
            "placement":          spec.get("placement", "center"),
            "face":               spec.get("face", "default"),
            "room_type":          room_type,
            "location_override":  spec.get("location_override"),
            "rotation_override":  spec.get("rotation_override"),
        }
        if spec.get("on_surface"):
            entry["on_surface"] = spec["on_surface"]
        resolved.append(entry)
    return resolved, skipped


@app.post("/coach-preview", response_model=CoachPreviewResponse)
def coach_preview(request: CoachExecRequest):
    """Compute the layout the way /design-from-coach would, but DO NOT touch
    Blender. The UI uses this to draw an SVG preview before the user commits.
    Each placed item carries location, rotation_z, and dimensions_m so the SVG
    can render the actual footprint."""
    import json
    from .tools.layout_tools import calculate_furniture_layout

    room = request.room or {}
    W = float(room.get("width", 5.0))
    D = float(room.get("depth", 4.0))
    H = float(room.get("height", 2.7))
    room_type = (room.get("type") or "").lower().replace(" ", "_")
    style = room.get("style") or None

    resolved, skipped = _resolve_specs_for_layout(request.specs or [], style, room_type)

    if not resolved:
        return CoachPreviewResponse(
            room={"width": W, "depth": D, "height": H, "type": room_type},
            placed=[], skipped=skipped,
        )

    house = request.house or {}
    offset = (house.get("origin_offset") or [0.0, 0.0, 0.0])
    layout_json = calculate_furniture_layout(
        W, D, H,
        json.dumps(resolved),
        origin_offset=json.dumps(offset),
        container_id=house.get("house_id", ""),
        room_id=house.get("room_id", ""),
        room_type=room_type,
    )
    layout = json.loads(layout_json) if layout_json.startswith("[") else []

    placed = []
    for p in layout:
        if "error" in p:
            asset_id = p.get("asset_id", "")
            slot     = p.get("slot", "?")
            err      = p["error"]
            detail   = f"{slot}"
            if asset_id:
                detail += f" ({asset_id})"
            detail += f": {err}"
            skipped.append(detail)
            continue
        item = {
            "slot":               p["slot"],
            "asset_id":           p["asset_id"],
            "name":               p.get("name", ""),
            "location":           p["location"],
            "rotation_z":         p["rotation_z"],
            "facing_correction_z": p.get("facing_correction_z", 0),
            "dimensions_m":       p.get("dimensions_m", {}),
        }
        if p.get("on_surface"):
            item["on_surface"]   = p["on_surface"]
            item["is_elevated"]  = True
            item["surface_z_m"]  = p.get("surface_z_m", 0.0)
        placed.append(item)

    return CoachPreviewResponse(
        room={"width": W, "depth": D, "height": H, "type": room_type},
        placed=placed,
        skipped=skipped,
    )


@app.post("/design-from-coach", response_model=CoachExecResponse)
def design_from_coach(request: CoachExecRequest):
    """Deterministic execution of a coach-approved plan.

    No agent LLMs in the loop: each spec's asset_id is resolved via search_catalog,
    layout is computed with calculate_furniture_layout, then create_room_in_blender
    (Workflow A) or house import (Workflow B) runs, followed by import_assets_to_blender.
    """
    import json
    from mcp_server import catalog
    from .tools.layout_tools import calculate_furniture_layout
    from .tools.blender_tools import (
        create_room_in_blender, create_polygon_room_in_blender, import_assets_to_blender
    )

    room = request.room or {}
    specs_in = request.specs or []
    house = request.house
    drawn_room = request.drawn_room  # polygon from "Oda Çiz"

    W = float(room.get("width", 5.0))
    D = float(room.get("depth", 4.0))
    H = float(room.get("height", 2.7))
    room_type = (room.get("type") or "").lower().replace(" ", "_")
    style = room.get("style") or None

    # Resolve each spec's asset_id from the catalog (carries override fields too)
    furniture_specs, skipped = _resolve_specs_for_layout(specs_in, style, room_type)

    def _build_room() -> str:
        """Create room geometry. Uses polygon if drawn_room has points, else rectangle."""
        if drawn_room and drawn_room.get("points"):
            raw_pts = drawn_room["points"]
            cx = float(drawn_room.get("center_x", 0.0))
            cy = float(drawn_room.get("center_y", 0.0))
            centered = [[p[0] - cx, p[1] - cy] for p in raw_pts]
            return create_polygon_room_in_blender(centered, H)
        return create_room_in_blender(W, D, H)

    if not furniture_specs and not house:
        # Still create the room so the user gets a blank shell
        try:
            _build_room()
        except Exception as e:
            return CoachExecResponse(result="", error=f"Room creation failed: {e}")
        return CoachExecResponse(
            result=f"Room created ({W}×{D}×{H}m). No furniture placed — catalog had no matches.",
            placed=[], skipped=skipped,
        )

    # ── Workflow B: house first ───────────────────────────────────────
    house_log = ""
    container_id = ""
    room_id = ""
    offset = [0.0, 0.0, 0.0]
    if house:
        container_id = house.get("house_id", "")
        room_id = house.get("room_id", "")
        offset = house.get("origin_offset") or [0.0, 0.0, 0.0]
        house_asset = catalog.get_asset_by_id(container_id) if container_id else None
        if not house_asset:
            return CoachExecResponse(result="", error=f"House '{container_id}' not in catalog")
        house_file = catalog.resolve_file_path(house_asset["file"])
        house_import_json = json.dumps([{
            "slot": "house",
            "file_path": str(house_file),
            "location": [0.0, 0.0, 0.0],
            "rotation_z": 0,
            "file_exists": house_file.exists(),
        }])
        house_log = import_assets_to_blender(house_import_json)
    else:
        # ── Workflow A: from-scratch room ─────────────────────────────
        try:
            house_log = _build_room()
        except Exception as e:
            return CoachExecResponse(result="", error=f"Room creation failed: {e}")

    # ── Layout ──────────────────────────────────────────────────────
    layout_json = calculate_furniture_layout(
        W, D, H,
        json.dumps(furniture_specs),
        origin_offset=json.dumps(offset),
        container_id=container_id,
        room_id=room_id,
        room_type=room_type,
    )

    # ── Import ──────────────────────────────────────────────────────
    import_log = import_assets_to_blender(layout_json)

    # ── Build response ──────────────────────────────────────────────
    placed_list = json.loads(layout_json) if layout_json.startswith("[") else []
    placed_summary = [
        {"slot": p.get("slot"), "name": p.get("name", ""), "location": p.get("location"),
         "rotation_z": p.get("rotation_z")}
        for p in placed_list
        if "error" not in p
    ]
    for p in placed_list:
        if "error" in p:
            skipped.append(f"{p.get('slot','?')}: {p['error']}")

    summary = (
        f"{'House' if house else 'Room'}: {house_log}\n\n"
        f"Furniture ({len(placed_summary)} placed):\n{import_log}"
    )
    if skipped:
        summary += "\n\nSkipped:\n  - " + "\n  - ".join(skipped)

    return CoachExecResponse(
        result=summary,
        placed=placed_summary,
        skipped=skipped,
    )


class HouseRoomRequest(BaseModel):
    house_id: str
    room_id: str
    style: str = "modern"


class HouseRoomResponse(BaseModel):
    result: str
    placed: list
    error: Optional[str] = None


@app.post("/design/house-room", response_model=HouseRoomResponse)
def design_house_room(request: HouseRoomRequest):
    """Deterministic house-room design: no AI agents, pure Python code."""
    import json
    from mcp_server import catalog
    from mcp_server.tools.interior_design_tools import ROOM_PRESETS, find_asset_for_slot
    from .tools.layout_tools import calculate_furniture_layout
    from .tools.blender_tools import import_assets_to_blender

    # 1. Get house asset
    house_asset = catalog.get_asset_by_id(request.house_id)
    if not house_asset:
        return HouseRoomResponse(result="", placed=[], error=f"House '{request.house_id}' not found")

    # 2. Find the target room
    room = None
    for r in house_asset.get("rooms", []):
        if r["room_id"] == request.room_id:
            room = r
            break
    if not room:
        return HouseRoomResponse(result="", placed=[], error=f"Room '{request.room_id}' not found in house '{request.house_id}'")

    # 3. Room dimensions and world offset
    dims = room.get("dimensions_m", {})
    W = float(dims.get("width", 5.0))
    D = float(dims.get("depth", 4.0))
    H = float(dims.get("height", 2.7))
    offset = room.get("origin_offset_m", [0.0, 0.0, 0.0])
    room_type = room.get("room_type", "living_room")

    # 4. Furniture slots from preset
    preset_slots = ROOM_PRESETS.get(room_type, [])
    if not preset_slots:
        return HouseRoomResponse(result="", placed=[], error=f"No preset for room_type '{room_type}'")

    # 5. Find catalog assets for each slot
    style = request.style or None
    furniture_specs = []
    skipped = []
    for slot in preset_slots:
        asset = find_asset_for_slot(slot, style, room_type)
        if not asset:
            if slot.get("optional"):
                skipped.append(slot["slot"])
                continue
            skipped.append(f"{slot['slot']}(required-missing)")
            continue
        furniture_specs.append({
            "slot": slot["slot"],
            "asset_id": asset["id"],
            "placement": slot["placement"],
            "room_type": room_type,
            "face": slot.get("face", "default"),
        })

    if not furniture_specs:
        return HouseRoomResponse(result="", placed=[], error="No furniture assets found for this room")

    # 6. Calculate layout with world offset
    layout_json = calculate_furniture_layout(
        W, D, H,
        json.dumps(furniture_specs),
        origin_offset=json.dumps(offset),
        container_id=request.house_id,
        room_id=request.room_id,
        room_type=room_type,
    )

    # 7. Import house to Blender first
    house_file = catalog.resolve_file_path(house_asset["file"])
    house_import_json = json.dumps([{
        "slot": "house",
        "file_path": str(house_file),
        "location": [0.0, 0.0, 0.0],
        "rotation_z": 0,
        "file_exists": house_file.exists(),
    }])
    house_result = import_assets_to_blender(house_import_json)

    # 8. Import furniture
    furniture_result = import_assets_to_blender(layout_json)

    # 9. Build human-readable response
    placed_list = json.loads(layout_json)
    placed_summary = [
        {"slot": p["slot"], "name": p.get("name", ""), "location": p.get("location")}
        for p in placed_list
        if "error" not in p
    ]
    result_text = (
        f"House: {house_result}\n"
        f"Furniture ({len(placed_summary)} pieces): {furniture_result}"
    )
    if skipped:
        result_text += f"\nSkipped slots: {', '.join(skipped)}"

    return HouseRoomResponse(result=result_text, placed=placed_summary)


# ── Sketchfab Entegrasyonu ────────────────────────────────────────

@app.get("/sketchfab/search")
async def search_sketchfab(q: str, category: Optional[str] = None, count: int = 24):
    """Search Sketchfab for downloadable 3D models. Supports UIDs and URLs.
    Uses /v3/search for high-quality results matching the website.
    """
    import requests, json as _j, re as _re
    
    q = q.strip()
    
    # ── Check if q is a URL or UID ────────────────────────────────────
    uid_match = _re.search(r"([a-f0-9]{32})", q.lower())
    if uid_match:
        uid = uid_match.group(1)
        url = f"https://api.sketchfab.com/v3/models/{uid}"
        try:
            resp = requests.get(url, timeout=10.0)
            if resp.status_code == 200:
                m = resp.json()
                if m.get("isDownloadable"):
                    thumb = ""
                    images = m.get("thumbnails", {}).get("images", [])
                    if images:
                        images.sort(key=lambda x: x.get("width", 0), reverse=True)
                        thumb = images[0].get("url", "")
                    
                    return {"results": [{
                        "uid": m.get("uid"),
                        "name": m.get("name"),
                        "thumbnailUrl": thumb,
                        "viewUrl": m.get("viewerUrl"),
                        "author": m.get("user", {}).get("username"),
                        "polyCount": m.get("faceCount"),
                        "license": m.get("license", {}).get("label"),
                    }]}
                else:
                    return {"error": "Bu model Sketchfab'da 'indirilebilir' (downloadable) olarak işaretlenmemiş."}
        except Exception:
            pass # Fallback to normal search if UID fetch fails

    # ── Normal Search (v3/search endpoint matches website quality) ────
    url = "https://api.sketchfab.com/v3/search"
    params = {
        "q": q,
        "type": "models",
        "downloadable": "true",
        "count": count
    }
    if category:
        params["categories"] = category

    try:
        resp = requests.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        
        content = resp.text.strip()
        if not content:
            return {"error": "Sketchfab boş bir yanıt döndürdü."}
        
        try:
            data = resp.json()
        except _j.JSONDecodeError:
            return {"error": f"Sketchfab yanıtı JSON formatında değil. Yanıt özeti: {content[:100]}..."}
        
        # Get all sketchfab UIDs from local catalog for comparison
        local_uids = set()
        if _CATALOG_PATH.exists():
            try:
                cat_content = _CATALOG_PATH.read_text(encoding="utf-8")
                cat_json = _j.loads(cat_content)
                cat_assets = cat_json.get("assets", cat_json) if isinstance(cat_json, dict) else cat_json
                for a in cat_assets:
                    if isinstance(a, dict) and a.get("source") == "sketchfab":
                        uid = a.get("sketchfab_uid")
                        if uid: local_uids.add(uid)
            except: pass

        results = []
        for m in data.get("results", []):
            thumb = ""
            images = m.get("thumbnails", {}).get("images", [])
            if images:
                images.sort(key=lambda x: x.get("width", 0), reverse=True)
                thumb = images[0].get("url", "")
            
            uid = m.get("uid")
            results.append({
                "uid": uid,
                "name": m.get("name"),
                "thumbnailUrl": thumb,
                "viewUrl": m.get("viewerUrl"),
                "author": m.get("user", {}).get("username"),
                "polyCount": m.get("faceCount"),
                "license": m.get("license", {}).get("label"),
                "is_local": uid in local_uids
            })
        return {"results": results}
    except requests.RequestException as re:
        return {"error": f"Sketchfab API hatası: {str(re)}"}
    except Exception as e:
        return {"error": f"Sketchfab bağlantı veya işlem hatası: {str(e)}"}

@app.get("/sketchfab/recommend")
async def recommend_sketchfab(q: str):
    """Short search for recommendations (used in Prompt Coach)."""
    res = await search_sketchfab(q, count=4)
    if "error" in res:
        return res
    return {"recommendations": res.get("results", [])}

@app.post("/sketchfab/download")
def download_sketchfab_model(body: dict):
    """Start background job to download and convert a Sketchfab model."""
    import uuid, threading
    
    uid      = body.get("uid")
    name     = body.get("name", "Sketchfab Model")
    cat      = body.get("category", "sketchfab")
    sub      = body.get("subcategory", "")
    thumb_url = body.get("thumbnailUrl")
    
    if not uid:
        return {"error": "uid gerekli"}
        
    job_id = f"sf_{str(uuid.uuid4())[:8]}"
    with _am_jobs_lock:
        _am_jobs[job_id] = {"status": "running", "lines": [], "error": None}
        
    def _run_download():
        import httpx, zipfile, shutil, json as _j
        from datetime import date as _date
        
        token = os.getenv("SKETCHFAB_TOKEN")
        if not token:
            with _am_jobs_lock:
                _am_jobs[job_id]["status"] = "error"
                _am_jobs[job_id]["error"]  = "SKETCHFAB_TOKEN .env dosyasında eksik"
            return

        def log(msg):
            with _am_jobs_lock:
                _am_jobs[job_id]["lines"].append(msg)

        try:
            log(f"Sketchfab'dan indirme URL'si alınıyor: {uid}...")
            dl_url = f"https://api.sketchfab.com/v3/models/{uid}/download"
            headers = {"Authorization": f"Token {token}"}
            
            import requests as _requests
            r = _requests.get(dl_url, headers=headers, timeout=20.0)
            if r.status_code == 401:
                raise Exception("Sketchfab Token geçersiz veya yetkisiz (401)")
            r.raise_for_status()
            dl_data = r.json()
            
            gltf_info = dl_data.get("gltf")
            if not gltf_info:
                raise Exception("Bu modelin glTF formatı indirilebilir değil.")
            
            download_link = gltf_info["url"]
            
            temp_dir = _ASSET_LIB_DIR / "models" / "sketchfab" / uid
            temp_dir.mkdir(parents=True, exist_ok=True)
            zip_path = temp_dir / "model.zip"
            
            log(f"ZIP indiriliyor ({round(gltf_info['size']/1048576, 2)} MB)...")
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                with client.stream("GET", download_link) as response:
                    response.raise_for_status()
                    with open(zip_path, "wb") as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)
            
            log("ZIP çıkarılıyor...")
            extract_dir = temp_dir / "extract"
            if extract_dir.exists(): shutil.rmtree(extract_dir)
            extract_dir.mkdir(exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            gltf_file = None
            for p in extract_dir.rglob("*.gltf"):
                gltf_file = p
                break
            if not gltf_file:
                for p in extract_dir.rglob("*.glb"):
                    gltf_file = p
                    break
            
            if not gltf_file:
                raise Exception("ZIP içinde .gltf veya .glb dosyası bulunamadı.")
            
            log("Blender ile .blend formatına dönüştürülüyor ve ölçülüyor...")
            blend_path = temp_dir / f"{uid}.blend"
            dims_path  = temp_dir / "dims.json"
            gltf_escaped = str(gltf_file).replace("\\", "/")
            blend_escaped = str(blend_path).replace("\\", "/")
            dims_escaped = str(dims_path).replace("\\", "/")
            
            script = f"""
import bpy, os, mathutils, json

# Clear existing scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

try:
    print(f"Importing glTF: {{ {gltf_escaped!r} }}")
    bpy.ops.import_scene.gltf(filepath={gltf_escaped!r})

    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        raise Exception("ZIP icinde yuklenebilir mesh bulunamadi (import_scene.gltf bos dondu)")

    # ── Apply all transforms so the .blend stores baked geometry ─────────
    # Many Sketchfab models are exported in cm with a scale=100 object
    # transform. Without applying, the mesh data is in cm and the stored
    # import_scale would need to compensate — causing errors when the blend
    # is appended later. Baking gives us correct metric geometry directly.
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # ── Measure bounding box in world space AFTER baking ─────────────────
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')
    for o in meshes:
        for corner in o.bound_box:
            wc = o.matrix_world @ mathutils.Vector(corner)
            if wc.x < min_x: min_x = wc.x
            if wc.x > max_x: max_x = wc.x
            if wc.y < min_y: min_y = wc.y
            if wc.y > max_y: max_y = wc.y
            if wc.z < min_z: min_z = wc.z
            if wc.z > max_z: max_z = wc.z

    dims = {{
        "width":  round(max_x - min_x, 4),
        "depth":  round(max_y - min_y, 4),
        "height": round(max_z - min_z, 4),
    }}

    # Sanity-check: if any dimension is unrealistically large (>50m) or zero,
    # the model is likely still in cm — apply a unit correction.
    _max_dim = max(dims["width"], dims["depth"], dims["height"])
    _unit_fix = 1.0
    if _max_dim > 50.0:
        _unit_fix = 0.01   # cm → m
    elif _max_dim < 0.005:
        _unit_fix = 100.0  # mm → m (rare)
    if _unit_fix != 1.0:
        dims = {{k: round(v * _unit_fix, 4) for k, v in dims.items()}}
        # Also re-scale objects so they match
        for o in bpy.data.objects:
            o.scale *= _unit_fix
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    os.makedirs(os.path.dirname({blend_escaped!r}), exist_ok=True)

    # Collect all data blocks for export
    all_data = set(bpy.data.objects)
    for o in bpy.data.objects:
        if o.data: all_data.add(o.data)
        for slot in o.material_slots:
            if slot.material:
                all_data.add(slot.material)
                if slot.material.node_tree:
                    for n in slot.material.node_tree.nodes:
                        if hasattr(n, 'image') and n.image:
                            all_data.add(n.image)

    bpy.data.libraries.write({blend_escaped!r}, all_data, fake_user=True, compress=False)

    with open({dims_escaped!r}, 'w') as f:
        json.dump({{"ok": True, "dims": dims}}, f)

except Exception as e:
    import traceback
    with open({dims_escaped!r}, 'w') as f:
        json.dump({{"error": f"Python Hatasi: {{str(e)}}\\n{{traceback.format_exc()}}"}}, f)
"""
            with httpx.Client(timeout=40.0) as c:
                r = c.post("http://localhost:8766",
                           json={"action": "run_python", "params": {"script": script}})
                r.raise_for_status()
                res = r.json()
                
            if not res.get("success"):
                raise Exception(f"Blender Sunucu Hatasi: {res.get('error') or 'Bilinmeyen'}")
            
            import json as _j
            if not dims_path.exists():
                raise Exception("Blender donusumu tamamladi ancak boyut bilgisi dosyasi olusturulamadi.")
            
            with open(dims_path, 'r') as f:
                inner = _j.load(f)
            
            if inner.get("error"):
                raise Exception(f"Blender Donusum Hatasi: {inner['error']}")
            
            measured = inner.get("dims")
            if not measured:
                raise Exception(f"Boyutlar olculemedi. JSON icerigi: {inner}")
            log(f"Boyutlar ölçüldü: {measured['width']}x{measured['depth']}x{measured['height']}m")
            
            asset_id = f"sf_{uid[:12]}"
            thumb_path = _THUMBS_DIR / f"{asset_id}.jpg"
            if thumb_url:
                log("Thumbnail indiriliyor...")
                with httpx.Client(timeout=20.0) as client:
                    r = client.get(thumb_url)
                    if r.status_code == 200:
                        thumb_path.write_bytes(r.content)
            
            from mcp_server.tools.size_reference import guess_subcategory, normalize_dims
            final_sub = sub or guess_subcategory(name)
            dims, scale_ratio = normalize_dims(measured, final_sub)
            import_scale = round(scale_ratio, 6) if scale_ratio else 1.0
            
            log("Kataloğa ekleniyor...")
            file_rel = f"models/sketchfab/{uid}/{uid}.blend"
            entry = {
                "id": asset_id,
                "name": name,
                "category": cat,
                "subcategory": final_sub,
                "source": "sketchfab",
                "sketchfab_uid": uid,
                "file": file_rel,
                "dimensions_m": dims,
                "import_scale": import_scale,
                "added_at": str(_date.today()),
                "placement": {
                    "rules": ["floor"],
                    "anchor": "floor_center",
                    "forward_axis": "+Y"
                }
            }
            
            with _catalog_lock:
                if _CATALOG_PATH.exists():
                    catalog_data = _j.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
                else:
                    catalog_data = {"assets": []}
                
                assets = catalog_data.get("assets", catalog_data) if isinstance(catalog_data, dict) else catalog_data
                if isinstance(catalog_data, dict):
                    catalog_data["assets"] = [a for a in assets if a.get("id") != asset_id]
                    catalog_data["assets"].append(entry)
                else:
                    catalog_data = [a for a in catalog_data if a.get("id") != asset_id]
                    catalog_data.append(entry)
                
                _CATALOG_PATH.write_text(_j.dumps(catalog_data, indent=2, ensure_ascii=False), encoding="utf-8")

            try:
                from mcp_server import catalog as _cat_module
                _cat_module.reload_catalog()
            except:
                pass

            try:
                shutil.rmtree(extract_dir)
                zip_path.unlink()
            except:
                pass
                
            log("Tamamlandı!")
            with _am_jobs_lock:
                _am_jobs[job_id]["status"] = "done"
                _am_jobs[job_id]["asset_id"] = asset_id
                
        except Exception as e:
            log(f"HATA: {str(e)}")
            with _am_jobs_lock:
                _am_jobs[job_id]["status"] = "error"
                _am_jobs[job_id]["error"]  = str(e)

    threading.Thread(target=_run_download, daemon=True).start()
    return {"job_id": job_id}

@app.get("/sketchfab/job/{job_id}")
def get_sketchfab_job(job_id: str):
    """Poll job status for Sketchfab downloads."""
    return get_job(job_id)


# ── System Prompts ─────────────────────────────────────────────────────────

_AGENT_KEYS = ["coach", "space_analyst", "furniture_selector",
               "layout_designer", "blender_executor", "team"]

_AGENT_NAME_TO_KEY = {
    "Interior Architect Coach":  "coach",
    "Space Analyst":             "space_analyst",
    "Furniture Selector":        "furniture_selector",
    "Layout Designer":           "layout_designer",
    "Blender Executor":          "blender_executor",
    "Interior Architect Team":   "team",
}


def _read_default_prompts() -> dict:
    """Capture hardcoded instruction lists from each create_* function without running any LLM."""
    captured: dict = {}

    # Patch agno Agent to intercept instructions kwarg
    try:
        import agno.agent as _agno_agent
        _orig_agent = _agno_agent.Agent.__init__

        def _cap_agent(self, *args, **kwargs):
            name = kwargs.get("name", "")
            instr = kwargs.get("instructions", [])
            if name and isinstance(instr, list):
                captured[name] = "\n".join(instr)

        _agno_agent.Agent.__init__ = _cap_agent
        try:
            from .prompt_coach       import create_prompt_coach
            from .space_analyst      import create_space_analyst
            from .furniture_selector import create_furniture_selector
            from .layout_designer    import create_layout_designer
            from .blender_executor   import create_blender_executor
            create_prompt_coach(None)
            create_space_analyst(None)
            create_furniture_selector(None)
            create_layout_designer(None)
            create_blender_executor(None)
        finally:
            _agno_agent.Agent.__init__ = _orig_agent
    except Exception:
        pass

    # Patch agno Team for team.py
    try:
        import agno.team as _agno_team
        _orig_team = _agno_team.Team.__init__

        def _cap_team(self, *args, **kwargs):
            instr = kwargs.get("instructions", [])
            if isinstance(instr, list):
                captured["Interior Architect Team"] = "\n".join(instr)

        _agno_team.Team.__init__ = _cap_team
        try:
            from .team import create_interior_team
            create_interior_team("gemini")
        except Exception:
            pass
        finally:
            _agno_team.Team.__init__ = _orig_team
    except Exception:
        pass

    return {v: captured.get(k, "") for k, v in _AGENT_NAME_TO_KEY.items()}


@app.get("/system/prompts")
def get_system_prompts():
    """Return current instruction text for all 6 agents (custom or default)."""
    import json as _j
    custom: dict = {}
    if _AGENT_PROMPTS_FILE.exists():
        try:
            custom = _j.loads(_AGENT_PROMPTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            custom = {}

    defaults = _read_default_prompts()
    prompts = {k: custom.get(k, defaults.get(k, "")) for k in _AGENT_KEYS}
    return {"prompts": prompts, "source": "custom" if custom else "default"}


@app.post("/system/prompts")
def save_system_prompts(body: dict):
    """Persist custom instructions to agent_prompts.json."""
    import json as _j
    prompts = body.get("prompts", {})
    if not isinstance(prompts, dict):
        return {"error": "prompts must be an object"}
    to_save = {k: v for k, v in prompts.items()
               if k in _AGENT_KEYS and isinstance(v, str)}
    with _prompts_lock:
        # Merge with existing so single-agent saves don't wipe others
        existing: dict = {}
        if _AGENT_PROMPTS_FILE.exists():
            try:
                existing = _j.loads(_AGENT_PROMPTS_FILE.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        existing.update(to_save)
        _AGENT_PROMPTS_FILE.write_text(
            _j.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return {"ok": True, "saved_keys": list(to_save.keys())}


@app.delete("/system/prompts/{agent_key}")
def reset_agent_prompt(agent_key: str):
    """Remove a single agent's custom prompt so it falls back to default."""
    import json as _j
    if agent_key not in _AGENT_KEYS:
        return {"error": f"Unknown agent key: {agent_key}"}
    if not _AGENT_PROMPTS_FILE.exists():
        return {"ok": True, "note": "no custom prompts file"}
    with _prompts_lock:
        try:
            data = _j.loads(_AGENT_PROMPTS_FILE.read_text(encoding="utf-8"))
            data.pop(agent_key, None)
            _AGENT_PROMPTS_FILE.write_text(
                _j.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            return {"error": str(e)}
    return {"ok": True, "reset": agent_key}
