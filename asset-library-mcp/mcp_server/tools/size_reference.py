"""Real-world furniture size reference + normalization helpers.

Single source of truth for "how big should a <subcategory> be" in meters.
Used to keep furniture dimensionally consistent with each other and the room
during layout (Tasarla / coach preview) and model generation.

Key axis = HEIGHT: it's the most standardized real-world dimension
(seat height ~0.45m, desk surface ~0.75m), so scaling uniformly to match
the reference height keeps the model's own proportions while making the
overall size realistic and consistent across all assets.
"""
from typing import Dict, Optional, Tuple

# Typical real-world dimensions (meters): width (X), depth (Y), height (Z)
FURNITURE_SIZE_REF: Dict[str, Dict[str, float]] = {
    "sofa":          {"w": 1.9, "d": 0.9,  "h": 0.8},
    "armchair":      {"w": 0.8, "d": 0.8,  "h": 0.9},
    "lounge_chair":  {"w": 0.8, "d": 0.85, "h": 0.85},
    "office_chair":  {"w": 0.6, "d": 0.6,  "h": 1.1},
    "dining_chair":  {"w": 0.5, "d": 0.55, "h": 0.9},
    "chair":         {"w": 0.55,"d": 0.55, "h": 0.9},
    "bar_stool":     {"w": 0.4, "d": 0.4,  "h": 0.75},
    "stool":         {"w": 0.4, "d": 0.4,  "h": 0.45},
    "bench":         {"w": 1.2, "d": 0.4,  "h": 0.45},
    "pouf":          {"w": 0.5, "d": 0.5,  "h": 0.4},
    "desk":          {"w": 1.4, "d": 0.7,  "h": 0.75},
    "dining_table":  {"w": 1.6, "d": 0.9,  "h": 0.75},
    "coffee_table":  {"w": 1.1, "d": 0.6,  "h": 0.42},
    "side_table":    {"w": 0.5, "d": 0.5,  "h": 0.55},
    "nightstand":    {"w": 0.5, "d": 0.4,  "h": 0.55},
    "console_table": {"w": 1.1, "d": 0.35, "h": 0.8},
    "table":         {"w": 1.2, "d": 0.7,  "h": 0.75},
    "wardrobe":      {"w": 1.2, "d": 0.6,  "h": 2.0},
    "cabinet":       {"w": 1.0, "d": 0.45, "h": 0.9},
    "bookshelf":     {"w": 0.9, "d": 0.35, "h": 1.8},
    "tv_stand":      {"w": 1.6, "d": 0.4,  "h": 0.5},
    "dresser":       {"w": 1.1, "d": 0.5,  "h": 0.8},
    "shelf":         {"w": 0.9, "d": 0.35, "h": 1.8},
    "single_bed":    {"w": 1.0, "d": 2.0,  "h": 0.5},
    "double_bed":    {"w": 1.5, "d": 2.0,  "h": 0.5},
    "queen_bed":     {"w": 1.6, "d": 2.1,  "h": 0.5},
    "king_bed":      {"w": 1.9, "d": 2.1,  "h": 0.5},
    "bed":           {"w": 1.5, "d": 2.0,  "h": 0.5},
    "floor_lamp":    {"w": 0.4, "d": 0.4,  "h": 1.6},
    "table_lamp":    {"w": 0.3, "d": 0.3,  "h": 0.5},
    "chandelier":    {"w": 0.6, "d": 0.6,  "h": 0.5},
    "refrigerator":  {"w": 0.7, "d": 0.7,  "h": 1.8},
    "rug":           {"w": 2.0, "d": 1.4,  "h": 0.02},
    "plant":         {"w": 0.5, "d": 0.5,  "h": 1.2},
    "_default":      {"w": 0.6, "d": 0.6,  "h": 0.8},
}

# Keyword → subcategory, for guessing a type from a free-text prompt (TR + EN)
_SUBCAT_KEYWORDS = {
    "office_chair":  ["office chair", "ofis sandaly", "çalışma sandaly", "calisma sandaly"],
    "dining_chair":  ["dining chair", "yemek sandaly"],
    "lounge_chair":  ["lounge", "berjer", "dinlenme koltu"],
    "armchair":      ["armchair", "koltuk", "tekli koltuk"],
    "chair":         ["chair", "sandalye", "sandaly"],
    "bar_stool":     ["bar stool", "bar tabure", "tabure"],
    "sofa":          ["sofa", "kanepe", "divan", "couch"],
    "coffee_table":  ["coffee table", "sehpa", "orta masa"],
    "dining_table":  ["dining table", "yemek masa"],
    "side_table":    ["side table", "yan masa", "yan sehpa"],
    "console_table": ["console", "konsol"],
    "nightstand":    ["nightstand", "komodin", "başucu"],
    "desk":          ["desk", "çalışma masa", "ofis masa", "masa"],
    "wardrobe":      ["wardrobe", "gardırop", "dolap"],
    "bookshelf":     ["bookshelf", "kitaplik", "raf", "shelf"],
    "tv_stand":      ["tv stand", "tv ünite", "televizyon"],
    "dresser":       ["dresser", "şifonyer"],
    "cabinet":       ["cabinet", "kabin", "vitrin"],
    "double_bed":    ["double bed", "çift kişilik yatak", "queen", "king"],
    "single_bed":    ["single bed", "tek kişilik yatak"],
    "bed":           ["bed", "yatak"],
    "floor_lamp":    ["floor lamp", "lambader", "ayaklı lamba"],
    "table_lamp":    ["table lamp", "masa lamba", "abajur"],
    "chandelier":    ["chandelier", "avize"],
    "refrigerator":  ["refrigerator", "fridge", "buzdolab"],
    "bench":         ["bench", "bank"],
    "pouf":          ["pouf", "puf"],
    "rug":           ["rug", "carpet", "halı", "kilim"],
    "plant":         ["plant", "bitki", "saksı"],
}


def _ascii_tr(s: str) -> str:
    """Lowercase + fold Turkish characters to ASCII so 'kitaplık'=='kitaplik'."""
    s = (s or "").lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ç", "c"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("â", "a")):
        s = s.replace(a, b)
    return s


def guess_subcategory(text: str) -> str:
    """Best-effort subcategory from a free-text prompt. Falls back to 'furniture'.

    Turkish-character insensitive (kitaplık == kitaplik).
    """
    t = _ascii_tr(text)
    for sub, kws in _SUBCAT_KEYWORDS.items():
        if any(_ascii_tr(kw) in t for kw in kws):
            return sub
    return "furniture"


def expected_dims(subcategory: str) -> Dict[str, float]:
    """Return reference {w, d, h} for a subcategory (or _default)."""
    return FURNITURE_SIZE_REF.get((subcategory or "").lower(), FURNITURE_SIZE_REF["_default"])


def _as_whd(dims: Dict) -> Optional[Tuple[float, float, float]]:
    """Accept {width,depth,height} or {w,d,h}; return (w,d,h) or None."""
    if not dims:
        return None
    w = dims.get("width",  dims.get("w"))
    d = dims.get("depth",  dims.get("d"))
    h = dims.get("height", dims.get("h"))
    try:
        w, d, h = float(w), float(d), float(h)
    except (TypeError, ValueError):
        return None
    if w <= 0 or d <= 0 or h <= 0:
        return None
    return w, d, h


def normalize_dims(actual: Dict, subcategory: str,
                   tolerance: float = 0.15) -> Tuple[Dict[str, float], float]:
    """Scale a model's dimensions uniformly so its HEIGHT matches the reference.

    Returns (normalized_dims, scale_ratio). If the actual height is already
    within ±tolerance of the reference, returns the input unchanged with ratio 1.0.
    Uniform scaling preserves the model's own proportions.
    """
    whd = _as_whd(actual)
    ref = expected_dims(subcategory)
    if whd is None:
        # No reliable measurement — fall back to reference dims directly
        return ({"width": ref["w"], "depth": ref["d"], "height": ref["h"]}, 1.0)

    w, d, h = whd
    ratio = ref["h"] / h
    if (1.0 - tolerance) < ratio < (1.0 + tolerance):
        return ({"width": round(w, 4), "depth": round(d, 4), "height": round(h, 4)}, 1.0)

    return (
        {"width": round(w * ratio, 4), "depth": round(d * ratio, 4), "height": round(h * ratio, 4)},
        round(ratio, 6),
    )


def cap_to_room(dims: Dict, room_w: float, room_d: float,
                max_fraction: float = 0.9) -> Tuple[Dict[str, float], float]:
    """Shrink dims uniformly if the footprint exceeds max_fraction of the room.

    Considers walls/space: e.g. a 2.5m-wide sofa in a 2m room gets scaled down.
    Returns (capped_dims, extra_ratio). extra_ratio is 1.0 if no capping needed.
    """
    whd = _as_whd(dims)
    if whd is None or room_w <= 0 or room_d <= 0:
        return (dims, 1.0)
    w, d, h = whd
    limit_w = room_w * max_fraction
    limit_d = room_d * max_fraction
    ratio = 1.0
    if w > limit_w:
        ratio = min(ratio, limit_w / w)
    if d > limit_d:
        ratio = min(ratio, limit_d / d)
    if ratio >= 0.999:
        return ({"width": w, "depth": d, "height": h}, 1.0)
    return (
        {"width": round(w * ratio, 4), "depth": round(d * ratio, 4), "height": round(h * ratio, 4)},
        round(ratio, 6),
    )
