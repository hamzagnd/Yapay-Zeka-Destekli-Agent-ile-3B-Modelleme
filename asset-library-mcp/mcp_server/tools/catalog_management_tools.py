"""MCP tools for adding new assets to the catalog via Claude."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import textwrap
import zipfile
from datetime import date
from pathlib import Path
from typing import Optional

from .. import catalog as _cat

# ── Blender background measurement script ────────────────────────────────
_MEASURE_PY = textwrap.dedent("""\
    import bpy, json, sys
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        print("RESULT:{}")
        sys.exit()
    xs, ys, zs, total_faces = [], [], [], 0
    for obj in meshes:
        for v in obj.data.vertices:
            co = obj.matrix_world @ v.co
            xs.append(co.x); ys.append(co.y); zs.append(co.z)
        total_faces += len(obj.data.polygons)
    seen, slots = set(), []
    for obj in meshes:
        for slot in obj.material_slots:
            if slot.material and slot.material.name not in seen:
                seen.add(slot.material.name)
                slots.append(slot.material.name)
    result = {
        "width": round(max(xs)-min(xs),3), "depth": round(max(ys)-min(ys),3),
        "height": round(max(zs)-min(zs),3), "poly_count": total_faces,
        "material_slots": slots,
    }
    print("RESULT:" + json.dumps(result))
""")

# ── Category / style guessing ─────────────────────────────────────────────
_CAT_KW = {
    "seating":      ["sofa","couch","armchair","chair","stool","bench","lounge","chesterfield"],
    "tables":       ["table","desk","counter","nightstand","console","coffee"],
    "storage":      ["wardrobe","cabinet","shelf","dresser","rack","bookshelf"],
    "beds":         ["bed","bunk","mattress"],
    "lighting":     ["lamp","light","pendant","sconce","chandelier"],
    "decor":        ["rug","plant","mirror","curtain","vase","clock","artwork"],
    "kitchen":      ["fridge","oven","sink","hood","microwave","cart"],
    "bathroom":     ["bathtub","toilet","shower","towel"],
    "outdoor":      ["garden","planter","bbq","swing"],
    "architecture": ["house","building","arch","storey","floor","villa","apartment"],
}
_SUBCAT_MAP = {
    "seating":  ["sofa","armchair","dining_chair","bar_stool","bench","lounge_chair"],
    "tables":   ["dining_table","coffee_table","side_table","desk","nightstand","console_table"],
    "storage":  ["wardrobe","cabinet","bookshelf","tv_stand","dresser"],
    "beds":     ["single_bed","double_bed","queen_bed","king_bed","bunk_bed"],
    "lighting": ["floor_lamp","table_lamp","pendant","ceiling_light","wall_sconce","chandelier"],
    "decor":    ["rug","plant","artwork","mirror","curtain","vase"],
    "kitchen":  ["refrigerator","oven","dishwasher","sink","hood","microwave","coffee_station"],
    "bathroom": ["bathtub","toilet","sink_bathroom","shower","bathroom_cabinet"],
    "outdoor":  ["garden_chair","garden_table","planter"],
    "architecture": ["residential","commercial","apartment","villa"],
}
_STYLE_KW = {
    "chesterfield": ["classic","victorian","chesterfield"],
    "industrial":   ["industrial","metal","raw"],
    "modern":       ["modern","contemporary"],
    "mid_century":  ["mid-century","retro","vintage"],
    "nordic":       ["scandinavian","nordic","minimalist"],
    "rustic":       ["rustic","farmhouse"],
}
_TEX_PATTERNS = [
    (r"diff|albedo|col(?!or)|basecolor","diffuse"),
    (r"rough","roughness"), (r"metal","metallic"),
    (r"nor_gl|normal_gl|nrm_gl","normal_gl"),
    (r"nor_dx|normal_dx|nrm_dx","normal_dx"),
    (r"nor(?!_)|nrm(?!_)","normal_gl"),
    (r"disp|height(?!_)","displacement"),
    (r"\bao\b|ambient_occ","ao"),
    (r"emit|emiss","emission"), (r"opac|alpha|mask","opacity"),
]


def _guess_cat(name: str) -> str:
    low = name.lower()
    for c, kws in _CAT_KW.items():
        if any(k in low for k in kws):
            return c
    return "seating"

def _guess_subcat(cat: str, name: str) -> str:
    low = name.lower()
    for s in _SUBCAT_MAP.get(cat, []):
        if s.split("_")[0] in low:
            return s
    return _SUBCAT_MAP.get(cat, [""])[0]

def _guess_style(name: str) -> list:
    low = name.lower()
    for key, styles in _STYLE_KW.items():
        if key in low:
            return styles
    return ["modern"]

def _tex_type(filename: str) -> str:
    low = filename.lower()
    for pat, t in _TEX_PATTERNS:
        if re.search(pat, low):
            return t
    return "other"

def _find_blender() -> str | None:
    if shutil.which("blender"):
        return "blender"
    for ver in ["4.5","4.3","4.2","4.1","4.0","3.6"]:
        p = Path(f"C:/Program Files/Blender Foundation/Blender {ver}/blender.exe")
        if p.exists():
            return str(p)
    return None

async def _measure_async(blend_path: Path, blender_exe: str) -> dict:
    tmp = blend_path.parent / "_measure_tmp.py"
    tmp.write_text(_MEASURE_PY, encoding="utf-8")
    try:
        proc = await asyncio.create_subprocess_exec(
            blender_exe, "--background", str(blend_path), "--python", str(tmp),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
        except asyncio.TimeoutError:
            proc.kill()
            return {}
        for line in stdout.decode(errors="replace").splitlines():
            if line.startswith("RESULT:"):
                return json.loads(line[7:])
    except Exception:
        pass
    finally:
        tmp.unlink(missing_ok=True)
    return {}


# ── Tool registration ─────────────────────────────────────────────────────
def register_tools(mcp, client):

    @mcp.tool()
    async def analyze_asset(file_path: str) -> str:
        """Analyze a .blend or .zip file and generate a draft catalog entry.

        Extracts the file (if zip), measures dimensions via Blender background mode,
        auto-guesses category/style from the filename, and returns a draft JSON entry
        plus a human-readable summary for the user to review.

        Args:
            file_path: Absolute path to the .blend or .zip file to analyze
        """
        src = Path(file_path)
        if not src.exists():
            return f"Hata: dosya bulunamadı — {file_path}"

        lib_root = _cat._library_root()
        is_zip = src.suffix.lower() == ".zip"

        # ── Zip extraction ────────────────────────────────────────────────
        if is_zip:
            with zipfile.ZipFile(src) as zf:
                entries = zf.namelist()
            blend_files = [e for e in entries if e.endswith(".blend")]
            tex_files   = [e for e in entries
                           if re.search(r"\.(jpg|jpeg|png|exr|hdr|tiff?|tga|bmp)$", e, re.I)]
            if not blend_files:
                return "Hata: zip içinde .blend dosyası yok."
            blend_entry = blend_files[0]
            stem = Path(blend_entry).stem
        else:
            stem = src.stem
            blend_entry = src.name
            tex_files = [
                f.name for f in src.parent.iterdir()
                if re.search(r"\.(jpg|jpeg|png|exr|hdr|tiff?|tga|bmp)$", f.name, re.I)
            ]

        base_id    = re.sub(r"[_\-]?\d+k$", "", stem, flags=re.I)
        res_match  = re.search(r"(\d+k)", stem, re.I)
        resolution = res_match.group(1).lower() if res_match else "unknown"

        guessed_cat    = _guess_cat(base_id)
        guessed_subcat = _guess_subcat(guessed_cat, base_id)
        guessed_styles = _guess_style(base_id)

        # ── Extract zip to models/ ────────────────────────────────────────
        if is_zip:
            dest = lib_root / "models" / guessed_cat / base_id
            if not dest.exists():
                dest.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(src) as zf:
                    zf.extractall(dest)
            blend_abs = dest / blend_entry
        else:
            blend_abs = src
            dest = src.parent

        rel_blend = f"models/{guessed_cat}/{base_id}/{blend_entry}".replace("\\", "/")

        # ── Blender measurement ───────────────────────────────────────────
        blender_exe = _find_blender()
        dims: dict = {}
        poly_count = None
        mat_slots: list = []

        if blender_exe and blend_abs.exists():
            data = await _measure_async(blend_abs, blender_exe)
            if data:
                dims       = {"width": data["width"], "depth": data["depth"], "height": data["height"]}
                poly_count = data.get("poly_count")
                mat_slots  = [{"slot": s, "type": "unknown", "default_color": "#888888"}
                              for s in data.get("material_slots", [])]

        if not dims:
            dims = {"width": None, "depth": None, "height": None}
        if not mat_slots:
            mat_slots = [{"slot": "main_material", "type": "unknown", "default_color": "#888888"}]

        # ── Textures ─────────────────────────────────────────────────────
        textures: dict = {}
        for tf in tex_files:
            ttype = _tex_type(Path(tf).name)
            textures[ttype] = f"models/{guessed_cat}/{base_id}/{tf}".replace("\\", "/")

        # ── Draft entry ───────────────────────────────────────────────────
        draft = {
            "id":                  base_id,
            "name":                stem.replace("_", " ").title(),
            "category":            guessed_cat,
            "subcategory":         guessed_subcat,
            "style":               guessed_styles,
            "tags":                [],
            "file":                rel_blend,
            "texture_resolution":  resolution,
            "material_slots":      mat_slots,
            "textures":            textures,
            "dimensions_m":        dims,
            "origin":              "floor_center",
            "facing_correction_z": 0,
            "placement_hints":     [],
            "poly_count":          poly_count,
            "added_at":            str(date.today()),
            "source":              str(src),
        }

        dim_str = (
            f"{dims['width']}w × {dims['depth']}d × {dims['height']}h m"
            if dims.get("width") else "ölçülemedi (Blender bulunamadı)"
        )

        summary = f"""=== TASLAK KATALOG GİRİŞİ ===

ID         : {draft['id']}
İsim       : {draft['name']}   ← düzenleyebilirsin
Kategori   : {draft['category']} / {draft['subcategory']}   ← tahmin
Stil       : {', '.join(draft['style'])}   ← tahmin
Etiketler  : (boş — eklemek ister misin?)
Boyut      : {dim_str}
Poly       : {f"{poly_count:,}" if poly_count else "?"}
Origin     : floor_center   ← doğrula
Yön düz.   : 0   ← BİLİNMİYOR — kontrol et!
Dosya      : {rel_blend}
Textureler : {', '.join(textures.keys()) if textures else '(yok)'}

─────────────────────────────────────────────
TASLAK JSON (düzenlemek için kopyala):
{json.dumps(draft, indent=2, ensure_ascii=False)}
─────────────────────────────────────────────

Sonraki adımlar:
1. Yönü kontrol et → preview_asset_in_blender("{str(blend_abs)}")
   (Blender'da Numpad 7 üstten görünüm — ön yüzey hangi yöne bakıyor?)
2. Gerekli düzeltmeleri söyle (facing, stil, isim, etiketler...)
3. Kaydet → save_asset_to_catalog(düzeltilmiş_json)"""

        return summary

    # ──────────────────────────────────────────────────────────────────────

    @mcp.tool()
    async def preview_asset_in_blender(file_path: str) -> str:
        """Import an asset into Blender at origin with zero rotation for inspection.

        Use this to check the default facing direction of a model before cataloging.
        After importing: in Blender press Numpad 7 (top view) or Numpad 1 (front view).

        Args:
            file_path: Absolute path to the .blend file to preview
        """
        result = await client.call("import_blend_asset", {
            "file_path": file_path,
            "location": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": 1.0,
            "name": "PREVIEW_" + Path(file_path).stem,
        })
        if "error" in result:
            return f"Import hatası: {result['error']}"

        return f"""Model Blender'a yüklendi: {Path(file_path).name}
Konum: [0, 0, 0]  |  Rotasyon: 0°

Yönü kontrol etmek için:
  Numpad 7  →  Üstten görünüm (yön kalibrasyonu için)
  Numpad 1  →  Önden görünüm

Koordinat sistemi (üstten bakış):
       +Y (Kuzey)
          ↑
  -X ←   ·   → +X
          ↓
       -Y (Güney)

Mobilyanın ön yüzeyi hangi yöne bakıyor?
  Kuzey (+Y) → facing_correction_z = 0    (düzeltme yok)
  Güney (-Y) → facing_correction_z = 180
  Doğu  (+X) → facing_correction_z = 90
  Batı  (-X) → facing_correction_z = 270

Gördüğünü söyle, JSON'u güncelleyip save_asset_to_catalog ile kaydedelim."""

    # ──────────────────────────────────────────────────────────────────────

    @mcp.tool()
    async def save_asset_to_catalog(entry_json: str) -> str:
        """Save a catalog entry to Catalog.json.

        Takes the (optionally edited) JSON from analyze_asset and writes it to the catalog.
        Required fields: id, name, category, subcategory, file.
        Adds added_at automatically if missing.

        Args:
            entry_json: JSON string of the complete catalog entry
        """
        try:
            entry = json.loads(entry_json)
        except json.JSONDecodeError as e:
            return f"Geçersiz JSON: {e}"

        for field in ("id", "name", "category", "subcategory", "file"):
            if not entry.get(field):
                return f"Eksik zorunlu alan: '{field}'"

        entry.setdefault("added_at", str(date.today()))
        entry.setdefault("facing_correction_z", 0)
        entry.setdefault("origin", "floor_center")

        lib_root = _cat._library_root()
        catalog_path = lib_root / "Catalog.json"

        with open(catalog_path, encoding="utf-8") as f:
            catalog_data = json.load(f)

        existing = {a["id"] for a in catalog_data["assets"]}
        updated = entry["id"] in existing
        if updated:
            catalog_data["assets"] = [a for a in catalog_data["assets"] if a["id"] != entry["id"]]

        catalog_data["assets"].append(entry)

        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, indent=2, ensure_ascii=False)

        _cat._catalog_cache = None  # invalidate cache

        action = "güncellendi" if updated else "eklendi"
        dims = entry.get("dimensions_m", {})
        dim_str = f"{dims.get('width','?')}w × {dims.get('depth','?')}d × {dims.get('height','?')}h m"
        return f"""✓ '{entry['name']}' kataloğa {action}!

ID         : {entry['id']}
Kategori   : {entry['category']} / {entry['subcategory']}
Stil       : {', '.join(entry.get('style', []))}
Boyut      : {dim_str}
Yön düz.   : {entry.get('facing_correction_z', 0)}°
Dosya      : {entry['file']}"""

    # ──────────────────────────────────────────────────────────────────────

    @mcp.tool()
    async def list_pending_assets() -> str:
        """List .zip and .blend files in the asset_library root and zip/ folder
        that are not yet in the catalog. Use this to find assets ready to analyze.
        """
        lib_root = _cat._library_root()
        zip_dir  = lib_root / "zip"

        existing_ids = {a["id"] for a in _cat.get_all_assets()}

        candidates = []
        for z in sorted(lib_root.glob("*.zip")) + sorted(zip_dir.glob("*.zip") if zip_dir.exists() else []):
            stem   = z.stem
            aid    = re.sub(r"[_\-]?\d+k$", "", stem, flags=re.I)
            status = "katalogda var" if aid in existing_ids else "henüz eklenmemiş"
            candidates.append(f"  [{status}]  {z.name}  →  {z}")

        for b in sorted(lib_root.glob("*.blend")):
            stem   = b.stem
            aid    = re.sub(r"[_\-]?\d+k$", "", stem, flags=re.I)
            status = "katalogda var" if aid in existing_ids else "henüz eklenmemiş"
            candidates.append(f"  [{status}]  {b.name}  →  {b}")

        if not candidates:
            return "Kök klasörde veya zip/ içinde .zip / .blend dosyası bulunamadı."

        return "Bulunan dosyalar:\n" + "\n".join(candidates)
