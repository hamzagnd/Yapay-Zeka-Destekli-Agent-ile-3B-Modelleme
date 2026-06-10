"""Create the Blender addon zip with forward-slash paths (required by Blender)."""
import zipfile
import os

src = os.path.join(os.path.dirname(__file__), "blender_addon")
dest = os.path.join(os.path.dirname(__file__), "asset_library_mcp_addon.zip")

with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
    parent = os.path.dirname(src)
    for root, dirs, files in os.walk(src):
        for f in files:
            filepath = os.path.join(root, f)
            arcname = os.path.relpath(filepath, parent).replace(os.sep, "/")
            zf.write(filepath, arcname)
            print(arcname)

print(f"\nZip created: {dest}")
