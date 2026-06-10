"""Interior Architect Team — coordinates all four agents via agno."""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from agno.team import Team
from agno.models.google import Gemini
from agno.models.anthropic import Claude

from ._prompt_loader import _load_agent_instructions
from .space_analyst import create_space_analyst
from .furniture_selector import create_furniture_selector
from .layout_designer import create_layout_designer
from .blender_executor import create_blender_executor


def _get_model(llm: str):
    if llm == "claude":
        return Claude(id="claude-sonnet-4-6")
    return Gemini(id="gemini-2.5-flash")


def create_interior_team(llm: str = "gemini") -> Team:
    """Build the Interior Architect Team with the specified LLM backend.

    Args:
        llm: 'gemini' (default) or 'claude'
    """
    model = _get_model(llm)

    return Team(
        name="Interior Architect Team",
        model=model,
        members=[
            create_space_analyst(model),
            create_furniture_selector(model),
            create_layout_designer(model),
            create_blender_executor(model),
        ],
        instructions=_load_agent_instructions("team", [
            "You are an experienced interior architect leading a design team.",
            "",
            "=== WORKFLOW A: FROM-SCRATCH ROOM ===",
            "Use when no house model is specified.",
            "  1. Space Analyst: analyze room type, dimensions (default 5×4×2.7m), style, custom furniture.",
            "  2. Furniture Selector: find catalog assets for each slot. Prefer room_type filter.",
            "  3. Layout Designer: calculate_furniture_layout(W, D, H, furniture_json,",
            "       origin_offset='[0,0,0]', container_id='', room_id='', room_type='<room_type>').",
            "  4. Blender Executor: create_room_in_blender(W, D, H), then import_assets_to_blender(placement_json).",
            "",
            "=== WORKFLOW B: HOUSE CONTAINER ===",
            "Use when user mentions a house model or says 'my house', 'the two-story house', etc.",
            "  1. Space Analyst: call list_house_assets() to find the house, list_house_rooms(house_id)",
            "     to get the room list. Extract origin_offset_m, dimensions_m, file path.",
            "     Output MUST include all four lines:",
            "       House: <house_id>",
            "       Room ID: <room_id>",
            "       House file: <absolute_path>",
            "       Origin offset: [x, y, z]",
            "  2. Furniture Selector: find catalog assets for each slot. Use room_type from the",
            "     Space Analyst's 'Room:' line. Use list_companions(<desk_id>) when pairing chairs.",
            "  3. Layout Designer: pass the House id and Room ID from Space Analyst as",
            "     container_id and room_id, plus room_type. The tool will clamp every piece",
            "     to interior_bbox_local and reject room-incompatible assets.",
            "  4. Blender Executor: read 'House file' from Space Analyst. Import HOUSE FIRST via",
            "     import_assets_to_blender (single-item JSON, location=[0,0,0], rotation_z=0).",
            "     THEN import furniture via import_assets_to_blender(placement_json).",
            "     Do NOT call create_room_in_blender in this workflow.",
            "",
            "=== NATURAL LANGUAGE RULES ===",
            "  - 'evi' / 'ev modeli' / 'arch_res_modern_2f_01' / 'evin içinde' → Workflow B",
            "  - 'living room içinde' / 'içindeki living room' → room_id matching 'living_room'",
            "  - 'office olan evi' / 'ofis odası' → room_id matching 'office'",
            "  - 'industrial tarz' → style=industrial",
            "  - '6x4' or '6 by 4' → width=6, depth=4",
            "  - chair + no desk mentioned → add desk slot first (chair uses 'in_front_of:desk', rot_z=0)",
            "",
            "=== SUMMARY FORMAT ===",
            "After completion: house/room used, furniture placed (name+position), any errors.",
        ]),
        show_members_responses=True,
        markdown=True,
    )


def run_team(prompt: str, llm: str = "gemini", floor_plan_image: Optional[str] = None) -> str:
    """Run the interior architect team and return the final response text."""
    from agno.media import Image as AgnoImage

    team = create_interior_team(llm)

    images = None
    if floor_plan_image:
        try:
            img_bytes = base64.b64decode(floor_plan_image)
            images = [AgnoImage(content=img_bytes, format="png")]
        except Exception:
            pass

    response = team.run(prompt, images=images) if images else team.run(prompt)
    if hasattr(response, "content") and response.content:
        return response.content
    return str(response)
