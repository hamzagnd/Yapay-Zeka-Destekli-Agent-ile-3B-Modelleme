"""Prompt Coach Agent — turns a rough user request into a clean prompt.

The user can type Turkish/English freely ("5x4 ofis kur desk'in bir chair'ı
olsun ve bunların sağındada bir sofa olsun"). The coach:
  - reads the catalog to know what's actually available
  - converts directional words (sağ/sol/karşı/önünde) into placement strings
    the layout engine understands
  - fills in sensible defaults for missing pieces (size 5x4x2.7, style modern)
  - returns a refined natural-language prompt the design team can act on cleanly

It does NOT design anything itself — it only rewrites the prompt.
"""
from agno.agent import Agent

from ._prompt_loader import _load_agent_instructions
from .tools.catalog_tools import (
    list_all_categories,
    get_room_preset,
    search_catalog,
    list_house_assets,
    list_house_rooms,
)


def create_prompt_coach(model) -> Agent:
    return Agent(
        name="Interior Architect Coach",
        role="Design a coherent interior layout like a professional architect, then output a structured prompt",
        model=model,
        tools=[list_all_categories, get_room_preset, search_catalog,
               list_house_assets, list_house_rooms],
        instructions=_load_agent_instructions("coach", [
            "You are a professional interior architect AND a prompt engineer.",
            "When the user gives a rough room request, you DESIGN the space thoughtfully",
            "like an experienced designer, then encode that design as a structured prompt",
            "the deterministic execution engine can run. Think first, then write output.",
            "",
            "╔══════════════════════════════════════════════════════════════╗",
            "║  PHASE 1 — INTERIOR DESIGN THINKING  (shapes your output)   ║",
            "╚══════════════════════════════════════════════════════════════╝",
            "",
            "Before writing a single line of JSON, reason through the space:",
            "",
            "A. UNDERSTAND THE ROOM",
            "   - What is the primary activity? (focus work / socialise / sleep / dine)",
            "   - What is the room's FOCAL POINT? (window view, TV wall, fireplace,",
            "     or — when none — the north wall is the natural visual anchor)",
            "   - Assume the entrance door is on the SOUTH wall unless told otherwise.",
            "   - Workflow B only: call list_house_assets() + list_house_rooms() to read",
            "     real dimensions, then use those instead of defaults.",
            "",
            "B. PLACE THE ANCHOR PIECE FIRST",
            "   The anchor is the largest/most-used item; everything else references it.",
            "   Default anchors per room type:",
            "   ┌─────────────────┬──────────────────────────────────────────────────┐",
            "   │ office          │ desk → north_wall, facing wall (rot 180°)        │",
            "   │ living_room     │ sofa → south_wall, facing room_center / TV       │",
            "   │ bedroom         │ bed  → north_wall, headboard to wall             │",
            "   │ dining_room     │ dining_table → center, chairs on all 4 sides     │",
            "   └─────────────────┴──────────────────────────────────────────────────┘",
            "   Override anchor wall only if user specifies or style calls for it.",
            "",
            "C. BUILD ACTIVITY ZONES",
            "   Group items by function. Each zone has an anchor + supporting items:",
            "   • WORK ZONE:    desk (north_wall) + chair (in_front_of:desk, face:desk)",
            "                   + optional lamp at corner_nw or corner_ne",
            "   • SEATING ZONE: sofa (south_wall) + coffee_table (in_front_of:sofa)",
            "                   + optional armchair (beside:sofa:right, face:room_center)",
            "   • SLEEP ZONE:   bed (north_wall) + nightstand (beside:bed:right)",
            "                   + wardrobe (east_wall or west_wall)",
            "   • DINING ZONE:  dining_table (center) + chairs (table_side:n/s/e/w)",
            "",
            "D. DESK ↔ CHAIR MUST ALWAYS FACE EACH OTHER (non-negotiable rule)",
            "   When a desk and a chair appear together:",
            "   • desk  → placement: north_wall (or any wall), face: room_center",
            "   • chair → placement: in_front_of:desk, face: desk",
            "   The chair sits DIRECTLY IN FRONT of the desk, facing the desk.",
            "   NEVER place the chair beside:desk or at a different wall.",
            "   This creates the ergonomic work triangle (desk faces wall,",
            "   chair faces desk, both look at each other).",
            "",
            "   Same rule for dining tables:",
            "   • dining_table → center",
            "   • chairs       → table_side:n / table_side:s / table_side:e / table_side:w",
            "     all with face: dining_table",
            "",
            "E. ALL SEATING MUST FACE SOMETHING MEANINGFUL",
            "   RULE: No sofa, armchair, or standalone chair may face a blank wall.",
            "   Priority order for 'face' targets:",
            "     1. its direct reference (desk, dining_table, coffee_table)",
            "     2. room_center  (creates a conversation focus)",
            "   If the only placement available would face a wall, use room_center instead.",
            "",
            "F. TRAFFIC & CLEARANCES",
            "   - Keep a clear 90 cm path from the south wall (entrance) to the north",
            "     wall. Do not block this corridor with furniture.",
            "   - Sofa ↔ coffee_table: minimum 45 cm in front.",
            "   - Chair ↔ desk: chair sits in_front_of:desk — 60-80 cm clearance.",
            "   - Don't cluster everything on one wall; distribute weight across the room.",
            "",
            "G. COMPLETENESS (based on catalog only)",
            "   ⚠ STRICT MODE — triggered by ANY of these phrases in the prompt:",
            "     'fazladan hiçbir şey ekleme', 'sadece belirttiğim', 'başka model ekleme',",
            "     'dışına çıkma', 'sadece bu modeller', 'sadece verdiğim', 'model detayları'",
            "   When STRICT MODE is active:",
            "     - Use ONLY the exact items the user listed (asset IDs or names).",
            "     - DO NOT add preset slots, companions, floor lamps, rugs, plants,",
            "       nightstands, or any other 'completing' items.",
            "     - DO NOT call get_room_preset() to add standard slots.",
            "     - specs = exclusively what the user wrote, nothing more.",
            "   ALSO: if the prompt contains a 'Model detayları:' JSON block, those",
            "   asset IDs are ALREADY pinned in the yapboz — treat them as fixed and",
            "   focus only on placement quality, not on finding substitutes.",
            "",
            "   Otherwise (NORMAL mode): call get_room_preset(room_type) to see standard",
            "   slots. Then call search_catalog for each to verify catalog availability.",
            "   ADD only items that:",
            "     a) exist in the catalog (search_catalog returns ≥1 result), AND",
            "     b) the user did NOT exclude (e.g. 'X yok', 'no X', 'X istemiyorum')",
            "   Do NOT invent items the catalog doesn't have.",
            "   Do NOT add what the user excluded — even if it looks incomplete.",
            "",
            "╔══════════════════════════════════════════════════════════════╗",
            "║  PHASE 2 — CATALOG GROUNDING  (strict)                      ║",
            "╚══════════════════════════════════════════════════════════════╝",
            "",
            "For EVERY item you plan to include, call:",
            "  search_catalog(subcategory=<sub>, room_type=<room>)",
            "  - Has ≥1 result → include it",
            "  - No result     → REMOVE it + add to warnings (do NOT substitute silently)",
            "  - Near-miss (different subcat but compatible room_type) → warn, let user decide",
            "",
            "╔══════════════════════════════════════════════════════════════╗",
            "║  PHASE 3 — WORKFLOW DETECTION                               ║",
            "╚══════════════════════════════════════════════════════════════╝",
            "",
            "Workflow A (from-scratch room): user says room dimensions or 'kur', 'oluştur'",
            "Workflow B (house container): keywords: 'ev', 'evin içi', 'iki katlı', 'house',",
            "  specific house IDs. → list_house_assets() + list_house_rooms(house_id)",
            "",
            "╔══════════════════════════════════════════════════════════════╗",
            "║  PHASE 4 — OUTPUT  (strict JSON, no markdown, no prose)     ║",
            "╚══════════════════════════════════════════════════════════════╝",
            "",
            "Respond with ONE JSON object. Nothing before or after it.",
            "{",
            '  "refined_prompt": "<A coherent Turkish paragraph explaining the design,',
            '                      followed by the mandatory Slot listesi block>",',
            '  "rationale":      "<2-4 sentences written AS A DESIGNER explaining WHY',
            '                      you placed things where you did: focal point chosen,',
            '                      traffic path preserved, zone groupings, etc.>",',
            '  "warnings":       ["❌ ... katalogda yok. Eklemek için: python add_asset.py ..."],',
            '  "room": {',
            '    "width": <m>, "depth": <m>, "height": <m>,',
            '    "type":  "<office|living_room|bedroom|dining_room|kitchen|bathroom>",',
            '    "style": "<modern|industrial|classic|mid-century|minimalist|...>"',
            "  },",
            '  "specs": [',
            '    {"slot":"<name>","subcategory":"<sub>","placement":"<keyword>","face":"<target>"},',
            "    ...",
            "  ],",
            '  "house": null',
            "}",
            "",
            "RATIONALE must be design-speak, not bookkeeping. BAD: 'Added default 5x4m.'",
            "GOOD: 'Masayı kuzey duvara yerleştirdim — kapıdan giren kişi masayı doğrudan",
            "görmez, bu da çalışma konforunu artırır. Koltuk masanın önünde, oda merkezine",
            "bakıyor; akışı engellemiyor.'",
            "",
            "PLACEMENT KEYWORDS (use EXACTLY):",
            "  north_wall | south_wall | east_wall | west_wall | center",
            "  corner_nw | corner_ne | corner_sw | corner_se",
            "  in_front_of:<slot>     — chair/sofa directly in front of a desk/table",
            "  beside:<slot>:left     — to the WEST of <slot>",
            "  beside:<slot>:right    — to the EAST of <slot>",
            "  table_side:n|s|e|w     — dining chair on that side of the dining_table",
            "",
            "FACE VALUES (allowed): room_center | <slot_name> | default",
            "",
            "TURKISH → PLACEMENT translation (apply rigorously):",
            "  'önünde / karşısında'        → in_front_of:<ref>   face:<ref>",
            "  'sağında / doğusunda'        → beside:<ref>:right",
            "  'solunda / batısında'        → beside:<ref>:left",
            "  'kuzey/güney/doğu/batı duvarı' → north/south/east/west_wall",
            "  'köşe (kuzey-doğu)'          → corner_ne  (and other 3 corners)",
            "  'ortada / merkezde'          → center",
            "",
            "SLOT LIST — append at end of refined_prompt (machine-readable, verbatim):",
            "  Slot listesi:",
            "  - slot: <name>, subcategory: <sub>, placement: <kw>, face: <target>",
            "",
            "EXAMPLE refined_prompt (office):",
            "  5m × 4m × 2.7m industrial tarzda bir çalışma odası. Masa kuzey duvarına",
            "  yerleştirildi; kapıdan girerken göz önünde olmayacak şekilde. Sandalye",
            "  masanın önünde, masaya bakıyor — ergonomik çalışma üçgeni oluşturuyor.",
            "  Zemin lambası kuzey-batı köşesinde, odaya sıcaklık katıyor.",
            "  Slot listesi:",
            "  - slot: desk,  subcategory: desk,     placement: north_wall,       face: room_center",
            "  - slot: chair, subcategory: armchair, placement: in_front_of:desk, face: desk",
            "  - slot: lamp,  subcategory: floor_lamp, placement: corner_nw,      face: default",
            "",
            "IMPORTANT CONSTRAINTS:",
            "  - refined_prompt + specs must match exactly (same slots, same placements)",
            "  - Only mention catalog-verified items in refined_prompt",
            "  - Missing items → warnings array, never into refined_prompt",
            "  - Preserve Workflow B house/room context if mentioned",
            "  - Do NOT call Blender tools",
        ]),
    )


# Turkish / English furniture words → catalog subcategory. Used to recover items
# the user explicitly asked for in their raw prompt but Coach forgot or claimed
# (incorrectly) didn't exist in the catalog.
_ASSET_KEYWORDS = {
    # Seating
    "sofa": "sofa", "kanepe": "sofa", "couch": "sofa",
    "koltuk": "armchair", "armchair": "armchair", "berjer": "armchair",
    "sandalye": "armchair", "chair": "armchair",
    "office chair": "office_chair", "ofis sandalyesi": "office_chair",
    "dining chair": "dining_chair", "yemek sandalyesi": "dining_chair",
    "bar tabure": "bar_stool", "tabure": "bar_stool", "stool": "bar_stool",
    "puf": "pouf", "pouf": "pouf",
    "bank": "bench", "bench": "bench",
    # Tables
    "masa": "desk", "çalışma masası": "desk", "desk": "desk",
    "yemek masası": "dining_table", "dining table": "dining_table",
    "sehpa": "coffee_table", "coffee table": "coffee_table",
    "yan sehpa": "side_table", "side table": "side_table",
    "konsol": "console_table", "console": "console_table",
    "komodin": "nightstand", "nightstand": "nightstand",
    # Storage
    "dolap": "wardrobe", "gardırop": "wardrobe", "wardrobe": "wardrobe",
    "kitaplık": "bookshelf", "kitaplik": "bookshelf", "bookshelf": "bookshelf",
    "tv ünitesi": "tv_stand", "tv stand": "tv_stand",
    "şifonyer": "dresser", "dresser": "dresser",
    # Beds
    "yatak": "double_bed", "bed": "double_bed",
    "tek kişilik yatak": "single_bed",
    # Lighting
    "yer lambası": "floor_lamp", "zemin lambası": "floor_lamp", "floor lamp": "floor_lamp",
    "masa lambası": "table_lamp", "table lamp": "table_lamp",
    "avize": "chandelier", "chandelier": "chandelier",
    # Decor
    "halı": "rug", "hali": "rug", "rug": "rug",
    "bitki": "plant", "saksı": "plant", "plant": "plant",
    "ayna": "mirror", "mirror": "mirror",
    "tablo": "artwork", "artwork": "artwork",
}


def _default_placement_for(subcategory: str):
    """Return a sensible (placement, face) for a subcategory by borrowing
    whatever existing ROOM_PRESET uses it. Falls back to wall/center heuristics."""
    from mcp_server.tools.interior_design_tools import ROOM_PRESETS
    for preset in ROOM_PRESETS.values():
        for slot in preset:
            if slot.get("subcategory") == subcategory:
                return slot.get("placement", "center"), slot.get("face", "default")
    # Heuristic fallback by category
    if subcategory in ("sofa", "bed", "double_bed", "wardrobe", "bookshelf",
                       "tv_stand", "dresser", "kitchen_counter", "bathtub"):
        return "east_wall", "room_center"
    if subcategory in ("floor_lamp", "plant"):
        return "corner_nw", "default"
    return "center", "default"


# Negation words that indicate the user does NOT want something.
# Checked in a ~40-char window around the furniture keyword match.
_NEGATION_WORDS = [
    "yok", "istemiyorum", "olmasın", "olmasin", "koyma", "ekleme",
    "istemem", "gerekmiyor", "no ", "without", "don't", "dont", "olmadan",
]


def _detect_excluded_subcats(user_prompt: str) -> set:
    """Return subcategories the user explicitly excluded.
    Detects patterns like 'masa yok', 'ahşap masa istemiyorum', 'no desk'."""
    if not user_prompt:
        return set()
    text = user_prompt.lower()
    excluded = set()
    for word in sorted(_ASSET_KEYWORDS, key=len, reverse=True):
        idx = text.find(word)
        if idx < 0:
            continue
        # Check a 40-char window around the keyword for negation words
        window_start = max(0, idx - 40)
        window_end = min(len(text), idx + len(word) + 40)
        window = text[window_start:window_end]
        if any(neg in window for neg in _NEGATION_WORDS):
            excluded.add(_ASSET_KEYWORDS[word])
    return excluded


def _detect_user_intent_subcats(user_prompt: str):
    """Scan the user's raw prompt for furniture mentions; return ordered, unique
    list of catalog subcategories POSITIVELY implied by the text (negated ones
    are excluded). Case-insensitive, matches longest keywords first."""
    if not user_prompt:
        return []
    excluded = _detect_excluded_subcats(user_prompt)
    text = user_prompt.lower()
    # Longest keywords first so multi-word phrases win over single-word ones
    seen = []
    for word in sorted(_ASSET_KEYWORDS, key=len, reverse=True):
        if word in text:
            sub = _ASSET_KEYWORDS[word]
            if sub not in excluded and sub not in seen:
                seen.append(sub)
            # blank out the match so a shorter overlapping keyword doesn't refire
            text = text.replace(word, " " * len(word))
    return seen


def _validate_and_complete_specs(parsed: dict, user_prompt: str = "") -> dict:
    """Belt-and-suspenders post-process: drop specs the catalog can't fulfill,
    inject required preset slots, and recover items the user asked for but
    Coach skipped or mis-reported as missing.

    The Coach LLM is asked to do all of this in its instructions but doesn't
    always comply (it may invent missing assets, skip required slots, or claim
    a catalog item doesn't exist when it does). This pass enforces the policy
    in code so the deterministic executor never gets a broken plan."""
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).parent.parent))
    from mcp_server import catalog as _catalog
    from mcp_server.tools.interior_design_tools import ROOM_PRESETS, find_asset_for_slot

    room = parsed.get("room") or {}
    room_type = (room.get("type") or "").lower().replace(" ", "_")
    style = room.get("style") or None
    specs = parsed.get("specs") or []
    warnings = list(parsed.get("warnings") or [])

    # Detect subcategories the user explicitly negated (e.g. "masa yok", "no desk")
    excluded_subcats = _detect_excluded_subcats(user_prompt)

    # 1) Drop specs whose subcategory the user negated OR has no catalog match.
    #    Specs with explicit asset_id (user picked from yapboz) are kept unconditionally.
    kept_specs = []
    for spec in specs:
        # If the spec already carries an explicit asset_id (user-added from catalog picker),
        # trust it — skip subcategory validation entirely.
        if spec.get("asset_id"):
            kept_specs.append(spec)
            continue
        sub = spec.get("subcategory", "")
        if not sub:
            continue
        if sub in excluded_subcats:
            # User explicitly said they don't want this — silently skip it
            continue
        asset = find_asset_for_slot({"subcategory": sub, "fallback": []}, style, room_type)
        if asset:
            kept_specs.append(spec)
        else:
            warn = (
                f"❌ {spec.get('slot', sub)}: katalogda \"{sub}\" subcategory'sinde "
                f"asset yok, listeden çıkarıldı. Eklemek için: "
                f"python add_asset.py {sub}.zip"
            )
            if warn not in warnings:
                warnings.append(warn)

    # Helper: drop any Coach warning that incorrectly claimed `sub` was missing
    # from the catalog. Triggered when post-process actually finds and injects
    # an asset for `sub` — keeping the wrong warning would confuse the user.
    # Matches by subcategory name + the Turkish keywords that route to it.
    def _strip_false_missing_warning(sub):
        sub_lower = sub.lower()
        # Words from _ASSET_KEYWORDS that map to this subcategory
        tr_words = [w for w, s in _ASSET_KEYWORDS.items() if s == sub]
        filtered = []
        for w in warnings:
            w_lower = w.lower()
            # Only consider Coach's "katalogda ... yok" style warnings
            looks_like_missing = ("katalog" in w_lower and "yok" in w_lower) or w_lower.startswith("❌")
            mentions_this_sub = (
                sub_lower in w_lower
                or any(tw.lower() in w_lower for tw in tr_words)
            )
            if looks_like_missing and mentions_this_sub:
                continue  # drop it
            filtered.append(w)
        warnings[:] = filtered

    # Step 2 (preset injection) intentionally removed: kullanıcı ne isterse
    # sadece onu ekle, otomatik preset slot ekleme yapma.
    existing_subcats = {s.get("subcategory") for s in kept_specs}

    # 3a) Recover explicitly-specified asset IDs ("şu modelleri kullan: id1, id2").
    #     These come from the Models tab picker and must be preserved verbatim —
    #     Coach must not rename or drop them.
    #     New format also embeds a JSON block ("Model detayları: [...]") with full
    #     metadata; we parse qty from there if available.
    import re as _re2, json as _json2
    _id_match = _re2.search(r'şu modelleri kullan:\s*([^\n]+)', user_prompt, _re2.IGNORECASE)
    # Parse qty map from the JSON detail block if present
    _qty_map: dict = {}
    _json_block_match = _re2.search(r'Model detayları:\s*(\[[\s\S]*?\])', user_prompt)
    if _json_block_match:
        try:
            for _entry in _json2.loads(_json_block_match.group(1)):
                if isinstance(_entry, dict) and _entry.get('id'):
                    _qty_map[_entry['id']] = int(_entry.get('qty', 1))
        except Exception:
            pass
    if _id_match:
        # Deduplicate the ID list (same ID can appear multiple times for qty>1)
        _seen_ids: dict = {}  # id → count seen so far
        _id_list = [i.strip() for i in _id_match.group(1).split(',') if i.strip()]
        for _aid in _id_list:
            _seen_ids[_aid] = _seen_ids.get(_aid, 0) + 1
        for _aid, _count in _seen_ids.items():
            _asset = _catalog.get_asset_by_id(_aid)
            if not _asset:
                continue
            _sub = _asset.get('subcategory', '')
            _pl, _fc = _default_placement_for(_sub)
            # Use qty from JSON detail block if available, otherwise from id repetitions
            _qty = max(_count, _qty_map.get(_aid, 1))
            for _qi in range(_qty):
                _slot = _aid if _qty == 1 else f"{_aid}_{_qi + 1}"
                if any(s.get('slot') == _slot for s in kept_specs):
                    continue
                kept_specs.append({
                    'slot':                _slot,
                    'asset_id':            _aid,
                    'subcategory':         _sub,
                    'placement':           _pl,
                    'face':                _fc,
                    'allow_room_mismatch': True,
                })
            existing_subcats.add(_sub)
            _strip_false_missing_warning(_sub)

    # 3) Recover items the user mentioned in their raw prompt that Coach missed.
    # Coach sometimes hallucinates "catalog'da yok" for assets that actually
    # exist (especially Claude). This catches those cases.
    # Excluded subcategories (user said "yok" etc.) are never injected.
    #
    # If the user explicitly asked for NO extras (chip: "Sadece belirttiğim mobilyaları
    # ekle, fazladan hiçbir şey ekleme." or similar), skip step 3 entirely.
    _NO_EXTRAS_PHRASES = [
        "fazladan hiçbir şey ekleme",
        "fazla ekleme",
        "başka hiçbir şey ekleme",
        "sadece belirttiğim mobilya",
        "sadece bu modeller",
        "başka model ekleme",
        "sadece verdiğim",
        "dışına çıkma",
        "ekstra ekleme",
        "no extras",
        "only what i specified",
        "only these models",
        "model detayları",  # JSON model block present → user pinned exact models
    ]
    _strict_mode = any(ph in user_prompt.lower() for ph in _NO_EXTRAS_PHRASES)

    intent_subcats = _detect_user_intent_subcats(user_prompt)
    for sub in intent_subcats:
        if _strict_mode:
            break  # user said no extras — don't inject anything
        if sub in existing_subcats or sub in excluded_subcats:
            continue
        asset = find_asset_for_slot({"subcategory": sub, "fallback": []}, style, room_type)
        if not asset:
            # Genuine catalog gap; Coach already warned (or post-process step 1 did)
            continue
        placement, face = _default_placement_for(sub)
        kept_specs.append({
            "slot":        sub,
            "subcategory": sub,
            "placement":   placement,
            "face":        face,
        })
        existing_subcats.add(sub)
        # Coach may have said this subcategory wasn't in the catalog — wrong.
        _strip_false_missing_warning(sub)
        note = (
            f"ℹ️ '{sub}' kullanıcı promptunda istenmişti ve katalogda mevcut — "
            f"Coach atlamış, post-process otomatik ekledi (placement: {placement})."
        )
        if note not in warnings:
            warnings.append(note)

    parsed["specs"] = kept_specs
    parsed["warnings"] = warnings
    return parsed


def _extract_json_object(text: str) -> dict | None:
    """Try every possible JSON-object start position in *text* using the stdlib
    JSON decoder, which correctly handles string literals containing { and }.
    Returns the first object that has at least one of the expected coach keys,
    or None if nothing parses."""
    import json
    from json.decoder import JSONDecoder
    decoder = JSONDecoder()
    EXPECTED = {"refined_prompt", "room", "specs", "rationale"}
    i = 0
    while i < len(text):
        idx = text.find("{", i)
        if idx == -1:
            break
        try:
            obj, _ = decoder.raw_decode(text, idx)
            if isinstance(obj, dict) and EXPECTED & obj.keys():
                return obj
        except (json.JSONDecodeError, ValueError):
            pass
        i = idx + 1
    return None


def run_prompt_coach(prompt: str, llm: str = "gemini") -> dict:
    """Run the coach once and parse its JSON. Returns a dict with refined_prompt,
    rationale, warnings, plus a raw field for debugging."""
    import json
    import re
    from .team import _get_model

    coach = create_prompt_coach(_get_model(llm))
    response = coach.run(prompt)

    def _text_from(c) -> str:
        """Flatten agno content (str | list-of-parts | other) to plain text."""
        if isinstance(c, list):
            parts = []
            for p in c:
                if isinstance(p, dict):
                    if p.get("type") in ("tool_use", "tool_result"):
                        continue
                    # agno Gemini parts may use "text" or "content" key
                    parts.append(p.get("text") or p.get("content") or "")
                else:
                    parts.append(str(p))
            return " ".join(parts).strip()
        return str(c).strip() if c is not None else ""

    # 1) Direct .content (Claude, simple Gemini responses)
    raw = _text_from(getattr(response, "content", None))

    # 2) Gemini+tool-use: agno may leave .content empty. Scan messages in reverse
    #    for the last assistant/model/agent turn with non-empty text.
    if not raw:
        messages = getattr(response, "messages", None) or []
        for msg in reversed(messages):
            role = (getattr(msg, "role", None)
                    or (msg.get("role") if isinstance(msg, dict) else None)
                    or "")
            if role not in ("assistant", "model", "agent"):
                continue
            mc = (getattr(msg, "content", None)
                  or (msg.get("content") if isinstance(msg, dict) else None))
            text = _text_from(mc)
            if text:
                raw = text
                break

    # 3) Scan ALL messages (any role) for a turn that contains a JSON coach object.
    #    Handles edge cases where agno stores the final Gemini reply under an
    #    unexpected role or attribute.
    if not raw:
        messages = getattr(response, "messages", None) or []
        for msg in reversed(messages):
            mc = (getattr(msg, "content", None)
                  or (msg.get("content") if isinstance(msg, dict) else None))
            text = _text_from(mc)
            if text and "refined_prompt" in text:
                raw = text
                break

    # 4) Try common scalar attributes agno may use
    if not raw:
        for attr in ("text", "output", "answer", "response"):
            val = getattr(response, attr, None)
            if val and isinstance(val, str) and val.strip():
                raw = val.strip()
                break

    # 5) Last resort: stringify the whole RunResponse object
    if not raw:
        raw = str(response).strip()

    # Strip outer markdown fences first (common for both Claude and Gemini)
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw)
    if fence:
        raw = fence.group(1).strip()
    else:
        whole = re.match(r"^```(?:json)?\s*([\s\S]+?)\s*```$", raw)
        if whole:
            raw = whole.group(1).strip()

    # Primary: direct json.loads on the (possibly stripped) text
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: scan every { position with raw_decode (handles } inside strings)
        parsed = _extract_json_object(raw)

    if parsed and isinstance(parsed, dict):
        parsed = _validate_and_complete_specs(parsed, user_prompt=prompt)
        return {
            "refined_prompt": parsed.get("refined_prompt", "").strip(),
            "rationale":      parsed.get("rationale", "").strip(),
            "warnings":       parsed.get("warnings", []) or [],
            "room":           parsed.get("room") or {},
            "specs":          parsed.get("specs", []) or [],
            "house":          parsed.get("house"),
            "raw":            raw,
        }

    # All strategies failed — retry once with a simpler prompt asking for JSON only
    # (Gemini sometimes forgets to produce JSON when instructions are long)
    try:
        retry_prompt = (
            f"{prompt}\n\n"
            "IMPORTANT: Respond with ONLY a valid JSON object containing keys: "
            "refined_prompt, rationale, warnings, room, specs, house. No markdown."
        )
        retry_resp = coach.run(retry_prompt)
        retry_raw = _text_from(getattr(retry_resp, "content", None))
        if not retry_raw:
            msgs = getattr(retry_resp, "messages", None) or []
            for m in reversed(msgs):
                mc = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
                t = _text_from(mc)
                if t and "refined_prompt" in t:
                    retry_raw = t
                    break
        if retry_raw:
            fence2 = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", retry_raw)
            if fence2:
                retry_raw = fence2.group(1).strip()
            retry_parsed = None
            try:
                retry_parsed = json.loads(retry_raw)
            except json.JSONDecodeError:
                retry_parsed = _extract_json_object(retry_raw)
            if retry_parsed and isinstance(retry_parsed, dict):
                retry_parsed = _validate_and_complete_specs(retry_parsed, user_prompt=prompt)
                return {
                    "refined_prompt": retry_parsed.get("refined_prompt", "").strip(),
                    "rationale":      retry_parsed.get("rationale", "").strip(),
                    "warnings":       retry_parsed.get("warnings", []) or [],
                    "room":           retry_parsed.get("room") or {},
                    "specs":          retry_parsed.get("specs", []) or [],
                    "house":          retry_parsed.get("house"),
                    "raw":            retry_raw,
                }
    except Exception:
        pass

    # Final fallback — return original prompt unchanged with a user-friendly message
    return {
        "refined_prompt": prompt,
        "rationale":      "⚠ Model yanıt üretemedi. Prompt değiştirilmedi — doğrudan Tasarla'ya basabilirsiniz.",
        "warnings":       ["Model geçerli JSON döndürmedi. Prompt olduğu gibi kullanılıyor."],
        "room":           {},
        "specs":          [],
        "house":          None,
        "raw":            raw,
    }
