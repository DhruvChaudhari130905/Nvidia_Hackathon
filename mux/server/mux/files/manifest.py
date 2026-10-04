"""Manifests (path to hash), version stamps, and diffs between manifests."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from uuid import uuid4


@dataclass
class FileEntry:
    """Entry in the file manifest."""
    file_id: str
    path: str
    size: int
    hash: str
    file_type: Optional[str] = None


class FileManifest:
    """Tracks file metadata: path -> file_id, size, hash."""

    def __init__(self) -> None:
        self._entries: Dict[str, FileEntry] = {}  # path -> FileEntry
        self._by_id: Dict[str, FileEntry] = {}    # file_id -> FileEntry
        self._checkpoints: Dict[str, Dict[str, Any]] = {}  # checkpoint_id -> checkpoint_data
        self._export_history: List[Dict[str, Any]] = []    # export history records
        self._room_metadata: Dict[str, Any] = {}           # room name, description
        self._lock = asyncio.Lock()

    def add(self, file_id: str, path: str, size: int, hash: Optional[str] = None, file_type: Optional[str] = None) -> None:
        """Add or update a file entry."""
        entry = FileEntry(file_id=file_id, path=path, size=size, hash=hash or "", file_type=file_type)
        self._entries[path] = entry
        self._by_id[file_id] = entry

    def update(self, path: str, size: int, hash: Optional[str] = None) -> None:
        """Update an existing file entry."""
        if path in self._entries:
            entry = self._entries[path]
            entry.size = size
            if hash:
                entry.hash = hash

    def remove(self, path: str) -> bool:
        """Remove a file entry. Returns True if existed."""
        if path in self._entries:
            entry = self._entries.pop(path)
            self._by_id.pop(entry.file_id, None)
            return True
        return False

    def get_id(self, path: str) -> Optional[str]:
        """Get file_id for a path."""
        entry = self._entries.get(path)
        return entry.file_id if entry else None

    def get_entry(self, path: str) -> Optional[FileEntry]:
        """Get full entry for a path."""
        return self._entries.get(path)

    def get_by_id(self, file_id: str) -> Optional[FileEntry]:
        """Get entry by file_id."""
        return self._by_id.get(file_id)

    def list_paths(self) -> List[str]:
        """List all tracked file paths."""
        return list(self._entries.keys())

    def list_entries(self) -> List[FileEntry]:
        """List all entries."""
        return list(self._entries.values())

    # Checkpoint methods
    def add_checkpoint(self, checkpoint_id: str, checkpoint_data: Dict[str, Any]) -> None:
        """Store a checkpoint."""
        self._checkpoints[checkpoint_id] = checkpoint_data

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a checkpoint."""
        return self._checkpoints.get(checkpoint_id)

    def list_checkpoints(self) -> Dict[str, Dict[str, Any]]:
        """List all checkpoints."""
        return dict(self._checkpoints)

    # Room metadata methods
    def set_room_metadata(self, name: Optional[str] = None, description: Optional[str] = None) -> None:
        """Set room name and description."""
        if name is not None:
            self._room_metadata["name"] = name
        if description is not None:
            self._room_metadata["description"] = description

    def get_room_metadata(self) -> Dict[str, Optional[str]]:
        """Get room name and description."""
        return {
            "name": self._room_metadata.get("name"),
            "description": self._room_metadata.get("description"),
        }

    # Export history methods
    def add_export_record(self, record: Dict[str, Any]) -> None:
        """Add an export record to history."""
        self._export_history.append(record)

    def get_export_history(self) -> List[Dict[str, Any]]:
        """Get export history."""
        return list(self._export_history)

    def reset_files(self) -> None:
        """Forget all file entries but keep checkpoints, export history and room metadata."""
        self._entries.clear()
        self._by_id.clear()

    def rebuild_from_checkpoint(self, files_data: Dict[str, str]) -> None:
        """Rebuild manifest from checkpoint file data.

        Regenerates file_ids and computes metadata from content.
        """
        self._entries.clear()
        self._by_id.clear()
        for path, content in files_data.items():
            file_id = str(uuid4())
            size = len(content.encode())
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:16]
            file_type = mimetypes.guess_type(path)[0]
            entry = FileEntry(file_id=file_id, path=path, size=size, hash=hash_val, file_type=file_type)
            self._entries[path] = entry
            self._by_id[file_id] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, path: str) -> bool:
        return path in self._entries

    @property
    def entries(self) -> dict[str, FileEntry]:
        """Return all file entries as a dict of path -> FileEntry."""
        return dict(self._entries)