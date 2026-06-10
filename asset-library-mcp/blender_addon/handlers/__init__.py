from .blend_import import BLEND_IMPORT_HANDLERS
from .room import ROOM_HANDLERS
from .generate import GENERATE_HANDLERS


def get_handler_registry():
    registry = {}
    registry.update(BLEND_IMPORT_HANDLERS)
    registry.update(ROOM_HANDLERS)
    registry.update(GENERATE_HANDLERS)
    return registry
