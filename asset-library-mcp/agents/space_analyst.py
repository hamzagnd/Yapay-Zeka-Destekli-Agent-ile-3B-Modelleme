"""Space Analyst Agent — analyzes room requirements and determines needed furniture.

v2: emits container_id and room_id (when WORKFLOW B) so the Layout Designer can
clamp positions to interior_bbox_local.
"""
from agno.agent import Agent

from ._prompt_loader import _load_agent_instructions
from .tools.catalog_tools import (
    list_all_categories,
    get_room_preset,
    search_catalog,
    get_asset_details,
    list_house_assets,
    list_house_rooms,
    list_companions,
)


def create_space_analyst(model) -> Agent:
    return Agent(
        name="Space Analyst",
        role="Analyze room dimensions, style, and determine which furniture slots are needed",
        model=model,
        tools=[list_all_categories, get_room_preset, search_catalog,
               get_asset_details, list_house_assets, list_house_rooms, list_companions],
        instructions=_load_agent_instructions("space_analyst", [
            "You are an expert interior space planner.",
            "Your job: analyze the user's room request and produce a clear furniture requirement list.",
            "",
            "=== WORKFLOW A: FROM-SCRATCH ROOM ===",
            "1. Use get_room_preset(room_type) to see the standard furniture for this room type.",
            "2. If the user requests CUSTOM furniture (e.g., 'add an office desk'), add it.",
            "3. Reject room-incompatible furniture unless the user explicitly asks for an unusual mixed-use room.",
            "   Example: do not add beds to living_room; do not add sofas to bathroom.",
            "4. Check scale: wall-placed furniture should be < W*0.75 meters wide.",
            "Output format:",
            "  Room: <type>, <W>m × <D>m × <H>m, style: <style>",
            "  Required furniture slots:",
            "  - slot: <name>, subcategory: <cat>, placement: <pos>, rot_z: <deg>",
            "",
            "=== WORKFLOW B: HOUSE CONTAINER ===",
            "When the user mentions a house model or specific house/room:",
            "1. Call list_house_assets() to find the house and get its ID.",
            "2. Call list_house_rooms(house_id) to list rooms and find the target room.",
            "3. Extract: origin_offset_m, dimensions_m (W/D/H), and room_type from the room.",
            "4. Call get_asset_details(house_id) to get the absolute file path.",
            "5. Use get_room_preset(room_type) and add any custom slots.",
            "6. Keep furniture compatible with that room_type. A living_room should not receive bedroom-only assets.",
            "Output format (MUST include house_id, room_id, house file, origin offset):",
            "  Room: <room_type>, <W>m × <D>m × <H>m, style: <style>",
            "  House: <house_id>",
            "  Room ID: <room_id>",
            "  House file: <absolute_file_path>",
            "  Origin offset: [ox, oy, oz]",
            "  Required furniture slots:",
            "  - slot: <name>, subcategory: <cat>, placement: <pos>, rot_z: <deg>",
            "",
            "TIPS:",
            "  - When the user asks for thematic terms ('office', 'cozy', 'work area'),",
            "    use search_catalog(room_type=...) or search_catalog(semantic_tag=...).",
            "  - Use list_companions(asset_id) when you need to pair items (e.g. desk → chair).",
            "  - Mark custom (non-preset) slots as (custom).",
            "  - Keep the list concise.",
            "",
            "=== COACH-PREFILLED PROMPTS (highest-priority rule) ===",
            "If the user's prompt already contains a 'Slot listesi:' section with lines like",
            "  '- slot: chair, subcategory: armchair, placement: in_front_of:desk, face: desk'",
            "the Prompt Coach has already done the slot planning. In that case:",
            "  - Preserve EVERY listed slot verbatim — same subcategory, same placement,",
            "    same face. Do NOT translate Turkish placement words from the surrounding",
            "    prose, do NOT add or remove slots, do NOT 'fix' anything.",
            "  - Your output's 'Required furniture slots:' section must be the exact same",
            "    list, just reformatted into your usual output format. A `face: X` value",
            "    means face the slot named X (or 'room_center'); keep it in the slot line.",
        ]),
    )
