"""Handler for executing AI-generated Blender Python scripts."""

from typing import Any, Dict


def run_python(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an AI-generated Python script inside the running Blender session.

    Args:
        params:
            script – Python source string (has 'bpy' in its namespace)
    """
    import bpy  # noqa: imported inside Blender context

    script = params.get("script", "").strip()
    if not script:
        return {"error": "No script provided"}

    # Strip markdown code fences if the LLM included them
    if script.startswith("```"):
        lines = script.splitlines()
        script = "\n".join(
            l for l in lines
            if not l.strip().startswith("```")
        ).strip()

    try:
        namespace: Dict[str, Any] = {"bpy": bpy, "__builtins__": __builtins__}
        exec(compile(script, "<ai_generated>", "exec"), namespace)  # noqa: S102
        # Scripts can return structured data by setting _result = {...}
        extra = namespace.get("_result", {})
        if isinstance(extra, dict):
            return {"ok": True, "message": "Script executed successfully", **extra}
        return {"ok": True, "message": "Script executed successfully"}
    except Exception as e:
        return {"error": str(e), "script_preview": script[:300]}


GENERATE_HANDLERS: Dict[str, Any] = {
    "run_python": run_python,
}
