"""Compact repository map for the coder agent."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


_SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}

_SUPPORTED_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
}

_PYTHON_EXPORT = re.compile(
    r"^(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)",
    re.MULTILINE,
)

_JS_EXPORT = re.compile(
    r"^\s*export\s+(?:default\s+)?"
    r"(?:async\s+)?(?:function|class|const|let|var)\s+"
    r"([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)

_JS_COMPONENT = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?"
    r"(?:function|const)\s+([A-Z][a-z][A-Za-z0-9_$]*)",
    re.MULTILINE,
)

_HONO_ROUTE = re.compile(
    r"\b(?:app|router)\."
    r"(get|post|put|patch|delete|options|head|all)"
    r"\s*\(\s*[\"'`]([^\"'`]+)",
    re.MULTILINE,
)


def build_repo_map(
    root: str | Path = ".",
) -> list[dict[str, Any]]:
    """Build a compact map of supported source files on disk."""
    repository = Path(root).resolve()

    if not repository.is_dir():
        return []

    files: dict[str, str] = {}

    for path in sorted(repository.rglob("*")):
        if not path.is_file() or _should_skip(path, repository):
            continue

        try:
            files[path.relative_to(repository).as_posix()] = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue

    return map_files(files)


def map_files(
    files: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Build the map from path -> content, e.g. the room's file manifest from the blob store."""
    return [
        _map_file(path, content)
        for path, content in sorted(files.items())
        if Path(path).suffix.lower() in _SUPPORTED_SUFFIXES
        and not any(part in _SKIP_DIRS for part in Path(path).parts)
    ]


def format_repo_map(
    entries: list[dict[str, Any]],
) -> str:
    """Return a repository map as compact text for the coder prompt."""

    lines: list[str] = []

    for entry in entries:
        line = entry["path"]

        if entry["exports"]:
            line += " | exports: " + ", ".join(entry["exports"])

        if entry["components"]:
            line += " | components: " + ", ".join(
                entry["components"]
            )

        if entry["routes"]:
            route_text = ", ".join(
                f"{method.upper()} {route}"
                for method, route in entry["routes"]
            )
            line += " | routes: " + route_text

        lines.append(line)

    return "\n".join(lines)


def _map_file(
    path: str,
    content: str,
) -> dict[str, Any]:
    suffix = Path(path).suffix.lower()

    if suffix == ".py":
        exports = _public_unique(
            match.group(1)
            for match in _PYTHON_EXPORT.finditer(content)
        )
    else:
        exports = _public_unique(
            match.group(1)
            for match in _JS_EXPORT.finditer(content)
        )

    if suffix in {".tsx", ".jsx", ".ts", ".js"}:
        components = _public_unique(
            match.group(1)
            for match in _JS_COMPONENT.finditer(content)
        )
    else:
        components = []

    routes = [
        (match.group(1), match.group(2))
        for match in _HONO_ROUTE.finditer(content)
    ]

    return {
        "path": path,
        "exports": exports,
        "components": components,
        "routes": routes,
    }


def _should_skip(
    path: Path,
    root: Path,
) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True

    return any(
        part in _SKIP_DIRS
        for part in relative.parts
    )


def _public_unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        if value.startswith("_"):
            continue

        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result
