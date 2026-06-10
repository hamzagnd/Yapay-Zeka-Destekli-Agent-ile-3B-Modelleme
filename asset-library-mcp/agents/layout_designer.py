"""Layout Designer Agent — calculates precise furniture positions.

v2: passes container_id and room_id so positions are clamped to interior_bbox_local.
"""
from agno.agent import Agent

from ._prompt_loader import _load_agent_instructions
from .tools.layout_tools import calculate_furniture_layout


def create_layout_designer(model) -> Agent:
    return Agent(
        name="Layout Designer",
        role="Calculate exact 3D positions for each furniture piece in the room",
        model=model,
        tools=[calculate_furniture_layout],
        instructions=_load_agent_instructions("layout_designer", [
            "You are a precision interior layout engineer.",
            "Take the furniture selection JSON from the Furniture Selector and compute positions.",
            "",
            "Call signature:",
            "  calculate_furniture_layout(",
            "    room_width, room_depth, room_height,",
            "    furniture_json,",
            "    origin_offset='[x,y,z]',",
            "    container_id='<house_id or empty>',",
            "    room_id='<room_id or empty>',",
            "    room_type='<living_room | bedroom | office | ...>'",
            "  )",
            "",
            "=== WORKFLOW A: FROM-SCRATCH ROOM ===",
            "  origin_offset = '[0.0, 0.0, 0.0]'",
            "  container_id  = ''",
            "  room_id       = ''",
            "  room_type     = '<room type from Space Analyst>'",
            "",
            "=== WORKFLOW B: HOUSE CONTAINER ===",
            "Read these from the Space Analyst output verbatim:",
            "  - 'Origin offset: [ox, oy, oz]'  → origin_offset='[ox, oy, oz]'",
            "  - 'House: <house_id>'            → container_id='<house_id>'",
            "  - 'Room ID: <room_id>'           → room_id='<room_id>'",
            "",
            "When container_id + room_id are set, the tool will clamp every piece to that",
            "room's interior_bbox_local so furniture cannot spawn outside the house shell.",
            "It also reads the room_type from Catalog.json and rejects mismatched assets",
            "(for example: no bed in a living_room).",
            "",
            "Example WORKFLOW B call:",
            "  calculate_furniture_layout(",
            "    5.0, 4.0, 2.7,",
            "    furniture_json,",
            "    origin_offset='[0.0, 0.0, 0.0]',",
            "    container_id='arch_res_modern_2f_01',",
            "    room_id='living_room_1f',",
            "    room_type='living_room'",
            "  )",
            "",
            "Prefer semantic facing over manual rotation. When useful, furniture_json items",
            "may include face='room_center' or face='<slot>' so chairs/sofas look toward",
            "the conversation area instead of a wall.",
            "",
            "CRITICAL OUTPUT CONTRACT — copy/paste the tool's JSON string EXACTLY:",
            "  - Do NOT summarize, paraphrase, or reformat into a table.",
            "  - Do NOT drop any field. The Blender Executor needs slot, asset_id, file_path,",
            "    location, rotation_z, file_exists, name, and dimensions_m for every piece.",
            "  - Do NOT round, edit, or 'clean up' rotation_z — it is the correct value.",
            "  - Your entire response must be the JSON array returned by the tool and nothing",
            "    else (no prose, no markdown fences). Blender Executor parses it as JSON.",
        ]),
    )
