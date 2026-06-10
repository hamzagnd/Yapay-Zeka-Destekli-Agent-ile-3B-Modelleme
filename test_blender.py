import httpx

script = """
import bpy, os, mathutils
_result = {"ok": True, "dims": {"width": 1.2, "depth": 1.3, "height": 1.4}}
"""

try:
    with httpx.Client(timeout=40.0) as c:
        r = c.post("http://localhost:8766",
                   json={"action": "run_python", "params": {"script": script}})
        r.raise_for_status()
        res = r.json()
        print("Response:", res)
except Exception as e:
    print("Error:", e)
