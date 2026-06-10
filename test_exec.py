import traceback

script = """
import bpy, os, mathutils
_result = {"ok": True, "dims": {"width": 1.2, "depth": 1.3, "height": 1.4}}
"""

namespace = {"__builtins__": __builtins__}
try:
    exec(compile(script, "<ai_generated>", "exec"), namespace)
    print("Namespace keys:", list(namespace.keys()))
    print("_result in namespace:", namespace.get("_result"))
except Exception as e:
    print("Exception:", e)
    traceback.print_exc()
