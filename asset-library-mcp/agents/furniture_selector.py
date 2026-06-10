"""Furniture Selector Agent - searches the catalog and selects the best assets.

v2: prefers room_type / semantic_tag filtering over raw subcategory search so
'office' requests return desks + office chairs, not random armchairs.
"""
from agno.agent import Agent

from ._prompt_loader import _load_agent_instructions
from .tools.catalog_tools import (
    search_catalog,
    get_asset_details,
    list_all_categories,
    list_companions,
)


def create_furniture_selector(model) -> Agent:
    return Agent(
        name="Furniture Selector",
        role="Search the asset library catalog and select the best matching furniture for each slot",
        model=model,
        tools=[search_catalog, get_asset_details, list_all_categories, list_companions],
        instructions=_load_agent_instructions("furniture_selector", [
            "You are an expert furniture curator for interior design.",
            "Your job: for each furniture slot from the Space Analyst, find the best asset.",
            "",
            "Selection strategy (try in order, stop on first match):",
            "  1. search_catalog(subcategory=<slot.subcategory>, room_type=<room.type>, style=<style>)",
            "  2. search_catalog(subcategory=<slot.subcategory>, room_type=<room.type>)",
            "  3. Only if still empty, search_catalog(subcategory=<slot.subcategory>) and",
            "     reject any result whose Room types do not include <room.type>.",
            "  4. If the slot subcategory has no room-compatible match, skip if optional.",
            "",
            "When pairing furniture (e.g. picking a chair for a desk), call",
            "list_companions(<desk_asset_id>) to get assets whose `compatible_with`",
            "matches - this avoids putting a lounge chair in front of an office desk.",
            "",
            "Confirm dimensions with get_asset_details(id) when you're unsure of fit.",
            "",
            "OUTPUT - a JSON list ONLY (no markdown fences, no extra text):",
            '[{"slot":"<name>","asset_id":"<id>","placement":"<placement>","room_type":"<room_type>","face":"room_center|<slot>|default"}, ...]',
            "",
            "Use the same placement values as given by the Space Analyst.",
            "If a slot line already has explicit `placement:` and `face:` values (because",
            "the Prompt Coach pre-resolved them), preserve those exact strings — do not",
            "change in_front_of:desk to beside:desk:right or anything similar. Your only",
            "job for those slots is filling in asset_id from the catalog.",
            "When placement/face is NOT specified, default to face='room_center' for wall",
            "furniture and face='<reference slot>' for chairs/seating paired with a desk,",
            "table, sofa, or coffee_table.",
            "Do not place bedroom-only assets in living_room/office/etc.; the Layout",
            "Designer will reject room mismatches as a final guardrail.",
            "Only set allow_room_mismatch=true when the user explicitly requests a",
            "mixed-use exception, such as an office desk inside a living room.",
        ]),
    )
