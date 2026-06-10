"""Non-blocking HTTP server for the Asset Library Blender addon.

Identical architecture to blender-orchestrator's server, running on port 8766
so both addons can coexist in the same Blender session without conflicts.
"""

import http.server
import json
import select
import socketserver
import threading
import time
from queue import Queue, Empty
from typing import Any, Callable, Dict, Optional

_server: Optional["BlenderHTTPServer"] = None


def get_server() -> Optional["BlenderHTTPServer"]:
    return _server


def set_server(server: Optional["BlenderHTTPServer"]) -> None:
    global _server
    _server = server


class NonBlockingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    timeout = 0

    def __init__(self, server_address, RequestHandlerClass, request_queue, response_dict):
        self.request_queue = request_queue
        self.response_dict = response_dict
        self.response_events: Dict[str, threading.Event] = {}
        super().__init__(server_address, RequestHandlerClass)

    def handle_request_noblock(self):
        try:
            ready = select.select([self.socket], [], [], 0)
            if ready[0]:
                self.handle_request()
        except Exception:
            pass


class AssetLibraryRequestHandler(http.server.BaseHTTPRequestHandler):

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            request = json.loads(post_data.decode("utf-8"))
            request_id = f"{id(request)}_{time.time()}"
            request["_request_id"] = request_id

            event = threading.Event()
            self.server.response_events[request_id] = event
            self.server.request_queue.put(request)
            event.wait(timeout=60.0)

            if request_id in self.server.response_dict:
                response = self.server.response_dict.pop(request_id)
                self._send_json(200, response)
            else:
                self._send_json(500, {"success": False, "error": "Request timeout"})

            if request_id in self.server.response_events:
                del self.server.response_events[request_id]

        except json.JSONDecodeError as e:
            self._send_json(400, {"success": False, "error": f"Invalid JSON: {e}"})
        except Exception as e:
            self._send_json(500, {"success": False, "error": str(e)})

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "server": "asset-library-mcp"})
        else:
            self._send_json(404, {"error": "Not found"})

    def _send_json(self, status: int, data: Dict[str, Any]):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, format, *args):
        pass


class BlenderHTTPServer:

    def __init__(self, host: str = "localhost", port: int = 8766):
        self.host = host
        self.port = port
        self.request_queue: Queue = Queue()
        self.response_dict: Dict[str, Any] = {}
        self.server: Optional[NonBlockingHTTPServer] = None
        self.running = False

    def start(self):
        if self.running:
            return
        self.server = NonBlockingHTTPServer(
            (self.host, self.port),
            AssetLibraryRequestHandler,
            self.request_queue,
            self.response_dict,
        )
        self.running = True
        print(f"Asset Library server started on {self.host}:{self.port}")

    def poll(self):
        if self.server and self.running:
            self.server.handle_request_noblock()

    def process_queue(self, handler_registry: Dict[str, Callable]):
        try:
            request = self.request_queue.get_nowait()
            request_id = request.pop("_request_id")

            action = request.get("action")
            handler = handler_registry.get(action)

            if handler:
                try:
                    result = handler(request.get("params", {}))
                    response = {"success": True, "result": result}
                except Exception as e:
                    response = {"success": False, "error": str(e)}
            else:
                response = {"success": False, "error": f"Unknown action: {action}"}

            self.response_dict[request_id] = response
            if self.server and request_id in self.server.response_events:
                self.server.response_events[request_id].set()

        except Empty:
            pass

    def shutdown(self):
        if self.server:
            self.running = False
            self.server.server_close()
            self.server = None
            print("Asset Library server stopped")
