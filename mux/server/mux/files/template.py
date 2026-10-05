"""The starter template every room begins from (checkpoint C0)."""

from pathlib import Path

# mux/server/mux/files/template.py -> mux/templates/fullstack-starter
TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates" / "fullstack-starter"
SKIPPED_DIRS = frozenset({"node_modules", ".git", "dist"})

def load_template(root: Path = TEMPLATE_DIR) -> dict[str, bytes]:
    """Every file under `root`, by its path relative to `root` (forward slashes). Build folders are skipped."""
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and not SKIPPED_DIRS.intersection(relative.parts):
            files[relative.as_posix()] = path.read_bytes()
    return files