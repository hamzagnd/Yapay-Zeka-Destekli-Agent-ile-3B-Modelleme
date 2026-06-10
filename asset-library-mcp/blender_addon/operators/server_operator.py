"""Modal timer operator for the Asset Library addon server."""

import bpy
from ..server.http_server import BlenderHTTPServer, get_server, set_server
from ..handlers import get_handler_registry


class ASSET_LIBRARY_OT_server_start(bpy.types.Operator):
    """Start the Asset Library HTTP server."""

    bl_idname = "asset_library.server_start"
    bl_label = "Start Asset Library Server"
    bl_options = {"REGISTER"}

    _timer = None

    def modal(self, context, event):
        if event.type == "TIMER":
            server = get_server()
            if server and server.running:
                server.poll()
                server.process_queue(get_handler_registry())
            else:
                self.cancel(context)
                return {"CANCELLED"}
        return {"PASS_THROUGH"}

    def execute(self, context):
        existing = get_server()
        if existing and existing.running:
            self.report({"WARNING"}, "Asset Library server is already running")
            return {"CANCELLED"}

        port = context.scene.asset_library_port
        server = BlenderHTTPServer(host="localhost", port=port)
        try:
            server.start()
        except OSError as e:
            self.report({"ERROR"}, f"Failed to start server: {e}")
            return {"CANCELLED"}

        set_server(server)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)

        self.report({"INFO"}, f"Asset Library server started on port {port}")
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None


class ASSET_LIBRARY_OT_server_stop(bpy.types.Operator):
    """Stop the Asset Library HTTP server."""

    bl_idname = "asset_library.server_stop"
    bl_label = "Stop Asset Library Server"
    bl_options = {"REGISTER"}

    def execute(self, context):
        server = get_server()
        if server and server.running:
            server.shutdown()
            set_server(None)
            self.report({"INFO"}, "Asset Library server stopped")
        else:
            self.report({"WARNING"}, "Server is not running")
        return {"FINISHED"}
