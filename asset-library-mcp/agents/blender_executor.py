"""Blender Executor Agent — builds the scene in Blender.

v2: the house container is imported at WORLD ORIGIN (0,0,0) with rot_z=0 so the
container's local space matches world space. The Layout Designer's clamp uses the
container's `interior_bbox_local` directly as a world bbox.
"""
from agno.agent import Agent

from ._prompt_loader import _load_agent_instructions
from .tools.blender_tools import (
    check_blender_connection,
    create_room_in_blender,
    import_assets_to_blender,
    get_blender_scene_state,
)


def create_blender_executor(model) -> Agent:
    return Agent(
        name="Blender Executor",
        role="Build the interior design scene in Blender: import container, then furniture",
        model=model,
        tools=[check_blender_connection, create_room_in_blender, import_assets_to_blender, get_blender_scene_state],
        instructions=_load_agent_instructions("blender_executor", [
            "You are the Blender 3D scene construction specialist.",
            "Always start by calling check_blender_connection(). If not running, stop and report.",
            "",
            "=== WORKFLOW A: FROM-SCRATCH ROOM ===",
            "Use when the Space Analyst did NOT report a 'House file:' line.",
            "  1. create_room_in_blender(width, depth, height)",
            "  2. import_assets_to_blender(placement_json)  ← JSON from Layout Designer",
            "  3. get_blender_scene_state() to confirm.",
            "",
            "=== WORKFLOW B: HOUSE CONTAINER ===",
            "Use when the Space Analyst output includes 'House file: <path>'.",
            "  1. DO NOT create a room. Import the HOUSE FIRST at world origin:",
            "     Build a single-item JSON and call import_assets_to_blender with it.",
            "     IMPORTANT — location must be [0,0,0] and rotation_z must be 0 so the",
            "     container's interior_bbox_local matches world coordinates:",
            '     \'[{"slot":"house","file_path":"<house_file_path>","location":[0,0,0],"rotation_z":0,"file_exists":true}]\'',
            "  2. Then call import_assets_to_blender(placement_json) with the furniture JSON",
            "     from the Layout Designer. The Layout Designer has already clamped each",
            "     piece to the room's interior bounding box, so furniture should be INSIDE.",
            "  3. get_blender_scene_state() to confirm the count and positions.",
            "",
            "Report: house imported (yes/no), furniture pieces placed, any errors.",
            "If Blender is not running: instruct the user to open Blender → N panel →",
            "Asset Library tab → Start Server.",
        ]),
    )
