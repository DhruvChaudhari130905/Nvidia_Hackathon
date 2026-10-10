"""Tool names models invent, mapped to the coder's real tools.

Nemotron reaches for names other coding agents use (view, read, write, glob) and, told only "unknown tool",
wanders until the repeat guard stops the task (room_db8a580bd5b9: add_image worked, then view / read failed
and it re-read style.css until blocked). Common inventions are translated here; anything else gets an error
that lists the real tool names.
"""

from __future__ import annotations

from typing import Any

_READ = {"view", "read", "cat", "open", "open_file", "view_file", "read_text", "get_file", "show_file"}
_WRITE = {"write", "create", "create_file", "write_to_file", "save_file", "new_file"}
_EDIT = {"edit", "str_replace", "replace", "apply_edit", "update_file", "modify_file", "str_replace_editor"}
_LIST = {"ls", "glob", "list", "list_dir", "list_directory", "find_files", "tree", "dir"}


def _first(args: dict[str, Any], *keys: str) -> Any:
    return next((args[k] for k in keys if args.get(k) not in (None, "")), None)


def resolve(name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The real tool and arguments for a call; unchanged when the name isn't a known invention."""
    path = _first(args, "path", "file_path", "filepath", "filename", "file", "target_file")
    if name in _READ:
        out: dict[str, Any] = {"path": path}
        for key in ("start_line", "end_line"):
            if key in args:
                out[key] = args[key]
        return "read_file", out
    if name in _WRITE:
        return "write_file", {"path": path, "content": _first(args, "content", "file_text", "text", "contents", "code") or ""}
    if name in _LIST:
        folder = _first(args, "path", "directory", "dir", "folder")
        return "list_files", {"path": folder if isinstance(folder, str) and "*" not in folder else "."}
    if name in _EDIT:
        edits = args.get("edits")
        if edits is None:
            find = _first(args, "old_str", "old_string", "find", "search", "old_text")
            replace = _first(args, "new_str", "new_string", "replace", "replacement", "new_text")
            edits = [{"find": find, "replace": replace if replace is not None else ""}] if find is not None else []
        out = {"path": path, "edits": edits}
        if "base_version" in args:
            out["base_version"] = args["base_version"]
        return "edit_file", out
    return name, args
