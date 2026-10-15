"""Check saved Python syntax without importing or executing generated code."""

from __future__ import annotations

import ast
from collections.abc import Mapping

from coding_assistant.contracts import Payload


def python_edit_path(name: str, arguments: Mapping[str, object]) -> str | None:
    path = arguments.get("path")
    if name not in {"filesystem.write_file", "filesystem.edit_file"} or arguments.get("dryRun"):
        return None
    return path if isinstance(path, str) and path.lower().endswith((".py", ".pyi")) else None


def syntax_check(path: str, result: Payload) -> Payload:
    """Interpret the full filesystem read response; failure is never a pass."""
    if result.get("is_error"):
        return {"passed": False, "detail": "Could not read saved source; syntax is unverified."}
    structured = result.get("structured_content")
    content = structured.get("content") if isinstance(structured, Mapping) else None
    if not isinstance(content, str):
        blocks = result.get("content")
        if isinstance(blocks, str):
            content = blocks
        elif isinstance(blocks, list):
            texts = [b.get("text") for b in blocks if isinstance(b, Mapping) and b.get("type") == "text"]
            content = "".join(str(text) for text in texts) if texts else None
    if not isinstance(content, str) or len(content) > 2_000_000:
        return {"passed": False, "detail": "Full source unavailable or too large; syntax is unverified."}
    try:
        ast.parse(content.lstrip("\ufeff"), filename=path)
    except (SyntaxError, ValueError, RecursionError) as error:
        detail = f"{type(error).__name__}: {error}"
        return {"passed": False, "detail": detail[:500] + " Repair the saved Python source before finishing."}
    return {"passed": True, "detail": "Saved Python parses successfully. Behavioral tests were not run."}
