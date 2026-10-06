"""GitHub routes: connect an account (OAuth) and export a room's current files to a new repository."""

from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from mux.api.deps import Editor, User
from mux.config import settings
from mux.integrations.github import GitHub, GitHubError, get_github
from mux.rooms.registry import get_registry

router = APIRouter()


def github() -> GitHub:
    return get_github(get_registry().session)


Hub = Annotated[GitHub, Depends(github)]


class ExportIn(BaseModel):
    repo_name: str = Field(pattern=r"^[A-Za-z0-9._-]{1,100}$")
    private: bool = True


def _safe_next(path: str) -> str:
    return path if path.startswith("/") and not path.startswith("//") else "/profile"


@router.get("/github/status")
async def status(user: User, hub: Hub) -> dict[str, object]:
    if not hub.configured:
        return {"configured": False, "connected": False, "login": None}
    return {"configured": True, **await hub.status(user.id)}


@router.get("/github/connect")
async def connect(user: User, hub: Hub, next: str = "/profile") -> dict[str, str]:
    """The URL to send the browser to; GitHub returns it to /github/callback, which returns it to the web app."""
    try:
        return {"url": hub.authorize_url(user.id, _safe_next(next))}
    except GitHubError as e:
        raise HTTPException(e.status, str(e)) from e


@router.get("/github/callback", include_in_schema=False)
async def callback(hub: Hub, state: str = "", code: Annotated[str, Query()] = "", error: str = "") -> RedirectResponse:
    """GitHub's redirect after the user answered. No bearer token here: the state says who it was."""
    pending = hub.take_state(state)
    if pending is None:
        return _back("/profile", "error", "the connection expired, try again")
    if error or not code:
        return _back(pending.next_path, "error", error or "GitHub sent no code")
    try:
        await hub.connect(pending.user_id, code)
    except GitHubError as e:
        return _back(pending.next_path, "error", str(e))
    return _back(pending.next_path, "connected")


def _back(path: str, result: str, detail: str = "") -> RedirectResponse:
    query = {"github": result, **({"detail": detail} if detail else {})}
    sep = "&" if "?" in path else "?"
    return RedirectResponse(f"{settings.web_url.rstrip('/')}{path}{sep}{urlencode(query)}", status_code=303)


@router.post("/rooms/{room_id}/export")
async def export(room_id: UUID, body: ExportIn, access: Editor, hub: Hub) -> dict[str, object]:
    """Create the repository under the caller's GitHub account with the room's current files as one commit."""
    actor = access.actor
    files = {path: await actor.get_blob(entry.hash) for path, entry in list(actor.files.manifest.items())}
    try:
        result = await hub.export(
            access.user.id, body.repo_name, private=body.private, files=files,
            message=f"Export from MUX: {actor.record.title}",
        )
    except GitHubError as e:
        raise HTTPException(e.status, str(e)) from e
    return {"url": result.repo_url, "commit_sha": result.commit_sha, "files": result.files}
