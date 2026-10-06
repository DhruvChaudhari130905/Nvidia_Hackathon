"""GitHub connect (OAuth with the repo scope) and export: a new repository holding the room's current files.

Tokens are stored encrypted (Fernet, GITHUB_TOKEN_ENCRYPTION_KEY) in the github_tokens table, so a restart keeps
them. An export creates a fresh repository and adds one commit on top of its first one; nothing is force-pushed.
"""

import asyncio
import base64
import logging
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mux.config import settings
from mux.db.tables import GithubToken

logger = logging.getLogger(__name__)

API = "https://api.github.com"
AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
SCOPES = "repo"
STATE_TTL_S = 600
TIMEOUT_S = 20.0
READY_TRIES = 5  # a repository created with auto_init can take a moment before its branch is readable


class GitHubError(Exception):
    """A GitHub call failed. `status` is the HTTP status the API route should answer with."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ExportResult:
    repo_url: str
    commit_sha: str
    files: int


@dataclass(frozen=True)
class _State:
    user_id: UUID
    next_path: str
    issued_at: float


class GitHub:
    """GitHub OAuth, token storage and export for every user of this server."""

    def __init__(
        self, session: Callable[[], AsyncSession], *, client_id: str, client_secret: str, redirect_uri: str,
        encryption_key: str, http: httpx.AsyncClient | None = None,
    ) -> None:
        self._session = session
        self.client_id = client_id
        self._client_secret = client_secret
        self.redirect_uri = redirect_uri
        if encryption_key:
            self._fernet = Fernet(encryption_key.encode())
        else:
            logger.warning("GITHUB_TOKEN_ENCRYPTION_KEY is not set: GitHub connections are lost on restart")
            self._fernet = Fernet(Fernet.generate_key())
        self._http = http or httpx.AsyncClient(timeout=TIMEOUT_S)
        self._states: dict[str, _State] = {}

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self._client_secret and self.redirect_uri)

    # ---- OAuth ----

    def authorize_url(self, user_id: UUID, next_path: str = "/profile") -> str:
        """The GitHub page that asks the user to connect. The state ties the callback to this user (single use)."""
        if not self.configured:
            raise GitHubError("GitHub export is not configured on this server", 503)
        self._prune()
        state = secrets.token_urlsafe(32)
        self._states[state] = _State(user_id, next_path, time.time())
        query = {"client_id": self.client_id, "redirect_uri": self.redirect_uri, "scope": SCOPES, "state": state}
        return f"{AUTHORIZE_URL}?{urlencode(query)}"

    def take_state(self, state: str) -> _State | None:
        """The user and return path a state was issued for; None if unknown, used or expired."""
        self._prune()
        return self._states.pop(state, None)

    def _prune(self) -> None:
        cutoff = time.time() - STATE_TTL_S
        for key in [k for k, s in self._states.items() if s.issued_at < cutoff]:
            del self._states[key]

    async def connect(self, user_id: UUID, code: str) -> None:
        """Trade the callback's code for a token and store it for the user."""
        r = await self._http.post(
            TOKEN_URL, headers={"Accept": "application/json"},
            data={"client_id": self.client_id, "client_secret": self._client_secret, "code": code,
                  "redirect_uri": self.redirect_uri},
        )
        body = r.json() if r.is_success else {}
        if "access_token" not in body:
            raise GitHubError(f"GitHub did not grant access ({body.get('error', r.status_code)})", 400)
        await self._save_token(user_id, body["access_token"], body.get("scope", ""))

    # ---- tokens ----

    async def _save_token(self, user_id: UUID, token: str, scopes: str) -> None:
        encrypted = self._fernet.encrypt(token.encode())
        stmt = insert(GithubToken).values(user_id=user_id, token_encrypted=encrypted, scopes=scopes)
        stmt = stmt.on_conflict_do_update(
            index_elements=[GithubToken.user_id], set_={"token_encrypted": encrypted, "scopes": scopes}
        )
        async with self._session() as session, session.begin():
            await session.execute(stmt)

    async def token(self, user_id: UUID) -> str | None:
        """The user's token; None if they never connected or it was encrypted with another key."""
        async with self._session() as session:
            row = await session.scalar(select(GithubToken).where(GithubToken.user_id == user_id))
        if row is None:
            return None
        try:
            return self._fernet.decrypt(row.token_encrypted).decode()
        except InvalidToken:
            return None

    async def status(self, user_id: UUID) -> dict[str, object]:
        """Whether the user is connected, and their GitHub login (a revoked token counts as not connected)."""
        token = await self.token(user_id)
        if token is None:
            return {"connected": False, "login": None}
        r = await self._http.get(f"{API}/user", headers=_headers(token))
        if not r.is_success:
            return {"connected": False, "login": None}
        return {"connected": True, "login": r.json().get("login")}

    # ---- export ----

    async def export(
        self, user_id: UUID, repo_name: str, *, private: bool, files: Mapping[str, bytes], message: str
    ) -> ExportResult:
        """Create `repo_name` under the user's account and commit `files` to its default branch."""
        token = await self.token(user_id)
        if token is None:
            raise GitHubError("Connect GitHub on your profile first", 409)
        if not files:
            raise GitHubError("The room has no files to export", 400)
        h = _headers(token)

        r = await self._http.post(
            f"{API}/user/repos", headers=h,
            json={"name": repo_name, "private": private, "auto_init": True, "description": "Built in MUX"},
        )
        if r.status_code == 422:
            raise GitHubError(f"You already have a repository named {repo_name}", 409)
        if r.status_code == 401:
            raise GitHubError("GitHub access was revoked: connect GitHub again", 409)
        _check(r, "create the repository")
        repo = r.json()
        full, branch = repo["full_name"], repo.get("default_branch") or "main"

        base_sha = await self._branch_head(h, full, branch)
        r = await self._http.get(f"{API}/repos/{full}/git/commits/{base_sha}", headers=h)
        _check(r, "read the first commit")
        base_tree = r.json()["tree"]["sha"]

        tree = []
        for path, content in sorted(files.items()):
            r = await self._http.post(
                f"{API}/repos/{full}/git/blobs", headers=h,
                json={"content": base64.b64encode(content).decode(), "encoding": "base64"},
            )
            _check(r, f"upload {path}")
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": r.json()["sha"]})

        r = await self._http.post(f"{API}/repos/{full}/git/trees", headers=h, json={"base_tree": base_tree, "tree": tree})
        _check(r, "create the tree")
        r = await self._http.post(
            f"{API}/repos/{full}/git/commits", headers=h,
            json={"message": message, "tree": r.json()["sha"], "parents": [base_sha]},
        )
        _check(r, "create the commit")
        commit = r.json()["sha"]
        # A fast-forward of the branch the repository was just created with: no force
        r = await self._http.patch(f"{API}/repos/{full}/git/refs/heads/{branch}", headers=h, json={"sha": commit})
        _check(r, "update the branch")
        return ExportResult(repo["html_url"], commit, len(files))

    async def _branch_head(self, h: dict[str, str], full: str, branch: str) -> str:
        for attempt in range(READY_TRIES):
            r = await self._http.get(f"{API}/repos/{full}/git/ref/heads/{branch}", headers=h)
            if r.is_success:
                return r.json()["object"]["sha"]
            if r.status_code not in (404, 409) or attempt == READY_TRIES - 1:
                _check(r, "read the new repository")
            await asyncio.sleep(0.5 * (attempt + 1))
        raise GitHubError("GitHub did not finish creating the repository")

    async def close(self) -> None:
        await self._http.aclose()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def _check(r: httpx.Response, what: str) -> None:
    if not r.is_success:
        logger.warning("GitHub could not %s: %s %s", what, r.status_code, r.text[:300])
        raise GitHubError(f"GitHub could not {what} ({r.status_code})")


_github: GitHub | None = None


def get_github(session: Callable[[], AsyncSession]) -> GitHub:
    """The process-wide GitHub client, made on first use from the settings."""
    global _github
    if _github is None:
        _github = GitHub(
            session, client_id=settings.github_client_id, client_secret=settings.github_client_secret,
            redirect_uri=settings.github_redirect_uri, encryption_key=settings.github_token_encryption_key,
        )
    return _github
