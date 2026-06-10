#!/usr/bin/env python3
"""
add_asset.py — Modeli asset library kataloğuna ekler (v2 schema).

Yeni: auto_categorize.py'i çağırarak bbox, forward axis, room_types, semantic_tags,
compatible_with alanlarını otomatik doldurur. Kullanıcı yalnızca düşük güvenli
alanları doğrular.

Kullanım:
  python add_asset.py                                         # zip/ altında tek zip varsa otomatik
  python add_asset.py model.zip                               # belirli zip
  python add_asset.py model.blend                             # doğrudan .blend
  python add_asset.py model.zip  --quick                      # düşük confidence olsa bile sormaz (CI)
  python add_asset.py model.zip  --quick --name "Red Chair"   # isim de ver, hiç prompt çıkmaz
  python add_asset.py model.zip  --quick --name "X" --id "x"  # tam otomatik
  python add_asset.py model.blend --no-llm                    # Gemini rafineyi atlar
"""

import json
import re
import shutil
import sys
import textwrap
import zipfile
from dataclasses import asdict
from datetime import date
from pathlib import Path

# ── auto_categorize import ───────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from auto_categorize import (
    CategorizationResult,
    auto_categorize_blend,
    build_catalog_entry,
    forward_axis_to_correction_z,
)

# ── Sabit yollar ──────────────────────────────────────────────────────────
CATALOG = ROOT / "Catalog.json"
ZIP_DIR = ROOT / "zip"
MODELS  = ROOT / "models"

# Onay eşiği — bunun altındaki alanlar kullanıcıya sorulur
CONFIDENCE_PROMPT_THRESHOLD = 0.7

ROOM_TYPES = ["living_room", "office", "home_office", "bedroom", "dining_room",
              "kitchen", "bathroom", "study", "lobby", "outdoor"]

TEXTURE_TYPE_PATTERNS = [
    (r"diff|albedo|col(?!or)|basecolor",       "diffuse"),
    (r"rough",                                 "roughness"),
    (r"metal",                                 "metallic"),
    (r"nor_gl|normal_gl|nrm_gl",              "normal_gl"),
    (r"nor_dx|normal_dx|nrm_dx",              "normal_dx"),
    (r"nor(?!_)|nrm(?!_)",                    "normal_gl"),
    (r"disp|height(?!_)",                     "displacement"),
    (r"\bao\b|ambient_occ",                   "ao"),
    (r"emit|emiss",                           "emission"),
    (r"opac|alpha|mask",                      "opacity"),
]

FORWARD_AXIS_OPTIONS = {"1": "+Y", "2": "-Y", "3": "+X", "4": "-X"}
FORWARD_AXIS_LABELS = {
    "+Y": "Kuzey (+Y) — modelin önü +Y'ye bakıyor",
    "-Y": "Güney (-Y) — modelin önü -Y'ye bakıyor",
    "+X": "Doğu  (+X) — modelin önü +X'e bakıyor",
    "-X": "Batı  (-X) — modelin önü -X'e bakıyor",
}


# ── Yardımcılar ───────────────────────────────────────────────────────────
def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    val = input(f"  {prompt}{hint}: ").strip()
    return val if val else default


def ask_list(prompt: str, default: list) -> list:
    raw = ask(prompt, ", ".join(default))
    return [t.strip() for t in raw.split(",") if t.strip()]


def ask_int(prompt: str, default: int) -> int:
    raw = ask(prompt, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def ask_float(prompt: str, default: float) -> float:
    raw = ask(prompt, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


def hr(char="─", n=60):
    print(char * n)


def section(title: str):
    print()
    hr()
    print(f"  {title}")
    hr()


def texture_type(filename: str) -> str:
    low = filename.lower()
    for pattern, ttype in TEXTURE_TYPE_PATTERNS:
        if re.search(pattern, low):
            return ttype
    return "other"


def confirm_field(result: CategorizationResult, field: str, label: str, quick: bool) -> None:
    """Düşük güvenli alanı kullanıcıya göster ve onay/değişiklik al."""
    conf = result.confidences.get(field, 0.0)
    src = result.sources.get(field, "?")
    current = getattr(result, field)

    if quick or conf >= CONFIDENCE_PROMPT_THRESHOLD:
        return

    if isinstance(current, list):
        shown = ", ".join(current) if current else "(boş)"
        print(f"  {label}: {shown}  (confidence={conf:.2f}, source={src})")
        new_raw = ask(f"  → düzenle (virgülle) veya Enter ile kabul et", shown)
        new_list = [t.strip() for t in new_raw.split(",") if t.strip()]
        setattr(result, field, new_list)
    else:
        print(f"  {label}: {current}  (confidence={conf:.2f}, source={src})")
        new_val = ask(f"  → düzenle veya Enter ile kabul et", str(current))
        setattr(result, field, new_val)


# ── Ana akış ─────────────────────────────────────────────────────────────
def main() -> None:
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║      Asset Library — v2 Katalog Ekleme (auto-cat)       ║")
    print("╚══════════════════════════════════════════════════════════╝")

    argv = sys.argv[1:]
    quick   = "--quick"  in argv
    use_llm = "--no-llm" not in argv

    # --name "Foo Bar"  and  --id "foo_bar"  flags (skip interactive name/ID prompts)
    def _flag(flag):
        try:
            i = argv.index(flag)
            return argv[i + 1]
        except (ValueError, IndexError):
            return None

    forced_name = _flag("--name")
    forced_id   = _flag("--id")

    args = [a for a in argv if not a.startswith("--")]

    # ── ADIM 1: Kaynak dosyayı seç ────────────────────────────────────────
    section("ADIM 1 — Kaynak Dosya")

    blend_direct = False
    blend_path_abs = None
    zip_path = None
    blend_entry = ""

    if args:
        arg = Path(args[0])
        if not arg.is_absolute():
            arg = ZIP_DIR / arg if arg.suffix.lower() == ".zip" else arg
        if arg.suffix.lower() == ".blend":
            blend_direct = True
            blend_path_abs = arg.resolve()
        else:
            zip_path = arg
    else:
        zips = sorted({z.resolve() for z in list(ZIP_DIR.glob("*.zip")) + list(ROOT.glob("*.zip"))})
        blends_root = sorted(ROOT.glob("*.blend"))
        all_sources = [(z, "zip") for z in zips] + [(b, "blend") for b in blends_root]
        if not all_sources:
            sys.exit(
                "  Hata: .zip veya .blend dosyası bulunamadı.\n"
                f"  {ROOT} veya {ZIP_DIR} altına koy, ya da: python add_asset.py dosyam.zip"
            )
        if len(all_sources) == 1:
            src, stype = all_sources[0]
            print(f"  Kaynak: {src.name}")
        else:
            print("  Birden fazla kaynak:")
            for i, (s, t) in enumerate(all_sources, 1):
                print(f"    {i}. [{t.upper()}] {s.name}")
            idx = ask_int("Seçin (numara)", 1) - 1
            src, stype = all_sources[idx]
        if stype == "blend":
            blend_direct = True
            blend_path_abs = Path(src).resolve()
        else:
            zip_path = Path(src)

    # ── ADIM 2: Zip ise çıkart, blend'i bul ──────────────────────────────
    tex_files: list[str] = []
    if blend_direct:
        stem = blend_path_abs.stem
        blend_entry = blend_path_abs.name
        base_id = re.sub(r"[_\-]?\d+k$", "", stem, flags=re.I)
        resolution = "unknown"
        # Yan klasördeki textureler
        for f in blend_path_abs.parent.iterdir():
            if re.search(r"\.(jpg|jpeg|png|exr|hdr|tiff?|tga|bmp)$", f.name, re.I):
                tex_files.append(f.name)
    else:
        section("ADIM 2 — Zip İçeriği")
        with zipfile.ZipFile(zip_path) as zf:
            entries = zf.namelist()
        blend_files = [e for e in entries if e.endswith(".blend")]
        tex_files   = [e for e in entries
                       if re.search(r"\.(jpg|jpeg|png|exr|hdr|tiff?|tga|bmp)$", e, re.I)]
        if not blend_files:
            sys.exit("  Hata: zip içinde .blend dosyası yok.")
        blend_entry = blend_files[0]
        stem = Path(blend_entry).stem
        base_id = re.sub(r"[_\-]?\d+k$", "", stem, flags=re.I)
        res_match = re.search(r"(\d+k)", stem, re.I)
        resolution = res_match.group(1).lower() if res_match else "unknown"
        print(f"  Blend     : {blend_entry}")
        print(f"  Textureler: {len(tex_files)} adet")

    # ── ADIM 3: Temel meta — kullanıcı isim/ID ────────────────────────────
    section("ADIM 3 — Temel Bilgiler")
    default_name = stem.replace("_", " ").title()
    default_id   = base_id
    if forced_name or (quick and forced_name is None and forced_id is None):
        name = forced_name or default_name
        aid  = forced_id   or default_id
        print(f"  İsim : {name}")
        print(f"  ID   : {aid}")
    else:
        name = forced_name or ask("Görünen isim", default_name)
        aid  = forced_id   or ask("ID (slug, küçük harf ve alt çizgi)", default_id)

    # ── ADIM 4: Dest klasör — extract et ──────────────────────────────────
    section("ADIM 4 — Dosyalar")

    # cat değerini henüz bilmiyoruz — auto_categorize Blender'a kadar gitmesi gerekiyor.
    # Geçici çözüm: extract'i Blender ölçümünden önce yap (zip için), kategori sonradan
    # belirlenince models/<cat>/<aid> klasörüne taşıyacağız.
    if blend_direct:
        blend_for_measure = blend_path_abs
        print(f"  Blend yolu : {blend_path_abs}")
    else:
        # Geçici extract → models/_pending/<aid>/
        pending = MODELS / "_pending" / aid
        if pending.exists():
            shutil.rmtree(pending)
        pending.mkdir(parents=True)
        print(f"  Çıkartılıyor (geçici) → {pending.relative_to(ROOT)}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(pending)
        blend_for_measure = pending / blend_entry

    # ── ADIM 5: Otomatik kategorize ───────────────────────────────────────
    section("ADIM 5 — Otomatik Kategorize (auto_categorize)")
    print("  Blender headless ölçüm + PCA + heuristic" + (" + Gemini rafine" if use_llm else "") + "...")
    result = auto_categorize_blend(blend_for_measure, use_llm=use_llm)

    print(f"\n  Otomatik bulundu:")
    print(f"    Kategori     : {result.category}/{result.subcategory}    (conf {result.confidences.get('category', 0):.2f})")
    print(f"    Boyut (m)    : {result.dimensions_m.get('width','?')}w × {result.dimensions_m.get('depth','?')}d × {result.dimensions_m.get('height','?')}h")
    print(f"    Forward axis : {result.forward_axis}    (conf {result.confidences.get('forward_axis', 0):.2f})")
    print(f"    Room types   : {', '.join(result.room_types) or '-'}")
    print(f"    Semantic tags: {', '.join(result.semantic_tags) or '-'}")
    print(f"    Compatible   : {', '.join(result.compatible_with) or '-'}")
    print(f"    Style        : {', '.join(result.style) or '-'}")
    print(f"    Poly count   : {result.poly_count}")
    print(f"    Overall conf : {result.overall_confidence():.2f}")

    # ── ADIM 6: Düşük güvenli alanları onaylat ────────────────────────────
    section("ADIM 6 — Düşük Güvenli Alanlar (manuel onay)")
    confirm_field(result, "category",        "Kategori",       quick)
    confirm_field(result, "subcategory",     "Alt kategori",   quick)
    confirm_field(result, "style",           "Stil",           quick)
    confirm_field(result, "room_types",      "Room types",     quick)
    confirm_field(result, "semantic_tags",   "Semantic tags",  quick)
    confirm_field(result, "compatible_with", "Compatible with",quick)

    # Forward axis — her zaman kullanıcıya sor (Blender'da gözle doğrulamak için)
    if not quick:
        conf = result.confidences.get("forward_axis", 0)
        print(f"\n  Forward axis tahmini: {result.forward_axis}  ({FORWARD_AXIS_LABELS[result.forward_axis]})  [conf {conf:.2f}]")
        print("  Modelin Blender'da hangi yöne baktığını doğrula:")
        for k, v in FORWARD_AXIS_OPTIONS.items():
            print(f"    {k} = {FORWARD_AXIS_LABELS[v]}")
        choice = ask("  Seçim (Enter = mevcut)", "")
        if choice in FORWARD_AXIS_OPTIONS:
            result.forward_axis = FORWARD_AXIS_OPTIONS[choice]
            result.facing_correction_z = forward_axis_to_correction_z(result.forward_axis)

    # ── ADIM 7: Klasöre taşı (kategori bilindi) ───────────────────────────
    cat = result.category
    dest = MODELS / cat / aid
    if blend_direct:
        rel_blend = f"models/{cat}/{aid}/{blend_entry}"
        # Direct blend için kopyalama yok — kullanıcı zaten yerleştirmiş
    else:
        if dest.exists():
            ow = ask(f"  '{dest.relative_to(ROOT)}' zaten var — üzerine yaz? (e/h)", "h")
            if ow.lower() != "e":
                sys.exit("  İptal.")
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pending), str(dest))
        rel_blend = f"models/{cat}/{aid}/{blend_entry}"
    rel_blend = rel_blend.replace("\\", "/")

    # ── ADIM 8: Textureler ────────────────────────────────────────────────
    textures: dict[str, str] = {}
    if blend_direct:
        for tf in tex_files:
            ttype = texture_type(tf)
            rel = f"models/{cat}/{aid}/{tf}".replace("\\", "/")
            textures[ttype] = rel
    else:
        for tex in tex_files:
            ttype = texture_type(Path(tex).name)
            rel = f"models/{cat}/{aid}/{tex}".replace("\\", "/")
            textures[ttype] = rel

    # ── ADIM 9: Mimari assetler için oda tanımı ──────────────────────────
    rooms = None
    container_meta = None
    if result.is_container:
        section("ADIM 9 — Mimari Asset: Odalar")
        print("  Bu bir konteyner (ev/bina). Odaları tanımla.")
        print("  (Blender'da 3D cursor ile oda merkezini ölç)")
        rooms = []
        while True:
            more = ask("Oda ekle? (e/h)", "h")
            if more.lower() != "e":
                break
            room_id = ask("  room_id (ör: living_room_1f)", "")
            if not room_id:
                continue
            room_name = ask("  Görünen isim", room_id.replace("_", " ").title())
            floor_no  = ask_int("  Kat numarası", 1)
            print(f"  Oda tipleri: {', '.join(ROOM_TYPES)}")
            room_type = ask("  Oda tipi", "living_room")
            print("  Origin koordinatları (Blender 3D cursor):")
            ox = ask_float("    X (m)", 0.0)
            oy = ask_float("    Y (m)", 0.0)
            oz = ask_float("    Z (m)", 0.0)
            print("  Oda boyutları:")
            rw = ask_float("    Genişlik (m)", 5.0)
            rd = ask_float("    Derinlik (m)", 4.0)
            rh = ask_float("    Tavan (m)", 2.7)
            rooms.append({
                "room_id":         room_id,
                "room_name":       room_name,
                "floor":           floor_no,
                "room_type":       room_type,
                "origin_offset_m": [round(ox, 3), round(oy, 3), round(oz, 3)],
                "dimensions_m":    {"width": round(rw, 3), "depth": round(rd, 3), "height": round(rh, 3)},
                "interior_bbox_local": {
                    "min": [round(ox - rw/2 + 0.2, 3), round(oy - rd/2 + 0.2, 3), round(oz, 3)],
                    "max": [round(ox + rw/2 - 0.2, 3), round(oy + rd/2 - 0.2, 3), round(oz + rh - 0.1, 3)],
                },
            })
            print(f"  ✓ Oda eklendi: {room_name}")

    # ── ADIM 10: Catalog girişini inşa et ─────────────────────────────────
    entry = build_catalog_entry(
        result,
        asset_id=aid,
        name=name,
        file_rel=rel_blend,
        texture_resolution=resolution,
        textures=textures,
        rooms=rooms,
        container_meta=container_meta,
        source=(f"zip/{zip_path.name}" if not blend_direct else f"blend/{blend_path_abs.name}"),
    )

    # ── ADIM 11: Özet + onay ──────────────────────────────────────────────
    section("ADIM 11 — Özet")
    dim_str = f"{result.dimensions_m.get('width','?')}w × {result.dimensions_m.get('depth','?')}d × {result.dimensions_m.get('height','?')}h m"
    print(f"  ID          : {aid}")
    print(f"  İsim        : {name}")
    print(f"  Kategori    : {cat}/{result.subcategory}")
    print(f"  Room types  : {', '.join(result.room_types) or '-'}")
    print(f"  Forward axis: {result.forward_axis}  (facing_correction_z={result.facing_correction_z}°)")
    print(f"  Boyut       : {dim_str}")
    print(f"  Container   : {result.is_container}")
    if rooms:
        print(f"  Odalar      : {len(rooms)} — {', '.join(r['room_name'] for r in rooms)}")
    print(f"  Dosya       : {rel_blend}")

    confirm = ask("Kataloğa kaydet? (e/h)", "e") if not quick else "e"
    if confirm.lower() != "e":
        sys.exit("  İptal edildi.")

    # ── ADIM 12: Catalog.json'a yaz ───────────────────────────────────────
    with open(CATALOG, encoding="utf-8") as f:
        catalog_data = json.load(f)
    existing_ids = {a["id"] for a in catalog_data["assets"]}
    if aid in existing_ids:
        print(f"\n  Uyarı: '{aid}' zaten var — güncelleniyor.")
        catalog_data["assets"] = [a for a in catalog_data["assets"] if a["id"] != aid]
    catalog_data["assets"].append(entry)
    catalog_data["updated_at"] = str(date.today())
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, indent=2, ensure_ascii=False)

    print(f"\n  ✓ '{name}' kataloga eklendi.")
    print(f"    ID: {aid}  |  Forward: {result.forward_axis} ({result.facing_correction_z}°)  |  {dim_str}")

    # ── ADIM 13: Zip sil? ─────────────────────────────────────────────────
    if not blend_direct and not quick:
        if ask("\n  Zip dosyasını sil? (e/h)", "h").lower() == "e":
            zip_path.unlink()
            print(f"  {zip_path.name} silindi.")


if __name__ == "__main__":
    main()
