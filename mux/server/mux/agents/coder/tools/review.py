"""Whole-codebase reviews: which files are in scope, a search tool, and checks before a review may finish."""

from __future__ import annotations

import inspect
import re
from pathlib import PurePosixPath
from typing import Any, Optional

from .files import FileToolError

REVIEW_MAX_TURNS = 60  # a review reads every source file, a few per turn
REVIEW_MAX_FILES = 150  # source files a review must read before finishing; larger projects are reviewed in part
MAX_REVIEW_CHARS = 15_000
MAX_MATCHES = 100

SOURCE_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".astro", ".html", ".css", ".scss", ".sass",
    ".less", ".py", ".rb", ".go", ".rs", ".java", ".kt", ".swift", ".php", ".cs", ".c", ".cc", ".cpp", ".h", ".sql",
    ".sh", ".graphql", ".prisma",
}
SKIP_DIRS = {"node_modules", "dist", "build", "out", ".next", ".nuxt", "coverage", "vendor", ".git", "__pycache__"}

SEARCH_TOOL_SCHEMAS: list[dict[str, Any]] = [{
    "type": "function",
    "function": {
        "name": "search_code",
        "description": "Find lines containing some text across the project's source files (e.g. where a function is used).",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
}]


def review_scope(paths: list[str]) -> list[str]:
    """The source files a review reads: code and styles, not lockfiles, assets, docs or build output."""
    scope = []
    for path in paths:
        parts = PurePosixPath(path).parts
        name = parts[-1] if parts else ""
        if any(part in SKIP_DIRS for part in parts[:-1]) or ".min." in name:
            continue
        if PurePosixPath(name).suffix.lower() in SOURCE_EXTENSIONS:
            scope.append(path)
    return sorted(scope)


async def search_code(files: Any, scope: list[str], query: str) -> dict[str, Any]:
    if not query or not query.strip():
        return {"ok": False, "error": "query is required"}
    matches: list[str] = []
    for path in scope:
        try:
            result = files.read_file(path)  # the local tools answer directly, the room's are async
            if inspect.isawaitable(result):
                result = await result
        except (FileToolError, OSError, ValueError):
            continue  # gone or unreadable since the scope was listed
        content = str(result.get("content", "")) if isinstance(result, dict) else ""
        for number, line in enumerate(content.splitlines(), 1):
            if query in line:
                matches.append(f"{path}:{number}: {line.strip()[:200]}")
                if len(matches) >= MAX_MATCHES:
                    return {"ok": True, "matches": matches, "note": f"stopped at {MAX_MATCHES} matches"}
    return {"ok": True, "matches": matches}


_HEADING = {name: re.compile(rf"\b{name}\b", re.I) for name in ("critical", "important", "minor")}


def review_problem(summary: str) -> Optional[str]:
    """Why `summary` isn't a finished review (a one-line recap, missing sections), or None."""
    missing = [name.capitalize() for name, pattern in _HEADING.items() if not pattern.search(summary)]
    if missing or not re.search(r"files reviewed", summary, re.I):
        return ("Not finished: finish_task's summary is the review the team reads, not a recap. Write it in full with "
                "Critical, Important and Minor sections (each finding with file:line, what goes wrong, and a fix), "
                "Strengths, a verdict, and a last line 'Files reviewed: N of M'.")
    return None
