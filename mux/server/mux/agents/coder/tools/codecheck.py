"""A quick check of the JS/TS the coder writes: syntax errors and relative imports of missing files.

Most rooms have no build runner, so without this a missing comma only shows up as a red overlay in the
preview. Parsing uses tree-sitter (JS with JSX, TS, TSX); if it isn't installed the syntax part is skipped
and only imports are checked.
"""

from __future__ import annotations

import inspect
import posixpath
import re
from functools import cache
from typing import Any

CODE_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
_RESOLVE = ("", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json", "/index.js", "/index.jsx", "/index.ts", "/index.tsx")
_IMPORT = re.compile(
    r"""(?:\bimport\s+(?:[\w*{}\s,$]+\s+from\s+)?|\bexport\s+[\w*{}\s,$]+\s+from\s+|\brequire\(\s*|\bimport\(\s*)['"](\.{1,2}/[^'"]+)['"]"""
)


@cache
def _parsers() -> dict[str, Any] | None:
    try:
        import tree_sitter_javascript
        import tree_sitter_typescript
        from tree_sitter import Language, Parser
    except ImportError:
        return None
    js = Parser(Language(tree_sitter_javascript.language()))
    return {
        "js": js,
        "ts": Parser(Language(tree_sitter_typescript.language_typescript())),
        "tsx": Parser(Language(tree_sitter_typescript.language_tsx())),
    }


def is_code(path: str) -> bool:
    return path.lower().endswith(CODE_EXTENSIONS) and "node_modules/" not in path


def syntax_errors(path: str, text: str) -> list[str]:
    parsers = _parsers()
    if parsers is None:
        return []
    ext = path.lower().rsplit(".", 1)[-1]
    tree = parsers["tsx" if ext == "tsx" else "ts" if ext == "ts" else "js"].parse(text.encode("utf-8"))
    node = _first_error(tree.root_node)
    if node is None:
        return []
    # Only the first error: the ones after it are usually knock-on effects of the same mistake
    line, col = node.start_point[0] + 1, node.start_point[1] + 1
    if node.is_missing:
        return [f"{path}:{line}:{col}: syntax error, missing '{node.type}'"]
    lines = text.splitlines()
    snippet = " ".join(lines[line - 1].split())[:60] if line <= len(lines) else ""
    return [f"{path}:{line}:{col}: syntax error near `{snippet}` (a missing ',', bracket or quote?)"]


def _first_error(node: Any) -> Any:
    """The first real error in document order, as deep as possible (an outer ERROR can span the whole file)."""
    if node.is_missing:
        return node
    if node.type == "ERROR" and _bare_ampersand(node):
        return None
    if not (node.has_error or node.type == "ERROR"):
        return None
    for child in node.children:
        if (found := _first_error(child)) is not None:
            return found
    return node if node.type == "ERROR" else None


def _bare_ampersand(node: Any) -> bool:
    # "Built with React & Tailwind" is valid JSX text (Babel and TypeScript accept it); tree-sitter doesn't
    parent = node.parent
    return (parent is not None and parent.type in ("jsx_element", "jsx_fragment")
            and bool(node.children) and node.children[0].type == "&")


def missing_imports(path: str, text: str, existing: set[str]) -> list[str]:
    here = posixpath.dirname(path)
    missing = []
    for spec in dict.fromkeys(m.group(1) for m in _IMPORT.finditer(text)):
        target = posixpath.normpath(posixpath.join(here, spec.split("?")[0]))
        if not any(target + suffix in existing for suffix in _RESOLVE):
            missing.append(f"{path}: imports '{spec}', which doesn't exist")
    return missing


def check_file(path: str, text: str, existing: set[str]) -> list[str]:
    return syntax_errors(path, text) + missing_imports(path, text, existing)


async def project_problems(files: Any, only: list[str] | None = None) -> list[str]:
    """Problems in the project's code files (or just `only`), as "path:line:col: what" lines."""
    existing = set((await _maybe(files.list_files(".")))["files"])
    problems: list[str] = []
    for path in sorted(only if only is not None else existing):
        if not is_code(path):
            continue
        try:
            text = (await _maybe(files.read_file(path)))["content"]
        except Exception:
            continue
        problems += check_file(path, text, existing)
    return problems


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value
