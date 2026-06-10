#!/usr/bin/env python3
"""
recategorize_existing.py — Catalog.json'daki tüm asset'leri auto_categorize ile
yeniden ölçer ve mevcut değerlerle karşılaştırır.

Amaç: forward_axis, footprint, semantic_tags gibi alanların gerçek Blender PCA
ölçümüyle eşleşip eşleşmediğini doğrulamak. Hangi alanların değişeceğini
side-by-side gösterir; kullanıcı seçtiklerini onaylayarak Catalog.json'a yazar.

Kullanım:
  python recategorize_existing.py                  # interaktif (her asset için sor)
  python recategorize_existing.py --dry-run        # sadece diff göster, yazma
  python recategorize_existing.py --auto-accept    # tüm değişiklikleri kabul et
  python recategorize_existing.py --no-llm         # Gemini rafineyi atla
  python recategorize_existing.py --id desk_metal  # sadece bu ID'yi yeniden ölç
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from auto_categorize import auto_categorize_blend, build_catalog_entry  # noqa: E402

CATALOG = ROOT / "Catalog.json"

# Karşılaştırılacak alanlar — bunlar auto_categorize'ın doldurduğu alanlar
COMPARE_FIELDS = [
    "category", "subcategory", "style", "tags",
    "semantic_tags", "room_types", "compatible_with",
    "is_container", "scale_class",
    "footprint", "placement", "dimensions_m",
    "poly_count",
]


# ── Renkli çıktı (Windows uyumlu — ANSI codes) ────────────────────────────
USE_COLOR = sys.stdout.isatty()


def c(text: str, color: str) -> str:
    if not USE_COLOR:
        return text
    codes = {"red": "31", "green": "32", "yellow": "33", "cyan": "36", "gray": "90"}
    return f"\x1b[{codes.get(color, '0')}m{text}\x1b[0m"


def hr(char: str = "─", n: int = 70) -> None:
    print(char * n)


def section(title: str) -> None:
    print()
    hr("═")
    print(f"  {title}")
    hr("═")


# ── Diff helper ──────────────────────────────────────────────────────────
def _normalize(v):
    """Compare-friendly normalization. Lists become sorted lowercase strings."""
    if isinstance(v, list):
        return sorted(str(x).lower() for x in v)
    if isinstance(v, dict):
        return {k: _normalize(v2) for k, v2 in v.items()}
    if isinstance(v, float):
        return round(v, 3)
    if isinstance(v, str):
        return v.lower()
    return v


def diff_fields(old: dict, new: dict) -> dict[str, tuple]:
    """Return {field: (old_val, new_val)} for fields that differ."""
    out: dict[str, tuple] = {}
    for fld in COMPARE_FIELDS:
        ov, nv = old.get(fld), new.get(fld)
        if _normalize(ov) != _normalize(nv):
            out[fld] = (ov, nv)
    return out


def render_value(v) -> str:
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def render_diff(diff: dict[str, tuple]) -> None:
    if not diff:
        print(c("  ✓ Hiçbir alan değişmiyor — Blender ölçümü mevcut katalog ile uyumlu.", "green"))
        return
    for fld, (ov, nv) in diff.items():
        print(f"  {c(fld, 'cyan')}")
        print(f"    eski: {c(render_value(ov), 'gray')}")
        print(f"    yeni: {c(render_value(nv), 'yellow')}")


# ── Ana akış ─────────────────────────────────────────────────────────────
def main() -> int:
    args = sys.argv[1:]
    dry_run     = "--dry-run" in args
    auto_accept = "--auto-accept" in args
    use_llm     = "--no-llm" not in args
    only_id: str | None = None
    if "--id" in args:
        i = args.index("--id")
        only_id = args[i + 1] if i + 1 < len(args) else None

    if not CATALOG.exists():
        print(f"Catalog.json bulunamadı: {CATALOG}", file=sys.stderr)
        return 2

    with open(CATALOG, encoding="utf-8") as f:
        catalog_data = json.load(f)

    assets = catalog_data["assets"]
    if only_id:
        assets = [a for a in assets if only_id in a["id"]]
        if not assets:
            print(f"'{only_id}' eşleşen asset yok.", file=sys.stderr)
            return 2

    print(f"\n{len(assets)} asset yeniden ölçülecek.")
    print(f"  Mode: {'DRY RUN' if dry_run else ('AUTO-ACCEPT' if auto_accept else 'INTERACTIVE')}")
    print(f"  Gemini LLM rafine: {'kapalı' if not use_llm else 'açık (GOOGLE_API_KEY varsa)'}")

    changes_to_apply: list[tuple[int, dict]] = []  # (index_in_catalog, new_entry)

    for asset in assets:
        section(f"{asset['id']}  —  {asset.get('name', '?')}")
        blend_rel = asset.get("file", "")
        blend_abs = ROOT / blend_rel
        if not blend_abs.exists():
            print(c(f"  ✗ Blend dosyası bulunamadı: {blend_abs}", "red"))
            continue

        print(f"  Ölçülüyor: {blend_rel}")
        result = auto_categorize_blend(blend_abs, use_llm=use_llm)

        # Mevcut asset için yeni entry inşa et (geometriyi yeniden hesapla, dosya yollarını koru)
        new_entry = build_catalog_entry(
            result,
            asset_id=asset["id"],
            name=asset["name"],
            file_rel=blend_rel,
            texture_resolution=asset.get("texture_resolution", "unknown"),
            textures=asset.get("textures", {}),
            rooms=asset.get("rooms"),
            container_meta=asset.get("container_meta"),
            source=asset.get("source", ""),
        )
        # added_at korunur
        new_entry["added_at"] = asset.get("added_at", str(date.today()))

        diff = diff_fields(asset, new_entry)
        print(f"  Overall confidence: {result.overall_confidence():.2f}")
        render_diff(diff)

        if not diff:
            continue
        if dry_run:
            continue

        # Apply?
        if auto_accept:
            accept = True
        else:
            ans = input(f"\n  Değişiklikleri uygula? ({c('e', 'green')}/h/q): ").strip().lower()
            if ans == "q":
                print("  Çıkılıyor.")
                break
            accept = (ans == "e" or ans == "")

        if accept:
            # Kataloğun asıl indeksinde değiştirmek için ID üzerinden bul
            for i, a in enumerate(catalog_data["assets"]):
                if a["id"] == asset["id"]:
                    changes_to_apply.append((i, new_entry))
                    print(c("  ✓ Kuyruğa eklendi.", "green"))
                    break

    # ── Yaz ──────────────────────────────────────────────────────────────
    if dry_run:
        print(c("\n[DRY RUN] Hiçbir değişiklik yazılmadı.", "yellow"))
        return 0

    if not changes_to_apply:
        print(c("\nHiçbir değişiklik onaylanmadı.", "gray"))
        return 0

    section(f"{len(changes_to_apply)} değişiklik uygulanıyor")
    for idx, new_entry in changes_to_apply:
        catalog_data["assets"][idx] = new_entry

    catalog_data["updated_at"] = str(date.today())

    backup = CATALOG.with_suffix(".json.bak")
    backup.write_text(json.dumps({"_backup_of": "Catalog.json", "assets": [
        a for i, _ in changes_to_apply for a in [catalog_data["assets"][i]]
    ]}, indent=2), encoding="utf-8")
    print(c(f"  Backup: {backup.name}", "gray"))

    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, indent=2, ensure_ascii=False)
    print(c(f"  ✓ Catalog.json güncellendi ({len(changes_to_apply)} asset).", "green"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
