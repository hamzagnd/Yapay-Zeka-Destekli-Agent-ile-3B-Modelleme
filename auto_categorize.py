#!/usr/bin/env python3
"""
auto_categorize.py — Hibrit otomatik asset kategorizasyon.

Aşamalar (her aşama bir sonraki için confidence kazanır):
  1) Filename + material name regex      → kategori/subkategori/style tahmini
  2) Blender headless                    → bbox, mesh PCA (forward axis), poly_count, material_slots
  3) PCA + kategori heuristic            → forward_axis tahmini
  4) Gemini Flash (toplam confidence < 0.8 ise)  → semantic_tags, room_types, compatible_with refine

Kullanım (kütüphane):
    from auto_categorize import auto_categorize_blend
    result = auto_categorize_blend(Path("model.blend"))
    # → {"category": "...", "subcategory": "...", "forward_axis": "+Y", "confidence": 0.95, ...}

CLI testi:
    python auto_categorize.py path/to/model.blend
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
TAXONOMY_PATH = ROOT_DIR / "taxonomy.json"

# ── Sabit eşleştirmeler ───────────────────────────────────────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "seating":      ["sofa", "couch", "armchair", "chair", "stool", "bench", "pouf", "chesterfield", "lounge", "recliner"],
    "tables":       ["table", "desk", "counter", "nightstand", "console", "coffee"],
    "storage":      ["wardrobe", "cabinet", "shelf", "dresser", "rack", "bookcase", "bookshelf", "tv_stand"],
    "beds":         ["bed", "bunk", "mattress", "crib"],
    "lighting":     ["lamp", "light", "pendant", "sconce", "chandelier", "lantern"],
    "decor":        ["rug", "carpet", "plant", "mirror", "curtain", "vase", "clock", "artwork", "painting"],
    "kitchen":      ["fridge", "refrigerator", "oven", "sink", "hood", "microwave", "cart", "coffee_machine", "coffee_cart", "stove"],
    "bathroom":     ["bathtub", "toilet", "shower", "towel"],
    "outdoor":      ["garden", "planter", "bbq", "swing", "pergola"],
    "architecture": ["house", "building", "arch", "storey", "story", "home", "villa", "apartment", "cabin"],
}

SUBCAT_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "seating": {
        "sofa":          ["sofa", "couch", "chesterfield"],
        "armchair":      ["armchair", "lounge", "recliner"],
        "dining_chair":  ["dining_chair", "dinner_chair"],
        "office_chair":  ["office_chair", "task_chair", "swivel"],
        "bar_stool":     ["stool", "barstool"],
        "bench":         ["bench"],
        "pouf":          ["pouf", "ottoman"],
    },
    "tables": {
        "desk":          ["desk", "workstation"],
        "coffee_table":  ["coffee", "cocktail"],
        "dining_table":  ["dining", "dinner"],
        "side_table":    ["side", "end_table", "accent"],
        "nightstand":    ["nightstand", "bedside"],
        "console_table": ["console"],
    },
    "storage": {
        "wardrobe":      ["wardrobe", "armoire", "closet"],
        "cabinet":       ["cabinet", "cupboard"],
        "bookshelf":     ["bookshelf", "bookcase"],
        "tv_stand":      ["tv_stand", "media"],
        "dresser":       ["dresser", "chest"],
    },
    "kitchen": {
        "coffee_station":["coffee_cart", "coffee_machine", "coffeecart"],
        "refrigerator":  ["fridge", "refrigerator"],
        "oven":          ["oven", "stove"],
        "microwave":     ["microwave"],
    },
    "architecture": {
        "residential":   ["house", "home", "storey", "story", "two-story", "villa", "cabin"],
        "commercial":    ["office_building", "shop"],
        "apartment":     ["apartment", "flat"],
    },
}

STYLE_HINTS: dict[str, list[str]] = {
    "chesterfield":  ["classic", "victorian", "chesterfield"],
    "mid_century":   ["mid-century", "retro", "vintage"],
    "mid-century":   ["mid-century", "retro", "vintage"],
    "midcentury":    ["mid-century", "retro", "vintage"],
    "industrial":    ["industrial", "metal", "raw"],
    "rustic":        ["rustic", "farmhouse", "wood"],
    "scandinavian":  ["scandinavian", "nordic", "minimalist"],
    "nordic":        ["scandinavian", "nordic", "minimalist"],
    "art_deco":      ["art_deco", "glamour", "luxury"],
    "minimalist":    ["minimalist", "clean", "simple"],
    "modern":        ["modern", "contemporary"],
    "contemporary":  ["modern", "contemporary"],
    "classic":       ["classic", "traditional"],
}

# Subkategori → varsayılan room_types
SUBCAT_TO_ROOMS: dict[str, list[str]] = {
    "sofa":           ["living_room", "lobby"],
    "armchair":       ["living_room", "office", "home_office"],
    "dining_chair":   ["dining_room"],
    "office_chair":   ["office", "home_office", "study"],
    "bar_stool":      ["kitchen", "bar"],
    "bench":          ["lobby", "outdoor", "dining_room"],
    "pouf":           ["living_room", "bedroom"],
    "desk":           ["office", "home_office", "study"],
    "coffee_table":   ["living_room"],
    "dining_table":   ["dining_room"],
    "side_table":     ["living_room", "bedroom"],
    "nightstand":     ["bedroom"],
    "console_table":  ["lobby", "living_room"],
    "wardrobe":       ["bedroom"],
    "cabinet":        ["living_room", "office", "bedroom"],
    "bookshelf":      ["office", "study", "living_room"],
    "tv_stand":       ["living_room"],
    "dresser":        ["bedroom"],
    "single_bed":     ["bedroom"],
    "double_bed":     ["bedroom"],
    "queen_bed":      ["bedroom"],
    "king_bed":       ["bedroom"],
    "coffee_station": ["kitchen", "office", "lobby"],
    "refrigerator":   ["kitchen"],
    "floor_lamp":     ["living_room", "bedroom", "office"],
    "table_lamp":     ["bedroom", "office", "living_room"],
    "pendant":        ["dining_room", "kitchen"],
    "residential":    ["residential"],
    "apartment":      ["residential"],
}

# Subkategori → uyumlu eşleştirmeler (companion assets)
SUBCAT_COMPATIBLE: dict[str, list[str]] = {
    "desk":           ["office_chair", "armchair", "table_lamp", "bookshelf"],
    "office_chair":   ["desk"],
    "sofa":           ["coffee_table", "side_table", "floor_lamp", "rug"],
    "armchair":       ["side_table", "floor_lamp"],
    "coffee_table":   ["sofa", "armchair"],
    "dining_table":   ["dining_chair", "pendant"],
    "dining_chair":   ["dining_table"],
    "double_bed":     ["nightstand", "wardrobe", "floor_lamp"],
    "queen_bed":      ["nightstand", "wardrobe", "floor_lamp"],
    "nightstand":     ["double_bed", "queen_bed", "table_lamp"],
    "coffee_station": ["bar_stool", "kitchen_counter"],
}

TAG_KEYWORDS: list[str] = [
    "leather", "wood", "metal", "steel", "glass", "marble", "plastic",
    "fabric", "concrete", "chrome", "brass", "gold", "black", "white",
    "brown", "gray", "tufted", "weathered", "vintage",
]

SEMANTIC_TAG_VOCABULARY: dict[str, list[str]] = {
    "rooms": ["office", "home_office", "study", "living_room", "bedroom",
              "dining_room", "kitchen", "bathroom", "lobby", "outdoor"],
    "purpose": ["work", "rest", "dining", "storage", "decoration",
                "lighting", "circulation"],
    "audience": ["residential", "commercial", "hospitality"],
    "ambience": ["minimal", "cozy", "industrial", "classic", "modern",
                 "luxury", "vintage", "rustic"],
}

CONTAINER_CATEGORIES = {"architecture"}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x) for x in value if isinstance(x, str) and x.strip()]


def _dict_of_string_lists(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key, items in value.items():
        vals = _string_list(items)
        if isinstance(key, str) and vals:
            out[key] = vals
    return out


def _nested_dict_of_string_lists(value: Any) -> dict[str, dict[str, list[str]]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict[str, list[str]]] = {}
    for key, nested in value.items():
        vals = _dict_of_string_lists(nested)
        if isinstance(key, str) and vals:
            out[key] = vals
    return out


def _load_taxonomy(path: Path = TAXONOMY_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"  [auto_categorize] taxonomy yuklenemedi ({path.name}): {e}", file=sys.stderr)
        return {}


def _apply_taxonomy(data: dict[str, Any]) -> None:
    global CATEGORY_KEYWORDS, SUBCAT_KEYWORDS, STYLE_HINTS
    global SUBCAT_TO_ROOMS, SUBCAT_COMPATIBLE, TAG_KEYWORDS
    global SEMANTIC_TAG_VOCABULARY

    category_keywords = _dict_of_string_lists(data.get("category_keywords"))
    if category_keywords:
        CATEGORY_KEYWORDS = category_keywords

    subcategory_keywords = _nested_dict_of_string_lists(data.get("subcategory_keywords"))
    if subcategory_keywords:
        SUBCAT_KEYWORDS = subcategory_keywords

    style_hints = _dict_of_string_lists(data.get("style_hints"))
    if style_hints:
        STYLE_HINTS = style_hints

    subcategory_rooms = _dict_of_string_lists(data.get("subcategory_rooms"))
    if subcategory_rooms:
        SUBCAT_TO_ROOMS = subcategory_rooms

    subcategory_compatible = _dict_of_string_lists(data.get("subcategory_compatible"))
    if subcategory_compatible:
        SUBCAT_COMPATIBLE = subcategory_compatible

    tag_keywords = _string_list(data.get("tag_keywords"))
    if tag_keywords:
        TAG_KEYWORDS = tag_keywords

    semantic_tag_vocabulary = _dict_of_string_lists(data.get("semantic_tag_vocabulary"))
    if semantic_tag_vocabulary:
        SEMANTIC_TAG_VOCABULARY = semantic_tag_vocabulary


_apply_taxonomy(_load_taxonomy())

# ── Veri sınıfları ────────────────────────────────────────────────────────
@dataclass
class CategorizationResult:
    """Tüm otomatik kategorize çıktısı tek bir yerde."""
    # Core taxonomy
    category:        str = ""
    subcategory:     str = ""
    style:           list[str] = field(default_factory=list)
    tags:            list[str] = field(default_factory=list)

    # New semantic layer
    semantic_tags:   list[str] = field(default_factory=list)
    room_types:      list[str] = field(default_factory=list)
    compatible_with: list[str] = field(default_factory=list)
    is_container:    bool = False
    scale_class:     str = "human"

    # Geometry (from Blender measurement)
    dimensions_m:    dict[str, float] = field(default_factory=dict)
    footprint:       dict[str, float] = field(default_factory=dict)
    poly_count:      int = 0
    material_slots:  list[dict[str, str]] = field(default_factory=list)

    # Orientation
    forward_axis:        str = "+Y"
    facing_correction_z: int = 0

    # Per-field confidence (0..1)
    confidences:     dict[str, float] = field(default_factory=dict)

    # Where each value came from: "rule" / "pca" / "llm" / "default"
    sources:         dict[str, str] = field(default_factory=dict)

    def overall_confidence(self) -> float:
        if not self.confidences:
            return 0.0
        return sum(self.confidences.values()) / len(self.confidences)


# ── Blender ölçüm scripti (background modda çalışır) ─────────────────────
# Bbox + mesh PCA + material slots döndürür.
_MEASURE_PY = textwrap.dedent("""\
    import bpy, json, sys, math

    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        print("RESULT:{}")
        sys.exit()

    xs, ys, zs, total_faces = [], [], [], 0
    # PCA için world-space koordinatları topla
    coords = []
    for obj in meshes:
        for v in obj.data.vertices:
            co = obj.matrix_world @ v.co
            xs.append(co.x); ys.append(co.y); zs.append(co.z)
            coords.append((co.x, co.y, co.z))
        total_faces += len(obj.data.polygons)

    seen, slots = set(), []
    for obj in meshes:
        for slot in obj.material_slots:
            if slot.material and slot.material.name not in seen:
                seen.add(slot.material.name)
                slots.append({"slot": slot.material.name,
                              "type": "unknown",
                              "default_color": "#888888"})

    # ── PCA (2D, XY plane) — modelin uzun ekseni horizontal eksenden hangisi ──
    # Center
    n = len(coords)
    cx = sum(c[0] for c in coords) / n
    cy = sum(c[1] for c in coords) / n
    # Sample (büyük meshler için speed)
    sample = coords if n < 10000 else coords[::max(1, n // 10000)]
    sxx = syy = sxy = 0.0
    for x, y, _ in sample:
        dx, dy = x - cx, y - cy
        sxx += dx*dx; syy += dy*dy; sxy += dx*dy
    # 2x2 covariance → açı (radyan)
    pca_angle_deg = 0.0
    if abs(sxy) > 1e-6 or abs(sxx - syy) > 1e-6:
        pca_angle_deg = math.degrees(0.5 * math.atan2(2.0*sxy, sxx - syy))
    long_axis_ratio = (max(sxx, syy) / max(min(sxx, syy), 1e-9)) if (sxx > 0 or syy > 0) else 1.0

    result = {
        "width":          round(max(xs) - min(xs), 3),
        "depth":          round(max(ys) - min(ys), 3),
        "height":         round(max(zs) - min(zs), 3),
        "bbox_min":       [round(min(xs), 3), round(min(ys), 3), round(min(zs), 3)],
        "bbox_max":       [round(max(xs), 3), round(max(ys), 3), round(max(zs), 3)],
        "poly_count":     total_faces,
        "material_slots": slots,
        "pca_angle_deg":  round(pca_angle_deg, 2),
        "long_axis_ratio":round(long_axis_ratio, 3),
    }
    print("RESULT:" + json.dumps(result))
""")


# ── Yardımcılar ───────────────────────────────────────────────────────────
def find_blender() -> str | None:
    """blender.exe yolu — PATH veya tipik kurulum dizinleri."""
    if shutil.which("blender"):
        return "blender"
    for ver in ["4.5", "4.3", "4.2", "4.1", "4.0", "3.6"]:
        p = Path(f"C:/Program Files/Blender Foundation/Blender {ver}/blender.exe")
        if p.exists():
            return str(p)
    return None


def measure_blend(blend_path: Path, blender_exe: str | None = None) -> dict:
    """Blender'ı headless açıp bbox + PCA + materials çıkartır."""
    exe = blender_exe or find_blender()
    if not exe:
        return {}
    tmp = blend_path.parent / "_auto_cat_measure.py"
    tmp.write_text(_MEASURE_PY, encoding="utf-8")
    try:
        proc = subprocess.run(
            [exe, "--background", str(blend_path), "--python", str(tmp)],
            capture_output=True, text=True, timeout=120,
        )
        for line in proc.stdout.splitlines():
            if line.startswith("RESULT:"):
                return json.loads(line[7:])
    except Exception as e:
        print(f"  [auto_categorize] Blender ölçümü başarısız: {e}", file=sys.stderr)
    finally:
        tmp.unlink(missing_ok=True)
    return {}


# ── Aşama 1: Regex/keyword tahmini ────────────────────────────────────────
def _normalize(text: str) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    return re.sub(r"[^a-z0-9]+", "_", text.lower())


def _tokens(text: str) -> list[str]:
    return [tok for tok in _normalize(text).split("_") if tok]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = str(value).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _keyword_score(filename: str, material_names: list[str], keyword: str) -> float:
    """Weighted exact-token/phrase matching; avoids over-trusting raw substrings."""
    kw_norm = _normalize(keyword).strip("_")
    if not kw_norm:
        return 0.0

    filename_norm = _normalize(filename).strip("_")
    material_norms = [_normalize(m).strip("_") for m in material_names]
    filename_tokens = set(_tokens(filename))
    material_tokens = set(tok for name in material_names for tok in _tokens(name))
    phrase_pattern = rf"(^|_){re.escape(kw_norm)}(_|$)"

    score = 0.0
    if re.search(phrase_pattern, filename_norm):
        score += 4.0 if "_" in kw_norm else 3.0
    elif "_" not in kw_norm and kw_norm in filename_tokens:
        score += 3.0
    elif len(kw_norm) >= 4 and any(kw_norm in token for token in filename_tokens):
        score += 0.75

    for material_norm in material_norms:
        if re.search(phrase_pattern, material_norm):
            score += 2.0 if "_" in kw_norm else 1.5

    if "_" not in kw_norm and kw_norm in material_tokens:
        score += 1.5
    elif len(kw_norm) >= 4 and any(kw_norm in token for token in material_tokens):
        score += 0.5

    return score


def _score_keyword_map(
    keyword_map: dict[str, list[str]],
    filename: str,
    material_names: list[str],
) -> dict[str, float]:
    return {
        key: sum(_keyword_score(filename, material_names, kw) for kw in keywords)
        for key, keywords in keyword_map.items()
    }


def _confidence_from_scores(best_score: float, second_score: float) -> float:
    if best_score <= 0:
        return 0.2
    strength = min(best_score / 8.0, 1.0)
    margin = (best_score - second_score) / max(best_score, 1e-6)
    return round(min(0.95, 0.45 + 0.35 * strength + 0.15 * max(margin, 0.0)), 2)


def _semantic_vocab_values() -> set[str]:
    return {item for values in SEMANTIC_TAG_VOCABULARY.values() for item in values}


def _all_subcategory_ids() -> set[str]:
    return {sub for subs in SUBCAT_KEYWORDS.values() for sub in subs}


def _style_vocab_values() -> set[str]:
    return {style for values in STYLE_HINTS.values() for style in values}


def _filter_allowed(values: list[str], allowed: set[str]) -> list[str]:
    if not allowed:
        return _unique(values)
    return [value for value in _unique(values) if value in allowed]


def guess_category(filename: str, material_names: list[str]) -> tuple[str, float]:
    """Dosya adı + material isimlerinden kategori. (category, confidence)"""
    scores = _score_keyword_map(CATEGORY_KEYWORDS, filename, material_names)
    best_cat, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score == 0:
        return "seating", 0.2  # düşük güven default
    second_score = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0.0
    # Tek eşleşme = orta güven; çok eşleşme = yüksek güven
    return best_cat, _confidence_from_scores(best_score, second_score)


def guess_subcategory(
    category: str,
    filename: str,
    material_names: list[str] | None = None,
) -> tuple[str, float]:
    material_names = material_names or []
    subs = SUBCAT_KEYWORDS.get(category, {})
    scores = _score_keyword_map(subs, filename, material_names)
    if scores:
        best_sub, best_score = max(scores.items(), key=lambda kv: kv[1])
        if best_score > 0:
            second_score = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0.0
            return best_sub, max(0.55, _confidence_from_scores(best_score, second_score))
    # Fallback: ilk subcategory (düşük güven)
    if subs:
        return next(iter(subs.keys())), 0.3
    return "", 0.0


def guess_style(filename: str, material_names: list[str]) -> tuple[list[str], float]:
    styles: list[str] = []
    for key, val in STYLE_HINTS.items():
        if _keyword_score(filename, material_names, key) > 0:
            for s in val:
                if s not in styles:
                    styles.append(s)
    if styles:
        return styles, 0.8
    return ["modern"], 0.3


def guess_tags(filename: str, material_names: list[str]) -> list[str]:
    """Material adlarından düşük seviye etiket çıkar."""
    tags: list[str] = []
    for kw in TAG_KEYWORDS:
        if _keyword_score(filename, material_names, kw) > 0:
            tags.append(kw)
    return _unique(tags)


# ── Aşama 2: PCA + heuristic forward axis ─────────────────────────────────
def guess_forward_axis(
    category: str,
    subcategory: str,
    dims: dict[str, float],
    pca_angle_deg: float,
    long_axis_ratio: float,
) -> tuple[str, float]:
    """
    Mesh'in uzun ekseni + kategori heuristic'i ile forward axis tahmini.

    Heuristic'ler:
      - Sandalye/koltuk: derinlik genelde sırt-ön mesafesi; uzun eksen = sides → forward = +Y
      - Sofa: uzunluk yan-yan = X; derinlik = ön-arka = Y → forward = +Y
      - Masa/desk: derinlik = oturma tarafı; çoğu desk için forward = +Y
      - Yatak: uzun eksen Y, baş yastığı = +Y kenar → forward = -Y (ayakucu)
      - Mimari (ev): cephe genelde -Y → forward = -Y
    """
    w = dims.get("width", 0)
    d = dims.get("depth", 0)
    h = dims.get("height", 0)

    # Mimari/container — cephe genelde -Y (girişe bakan yön)
    if category == "architecture":
        return "-Y", 0.6

    # Yatak: forward = -Y (ayakucu)
    if subcategory in ("single_bed", "double_bed", "queen_bed", "king_bed", "bunk_bed"):
        return "-Y", 0.7

    # Sofa, dining_table: X uzun → forward = +Y (önyüz Y'ye bakar)
    if subcategory in ("sofa", "dining_table", "coffee_table"):
        if w > d * 1.3:
            return "+Y", 0.8
        elif d > w * 1.3:
            return "+X", 0.7
        return "+Y", 0.5

    # Sandalye/koltuk: standart Y forward
    if subcategory in ("armchair", "office_chair", "dining_chair", "lounge_chair", "bar_stool"):
        return "+Y", 0.65

    # Masa/desk
    if subcategory in ("desk", "side_table", "nightstand", "console_table"):
        return "+Y", 0.6

    # Düşük confidence default
    return "+Y", 0.4


def forward_axis_to_correction_z(forward_axis: str) -> int:
    """forward_axis → facing_correction_z (legacy)"""
    return {"+Y": 0, "-Y": 180, "+X": 270, "-X": 90}.get(forward_axis, 0)


# ── Aşama 3: Subkategori → semantic_tags / room_types / compatible ────────
def derive_semantic_layer(
    category: str,
    subcategory: str,
    style: list[str],
    tags: list[str],
) -> tuple[list[str], list[str], list[str], float]:
    """SUBCAT_TO_ROOMS + SUBCAT_COMPATIBLE'dan derive et."""
    semantic_allowed = _semantic_vocab_values()
    room_allowed = set(SEMANTIC_TAG_VOCABULARY.get("rooms", [])) | set(SEMANTIC_TAG_VOCABULARY.get("audience", []))
    compatible_allowed = _all_subcategory_ids()

    room_types = _filter_allowed(list(SUBCAT_TO_ROOMS.get(subcategory, [])), room_allowed)
    compatible = _filter_allowed(list(SUBCAT_COMPATIBLE.get(subcategory, [])), compatible_allowed)

    # semantic_tags: room_types + style + işlevsel
    sem: list[str] = []
    sem.extend(room_types)
    sem.extend([s for s in style if s in semantic_allowed][:2])
    # İşlev tag'i
    if subcategory in ("desk", "office_chair", "bookshelf"):
        sem.append("work")
    elif subcategory in ("sofa", "armchair", "bed", "double_bed", "queen_bed"):
        sem.append("rest")
    elif subcategory in ("dining_table", "dining_chair"):
        sem.append("dining")
    # tekilleştir
    sem = _filter_allowed(sem, semantic_allowed)

    # confidence: room_types + compatible varsa yüksek
    conf = 0.85 if (room_types and compatible) else (0.6 if room_types else 0.3)
    return sem, room_types, compatible, conf


# ── Aşama 4: Gemini LLM rafine (opsiyonel) ────────────────────────────────
def _llm_refine(result: CategorizationResult, filename: str) -> CategorizationResult:
    """
    Gemini Flash ile düşük güvenli alanları rafine et. GOOGLE_API_KEY yoksa pas geç.

    Sadece şu alanları günceller (kategori vs forward_axis sabit kalır):
      - semantic_tags
      - room_types (var olana ek)
      - compatible_with (var olana ek)
      - style (rafine)
    """
    try:
        import google.generativeai as genai  # type: ignore
    except Exception:
        return result

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return result

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            generation_config={"temperature": 0.0, "response_mime_type": "application/json"},
        )

        prompt = textwrap.dedent(f"""\
            You categorize 3D furniture/architecture assets for an interior design library.

            Asset filename: {filename}
            Current category: {result.category}
            Current subcategory: {result.subcategory}
            Current style: {result.style}
            Current tags: {result.tags}
            Materials: {[m.get("slot") for m in result.material_slots]}
            Dimensions (m): {result.dimensions_m}

            Refine the semantic metadata. Return ONLY a JSON object:
            {{
              "semantic_tags":   ["..."],   // 3-6 theme/intent keywords from this vocabulary:
                                            //   office, home_office, study, living_room, bedroom,
                                            //   dining_room, kitchen, bathroom, lobby, outdoor,
                                            //   work, rest, dining, storage, decoration,
                                            //   minimal, cozy, industrial, classic, modern, luxury, vintage, rustic
              "room_types":      ["..."],   // 1-3 room types this asset belongs in
              "compatible_with": ["..."],   // 2-5 subcategory IDs that pair well (e.g. ["office_chair","table_lamp"])
              "style":           ["..."]    // 1-3 refined style keywords
            }}

            Be specific and consistent. No prose, JSON only.
        """)

        resp = model.generate_content(prompt)
        data = json.loads(resp.text)
        allowed_by_field = {
            "semantic_tags": _semantic_vocab_values(),
            "room_types": set(SEMANTIC_TAG_VOCABULARY.get("rooms", [])) | set(SEMANTIC_TAG_VOCABULARY.get("audience", [])),
            "compatible_with": _all_subcategory_ids(),
            "style": _style_vocab_values(),
        }

        # LLM çıktısı varsa override, kaynak işaretle
        for fld in ("semantic_tags", "room_types", "compatible_with", "style"):
            val = data.get(fld)
            if isinstance(val, list) and val:
                val = _filter_allowed([str(x).strip() for x in val], allowed_by_field.get(fld, set()))
                if not val:
                    continue
                # var olanları LLM çıktısıyla birleştir
                existing = getattr(result, fld)
                merged: list[str] = []
                for x in val + existing:
                    if x and x not in merged:
                        merged.append(x)
                setattr(result, fld, merged)
                result.sources[fld] = "llm"
                result.confidences[fld] = max(result.confidences.get(fld, 0), 0.9)
    except Exception as e:
        print(f"  [auto_categorize] Gemini rafine başarısız (yoksayıldı): {e}", file=sys.stderr)

    return result


# ── Ana orkestratör ───────────────────────────────────────────────────────
def auto_categorize_blend(
    blend_path: Path,
    *,
    use_llm: bool = True,
    confidence_threshold: float = 0.8,
) -> CategorizationResult:
    """
    Bir .blend dosyasını otomatik kategorize et.

    Args:
        blend_path: .blend dosyasının yolu.
        use_llm: GOOGLE_API_KEY varsa Gemini Flash rafinesini çalıştır.
        confidence_threshold: Bunun altında LLM tetiklenir (default 0.8).

    Returns:
        CategorizationResult — tüm alanlar + her alanın confidence/source bilgisi.
    """
    res = CategorizationResult()
    filename = blend_path.stem

    # Aşama 1: Filename regex (material'lar henüz yok)
    cat_guess, cat_conf = guess_category(filename, [])
    res.category = cat_guess
    res.confidences["category"] = cat_conf
    res.sources["category"] = "rule"

    res.is_container = cat_guess in CONTAINER_CATEGORIES
    res.scale_class = "architectural" if res.is_container else "human"

    sub, sub_conf = guess_subcategory(cat_guess, filename)
    res.subcategory = sub
    res.confidences["subcategory"] = sub_conf
    res.sources["subcategory"] = "rule"

    style, st_conf = guess_style(filename, [])
    res.style = style
    res.confidences["style"] = st_conf
    res.sources["style"] = "rule"

    res.tags = guess_tags(filename, [])
    res.sources["tags"] = "rule"

    # Aşama 2: Blender headless ölçüm
    blender_exe = find_blender()
    measure: dict[str, Any] = {}
    if blender_exe:
        measure = measure_blend(blend_path, blender_exe)
    if measure:
        res.dimensions_m = {
            "width":  measure["width"],
            "depth":  measure["depth"],
            "height": measure["height"],
        }
        res.footprint = {
            "width_m":           measure["width"],
            "depth_m":           measure["depth"],
            "height_m":          measure["height"],
            "clearance_front_m": _default_clearance_front(res.subcategory),
            "clearance_sides_m": _default_clearance_sides(res.subcategory),
        }
        res.poly_count = measure.get("poly_count", 0)
        res.material_slots = measure.get("material_slots", [])
        res.sources["dimensions_m"] = "blender"

        # Material isimleri elde — kategori tahminini güçlendir
        mat_names = [m.get("slot", "") for m in res.material_slots]
        cat_guess2, cat_conf2 = guess_category(filename, mat_names)
        if cat_conf2 > cat_conf:
            res.category = cat_guess2
            res.confidences["category"] = cat_conf2
            res.is_container = cat_guess2 in CONTAINER_CATEGORIES
            res.scale_class = "architectural" if res.is_container else "human"
            sub, sub_conf = guess_subcategory(cat_guess2, filename, mat_names)
            res.subcategory = sub
            res.confidences["subcategory"] = sub_conf

        sub2, sub_conf2 = guess_subcategory(res.category, filename, mat_names)
        if sub_conf2 > res.confidences.get("subcategory", 0):
            res.subcategory = sub2
            res.confidences["subcategory"] = sub_conf2

        style2, st_conf2 = guess_style(filename, mat_names)
        if st_conf2 > res.confidences.get("style", 0):
            res.style = style2
            res.confidences["style"] = st_conf2

        res.tags = _unique(res.tags + guess_tags(filename, mat_names))

        # Aşama 3: Forward axis (PCA + heuristic)
        fwd, fwd_conf = guess_forward_axis(
            res.category, res.subcategory, res.dimensions_m,
            measure.get("pca_angle_deg", 0.0),
            measure.get("long_axis_ratio", 1.0),
        )
        res.forward_axis = fwd
        res.facing_correction_z = forward_axis_to_correction_z(fwd)
        res.confidences["forward_axis"] = fwd_conf
        res.sources["forward_axis"] = "pca+heuristic"
    else:
        # Blender yoksa minimal default
        res.confidences["dimensions_m"] = 0.0
        res.confidences["forward_axis"] = 0.2

    # Aşama: Semantic layer (subcategory → room_types/compatible/semantic_tags)
    sem, rooms, compat, sem_conf = derive_semantic_layer(
        res.category, res.subcategory, res.style, res.tags
    )
    res.semantic_tags = sem
    res.room_types = rooms
    res.compatible_with = compat
    res.confidences["semantic_tags"] = sem_conf
    res.confidences["room_types"] = sem_conf
    res.confidences["compatible_with"] = sem_conf
    for k in ("semantic_tags", "room_types", "compatible_with"):
        res.sources[k] = "rule"

    # Aşama 4: LLM rafine (toplam confidence düşükse veya zorla)
    if use_llm and res.overall_confidence() < confidence_threshold:
        res = _llm_refine(res, blend_path.name)

    return res


def _default_clearance_front(subcategory: str) -> float:
    """Subkategoriye göre önündeki gereken boşluk (m)."""
    return {
        "desk":          0.8,   # sandalye ve bacak
        "dining_table":  0.7,
        "sofa":          0.6,
        "coffee_table":  0.4,
        "bed":           0.6,
        "double_bed":    0.6,
        "queen_bed":     0.6,
        "wardrobe":      0.8,
        "armchair":      0.4,
        "office_chair":  0.3,
        "kitchen_counter": 1.0,
    }.get(subcategory, 0.3)


def _default_clearance_sides(subcategory: str) -> float:
    return {
        "sofa":          0.15,
        "desk":          0.10,
        "bed":           0.10,
        "double_bed":    0.10,
        "queen_bed":     0.10,
        "wardrobe":      0.05,
    }.get(subcategory, 0.10)


# ── Catalog girişi inşa ───────────────────────────────────────────────────
def build_catalog_entry(
    result: CategorizationResult,
    *,
    asset_id: str,
    name: str,
    file_rel: str,
    texture_resolution: str = "unknown",
    textures: dict[str, str] | None = None,
    rooms: list[dict] | None = None,
    container_meta: dict | None = None,
    source: str = "",
) -> dict[str, Any]:
    """CategorizationResult'ı Catalog.json formatına çevir."""
    entry: dict[str, Any] = {
        "id":          asset_id,
        "name":        name,
        "category":    result.category,
        "subcategory": result.subcategory,
        "style":       result.style,
        "tags":        result.tags,

        "semantic_tags":   result.semantic_tags,
        "room_types":      result.room_types,
        "is_container":    result.is_container,
        "scale_class":     result.scale_class,
        "compatible_with": result.compatible_with,

        "footprint": result.footprint,
        "placement": {
            "rules": _default_placement_rules(result.subcategory, result.is_container),
            "anchor": "floor_center",
            "forward_axis": result.forward_axis,
            "facing_correction_z": result.facing_correction_z,
            "confidence": round(result.confidences.get("forward_axis", 0.0), 2),
        },

        "file": file_rel,
        "texture_resolution": texture_resolution,
        "material_slots": result.material_slots,
        "textures": textures or {},

        "dimensions_m": result.dimensions_m,
        "origin": "floor_center",
        "facing_correction_z": result.facing_correction_z,
        "poly_count": result.poly_count,

        "added_at": str(date.today()),
        "source": source,
    }

    # ── Auto import_scale: furniture saved in cm/mm instead of m ───────────
    # If the largest dimension is suspiciously large for a non-container object
    # (> 5m), the blend was probably exported in cm (100x) or mm (1000x).
    # Store a corrective scale so import_assets_to_blender applies it.
    if not result.is_container:
        d = result.dimensions_m
        max_dim = max(d.get("width", 0), d.get("depth", 0), d.get("height", 0))
        if max_dim > 5.0:
            # Heuristic: find the power-of-10 that brings max_dim into [0.1, 5] range
            import math as _math
            exp = _math.floor(_math.log10(max_dim))     # e.g. log10(98) ≈ 1.99 → 1
            correction = 10 ** (-exp)                   # 10^-1 = 0.1 for exp=1, 10^-2=0.01 for exp=2
            # Fine-tune: find which power brings max_dim closest to <= 3m
            for exp_try in (exp, exp + 1):
                c = 10 ** (-exp_try)
                if max_dim * c <= 3.0:
                    correction = c
                    break
            entry["import_scale"] = correction
            # Also fix the stored dimensions
            entry["dimensions_m"] = {k: round(v * correction, 4) for k, v in d.items()}
            entry["footprint"]["width_m"]  = round(entry["footprint"].get("width_m",  0) * correction, 4)
            entry["footprint"]["depth_m"]  = round(entry["footprint"].get("depth_m",  0) * correction, 4)
            entry["footprint"]["height_m"] = round(entry["footprint"].get("height_m", 0) * correction, 4)

    if result.is_container:
        entry["container_meta"] = container_meta or _default_container_meta(result.dimensions_m)
        if rooms:
            entry["rooms"] = rooms

    return entry


def _default_placement_rules(subcategory: str, is_container: bool) -> list[str]:
    if is_container:
        return ["world_origin", "ground"]
    table_like = subcategory in ("desk", "dining_table", "coffee_table", "side_table",
                                  "nightstand", "console_table", "kitchen_counter")
    bed_like = subcategory in ("single_bed", "double_bed", "queen_bed", "king_bed", "bunk_bed")
    if bed_like:
        return ["floor", "wall_only", "corner_ok"]
    if subcategory in ("sofa",):
        return ["floor", "wall_optional", "center_ok"]
    if subcategory in ("armchair", "office_chair", "dining_chair", "lounge_chair"):
        return ["floor", "freestanding", "center_ok"]
    if table_like:
        return ["floor", "wall_optional", "center_ok"]
    if subcategory in ("wardrobe", "bookshelf", "cabinet", "dresser", "tv_stand"):
        return ["floor", "wall_only"]
    return ["floor", "center_ok"]


def _default_container_meta(dims: dict[str, float]) -> dict[str, Any]:
    """interior_bbox_local default: dış bbox'tan %15 içe çekilmiş."""
    w = dims.get("width", 10.0)
    d = dims.get("depth", 10.0)
    h = dims.get("height", 3.0)
    inset_xy = 0.3
    inset_h_top = 1.0
    return {
        "floor_z_world": 0.0,
        "interior_bbox_local": {
            "min": [round(-w/2 + inset_xy, 3), round(-d/2 + inset_xy, 3), 0.0],
            "max": [round( w/2 - inset_xy, 3), round( d/2 - inset_xy, 3), round(h - inset_h_top, 3)]
        },
        "entrance_local": [0.0, round(-d/2 + inset_xy, 3), 0.0],
    }


# ── CLI testi ─────────────────────────────────────────────────────────────
def _cli() -> None:
    if len(sys.argv) < 2:
        print("Usage: python auto_categorize.py <path/to/model.blend>")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Not found: {path}")
        sys.exit(2)
    use_llm = "--no-llm" not in sys.argv
    res = auto_categorize_blend(path, use_llm=use_llm)
    print(json.dumps(asdict(res), indent=2, ensure_ascii=False))
    print(f"\n  Overall confidence: {res.overall_confidence():.2f}")


if __name__ == "__main__":
    _cli()
