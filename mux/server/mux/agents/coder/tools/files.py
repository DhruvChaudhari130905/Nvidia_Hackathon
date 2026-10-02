"""Coder file tools with line reads and version checks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable


_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "dist"}


class FileToolError(Exception):
    """Base error for coder file tools."""


class StaleVersionError(FileToolError):
    """Raised when a file changed after the coder last read it."""


class FileAlreadyExistsError(FileToolError):
    """Raised when write_file targets an existing file."""


class MissingFileError(FileToolError):
    """Raised when a requested file does not exist."""


class NoMatchError(FileToolError):
    """Raised when an edit find string is not present."""


class FileTools:
    """Read and safely modify files inside a repository."""

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root).resolve()

    def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, Any]:
        """Read a file and return its content plus version stamp."""
        file_path = self._resolve(path)

        if not file_path.is_file():
            raise MissingFileError(f"file not found: {path}")

        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        start = 1 if start_line is None else max(1, start_line)
        end = len(lines) if end_line is None else max(start, end_line)

        selected = lines[start - 1 : end]

        return {
            "path": path,
            "content": "\n".join(selected),
            "version": _version(content),
            "start_line": start,
            "end_line": min(end, len(lines)),
        }

    def write_file(
        self,
        path: str,
        content: str,
    ) -> dict[str, Any]:
        """Create a new file. Refuse to overwrite an existing file."""
        file_path = self._resolve(path)

        if file_path.exists():
            raise FileAlreadyExistsError(
                f"file already exists: {path}"
            )

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        return {
            "ok": True,
            "path": path,
            "version": _version(content),
        }

    def edit_file(
        self,
        path: str,
        base_version: str,
        edits: Iterable[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Apply find/replace edits only when base_version is current.

        No changes are written if the version is stale or an edit
        cannot be matched.
        """
        file_path = self._resolve(path)

        if not file_path.is_file():
            raise MissingFileError(f"file not found: {path}")

        current_content = file_path.read_text(encoding="utf-8")
        current_version = _version(current_content)

        if base_version != current_version:
            return {
                "ok": False,
                "error": "stale: re-read first",
                "path": path,
                "current_version": current_version,
            }

        updated = current_content

        for edit in edits:
            find = edit.get("find", "")
            replace = edit.get("replace", "")

            if not find:
                raise NoMatchError(
                    f"empty find string for: {path}"
                )

            matches = updated.count(find)

            if matches == 0:
                return {
                    "ok": False,
                    "error": "no match",
                    "path": path,
                    "find": find,
                    "version": current_version,
                }

            if matches > 1:
                return {
                    "ok": False,
                    "error": f"find matches {matches} places; include more surrounding text",
                    "path": path,
                    "find": find,
                    "version": current_version,
                }

            updated = updated.replace(find, replace, 1)

        file_path.write_text(updated, encoding="utf-8")
        new_version = _version(updated)

        return {
            "ok": True,
            "path": path,
            "version": new_version,
            "previous_version": current_version,
        }

    def list_files(self, path: str = ".") -> dict[str, Any]:
        """Return files under path, relative to the repository root."""
        directory = self._resolve(path)

        if not directory.is_dir():
            raise MissingFileError(f"directory not found: {path}")

        files = []

        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue

            relative = file_path.relative_to(self.root)

            if any(part in _SKIP_DIRS for part in relative.parts):
                continue

            files.append(relative.as_posix())

        files.sort()

        return {
            "ok": True,
            "files": files,
        }

    def delete_file(
        self,
        path: str,
        base_version: str,
    ) -> dict[str, Any]:
        """Delete a file only when its version is still current."""
        file_path = self._resolve(path)

        if not file_path.is_file():
            raise MissingFileError(f"file not found: {path}")

        content = file_path.read_text(encoding="utf-8")
        current_version = _version(content)

        if base_version != current_version:
            return {
                "ok": False,
                "error": "stale",
                "path": path,
                "current_version": current_version,
            }

        file_path.unlink()

        return {
            "ok": True,
            "path": path,
            "deleted": True,
        }

    def _resolve(self, path: str) -> Path:
        """Resolve a path and prevent access outside the repository."""
        candidate = (self.root / path).resolve()

        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise FileToolError(
                f"path outside repository: {path}"
            ) from exc

        return candidate


def _version(content: str) -> str:
    """Return a deterministic version stamp for file contents."""
    return hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()
