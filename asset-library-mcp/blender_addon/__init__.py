bl_info = {
    "name": "Asset Library MCP Bridge",
    "author": "Claude Code",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Asset Library",
    "description": "HTTP server bridge for importing local .blend assets via MCP",
    "category": "Development",
}

import bpy
from .operators.server_operator import (
    ASSET_LIBRARY_OT_server_start,
    ASSET_LIBRARY_OT_server_stop,
)
from .server.http_server import get_server


class ASSET_LIBRARY_PT_panel(bpy.types.Panel):
    """Asset Library MCP Server Control Panel"""
    bl_label = "Asset Library MCP"
    bl_idname = "ASSET_LIBRARY_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Library"

    def draw(self, context):
        layout = self.layout
        server = get_server()
        is_running = server is not None and server.running

        if is_running:
            layout.label(text=f"Server running on port {server.port}", icon="CHECKMARK")
            layout.operator("asset_library.server_stop", text="Stop Server", icon="CANCEL")
        else:
            layout.label(text="Server stopped", icon="X")
            layout.operator("asset_library.server_start", text="Start Server", icon="PLAY")

        layout.separator()
        layout.prop(context.scene, "asset_library_port")


def register():
    bpy.types.Scene.asset_library_port = bpy.props.IntProperty(
        name="Port",
        description="Port for the Asset Library HTTP server",
        default=8766,
        min=1024,
        max=65535,
    )
    bpy.utils.register_class(ASSET_LIBRARY_OT_server_start)
    bpy.utils.register_class(ASSET_LIBRARY_OT_server_stop)
    bpy.utils.register_class(ASSET_LIBRARY_PT_panel)


def unregister():
    server = get_server()
    if server and server.running:
        server.shutdown()

    bpy.utils.unregister_class(ASSET_LIBRARY_PT_panel)
    bpy.utils.unregister_class(ASSET_LIBRARY_OT_server_stop)
    bpy.utils.unregister_class(ASSET_LIBRARY_OT_server_start)
    del bpy.types.Scene.asset_library_port


if __name__ == "__main__":
    register()
