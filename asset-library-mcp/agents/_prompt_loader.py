"""Utility: load agent instructions from agent_prompts.json if present, else use hardcoded defaults."""
from __future__ import annotations
import json
from pathlib import Path

_PROMPTS_FILE = Path(__file__).parent.parent / "agent_prompts.json"


def _load_agent_instructions(key: str, default: list[str]) -> list[str]:
    """Return custom instructions from agent_prompts.json when the key exists, else default."""
    try:
        if _PROMPTS_FILE.exists():
            data = json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))
            if key in data and data[key]:
                return data[key].splitlines()
    except Exception:
        pass
    return default
