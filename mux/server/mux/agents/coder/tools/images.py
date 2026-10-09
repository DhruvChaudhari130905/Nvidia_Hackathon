"""add_image: a real, openly licensed photo saved into the project, so pages never show placeholders.

Photos come from Openverse (no API key). The file is stored the way the room keeps every binary file, as
a base64 data URL (mux.files.binary), so the preview, exports and the WebContainer all get the real image.
"""

from __future__ import annotations

import base64
import inspect
from typing import Any

import httpx

SEARCH_URL = "https://api.openverse.org/v1/images/"
MAX_BYTES = 2_000_000  # the room's cap for images (MAX_ASSET_BYTES in the web app)
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_IMAGE_PATH = (".jpg", ".jpeg", ".png", ".webp")


async def add_image(files: Any, client: httpx.AsyncClient, used: set[str], query: str, path: str,
                    added: list[str] | None = None) -> dict[str, Any]:
    """Find a photo for `query`, save it at `path` and return where it went plus its credit line."""
    query = query.strip()
    if not query:
        return {"ok": False, "error": "query is required"}
    if not path.lower().endswith(_IMAGE_PATH):
        return {"ok": False, "error": "path must end in .jpg, .jpeg, .png or .webp"}
    res = await client.get(SEARCH_URL, params={
        "q": query, "license_type": "commercial", "mature": "false", "page_size": 20,
    }, timeout=20)
    res.raise_for_status()
    for hit in res.json().get("results", []):
        if hit.get("id") in used:
            continue
        image = await _download(client, hit.get("url")) or await _download(client, hit.get("thumbnail"))
        if image is None:
            continue
        mime, data = image
        # Keep the name the coder chose, with the extension of what was actually downloaded
        saved = path.rsplit(".", 1)[0] + _EXT[mime] if not path.lower().endswith(_ext_variants(mime)) else path
        content = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        written = files.write_file(saved, content)
        written = await written if inspect.isawaitable(written) else written
        if not written.get("ok"):
            return written
        used.add(hit["id"])
        if added is not None:
            added.append(saved)
        return {"ok": True, "path": saved, "width": hit.get("width"), "height": hit.get("height"),
                "credit": _credit(hit)}
    return {"ok": False, "error": f"no usable photo found for: {query}"}


async def _download(client: httpx.AsyncClient, url: str | None) -> tuple[str, bytes] | None:
    if not url:
        return None
    try:
        res = await client.get(url, timeout=20, follow_redirects=True)
    except httpx.HTTPError:
        return None
    mime = res.headers.get("content-type", "").split(";")[0].strip().lower()
    if res.status_code != 200 or mime not in _EXT or not res.content or len(res.content) > MAX_BYTES:
        return None
    return mime, res.content


def _ext_variants(mime: str) -> tuple[str, ...]:
    return (".jpg", ".jpeg") if mime == "image/jpeg" else (_EXT[mime],)


def _credit(hit: dict[str, Any]) -> str:
    code = str(hit.get("license") or "").lower()
    license = {"cc0": "CC0", "pdm": "Public Domain"}.get(code, f"CC {code.upper()}")
    by = f" by {hit['creator']}" if hit.get("creator") else ""
    return f"{hit.get('title') or 'Photo'}{by} ({license}), {hit.get('foreign_landing_url') or hit.get('url')}"


# Image services that only draw grey boxes: a page still using one isn't finished
PLACEHOLDER_HOSTS = ("via.placeholder.com", "placehold.co", "placehold.it", "dummyimage.com",
                     "picsum.photos", "placekitten.com", "fakeimg.pl")
_CODE = (".html", ".htm", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".css", ".scss")


async def picture_problems(files: Any, added: list[str], created: set[str]) -> list[str]:
    """What's left before a task's pictures are done: placeholder images in use, and added photos never used.

    Placeholders count everywhere when the task added photos (it's about pictures); otherwise only in files
    the task created, so an unrelated task isn't sent off to replace pictures nobody asked about.
    """
    listed = await _maybe(files.list_files("."))
    texts: dict[str, str] = {}
    for path in listed.get("files", []):
        if not path.lower().endswith(_CODE) or path.endswith("package-lock.json"):
            continue
        try:
            texts[path] = (await _maybe(files.read_file(path)))["content"]
        except Exception:
            continue  # binary or unreadable: nothing to check
    problems = [
        f"{path} still uses placeholder images ({', '.join(sorted({h for h in PLACEHOLDER_HOSTS if h in text}))})"
        for path, text in sorted(texts.items())
        if (added or path in created) and any(h in text for h in PLACEHOLDER_HOSTS)
    ]
    for path in added:
        # Pages refer to public/ files from the site root, so public/images/a.jpg is used as /images/a.jpg
        served = path.removeprefix("public/")
        if not any(served in text for text in texts.values()):
            problems.append(f"{path} was added but no page or component uses it")
    return problems


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value
