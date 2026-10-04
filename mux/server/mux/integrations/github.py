"""GitHub OAuth connect, encrypted token storage, and pushing an export from a checkpoint manifest."""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from pydantic import BaseModel

from mux.config import settings

logger = logging.getLogger(__name__)

OAUTH_STATE_TTL_SECONDS = 600


class GitHubOAuthConfig(BaseModel):
    """GitHub OAuth configuration."""
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str] = ["repo", "user:email"]


class GitHubTokenData(BaseModel):
    """Stored GitHub token data."""
    access_token: str
    token_type: str = "bearer"
    scope: str = ""
    expires_at: Optional[float] = None
    refresh_token: Optional[str] = None


class GitHubUserInfo(BaseModel):
    """GitHub user information."""
    login: str
    id: int
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None


@dataclass
class GitHubExportResult:
    """Result of exporting to GitHub."""
    commit_sha: str
    html_url: str
    files_pushed: int


class GitHubIntegration:
    """Handles GitHub OAuth and repository operations."""

    def __init__(self, encryption_key: Optional[bytes] = None):
        """
        Initialize GitHub integration.

        Args:
            encryption_key: Fernet key for encrypting stored tokens.
                           If not provided, uses GITHUB_TOKEN_ENCRYPTION_KEY from settings
                           or generates a new one (not persistent across restarts).
        """
        self.config = self._load_config()
        self._fernet = self._init_fernet(encryption_key)
        self._token_store: dict[str, str] = {}  # user_id -> encrypted token; in-memory, replace with DB in production
        self._pending_states: dict[str, tuple[str, float]] = {}  # state -> (user_id, issued_at)

    def _load_config(self) -> GitHubOAuthConfig:
        """Load GitHub OAuth config from settings."""
        client_id = getattr(settings, "github_client_id", "") or os.getenv("GITHUB_CLIENT_ID", "")
        client_secret = getattr(settings, "github_client_secret", "") or os.getenv("GITHUB_CLIENT_SECRET", "")
        redirect_uri = getattr(settings, "github_redirect_uri", "") or os.getenv("GITHUB_REDIRECT_URI", "")

        if not client_id or not client_secret:
            logger.warning("GitHub OAuth not configured - set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET")

        return GitHubOAuthConfig(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )

    def _init_fernet(self, key: Optional[bytes]) -> Fernet:
        """Initialize Fernet for token encryption."""
        if key:
            return Fernet(key)

        # Try to get key from settings/env
        key_b64 = getattr(settings, "github_token_encryption_key", "") or os.getenv("GITHUB_TOKEN_ENCRYPTION_KEY", "")
        if key_b64:
            try:
                return Fernet(key_b64.encode())
            except Exception as e:
                logger.warning(f"Invalid encryption key: {e}")

        # Generate ephemeral key (tokens won't persist across restarts)
        logger.warning("No persistent encryption key - generating ephemeral key. Tokens will be lost on restart.")
        return Fernet(Fernet.generate_key())

    def _encrypt_token(self, token_data: GitHubTokenData) -> str:
        """Encrypt token data for storage."""
        data = token_data.model_dump_json().encode()
        return self._fernet.encrypt(data).decode()

    def _decrypt_token(self, encrypted: str) -> GitHubTokenData:
        """Decrypt token data from storage."""
        data = self._fernet.decrypt(encrypted.encode())
        return GitHubTokenData.model_validate_json(data)

    # =========================================================================
    # OAuth Flow
    # =========================================================================

    def get_authorization_url(self, user_id: str, state: Optional[str] = None) -> tuple[str, str]:
        """
        Generate GitHub OAuth authorization URL.

        Args:
            user_id: The user ID to associate with the OAuth flow.
            state: Optional state parameter (generated if not provided).

        Returns:
            Tuple of (authorization_url, state)
        """
        if not self.config.client_id:
            raise RuntimeError("GitHub OAuth not configured: missing client_id")

        if not state:
            state = secrets.token_urlsafe(32)

        # Remember which user started this flow; the callback looks it up by state
        self._prune_states()
        self._pending_states[state] = (user_id, time.time())

        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
            "allow_signup": "true",
        }

        url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
        return url, state

    def _prune_states(self) -> None:
        cutoff = time.time() - OAUTH_STATE_TTL_SECONDS
        for key in [k for k, (_, ts) in self._pending_states.items() if ts < cutoff]:
            del self._pending_states[key]

    def consume_state(self, state: str) -> Optional[str]:
        """Return the user id for a state issued by get_authorization_url (single use), or None."""
        self._prune_states()
        entry = self._pending_states.pop(state, None)
        return entry[0] if entry else None

    async def exchange_code_for_token(self, code: str, state: str) -> GitHubTokenData:
        """
        Exchange OAuth code for access token.

        Args:
            code: Authorization code from GitHub callback.
            state: State parameter from callback.

        Returns:
            GitHubTokenData with access token and metadata.
        """
        if not self.config.client_id or not self.config.client_secret:
            raise RuntimeError("GitHub OAuth not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "code": code,
                    "redirect_uri": self.config.redirect_uri,
                },
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

        if "error" in data:
            raise ValueError(f"GitHub OAuth error: {data['error']} - {data.get('error_description', '')}")

        token_data = GitHubTokenData(
            access_token=data["access_token"],
            token_type=data.get("token_type", "bearer"),
            scope=data.get("scope", ""),
            expires_at=time.time() + data.get("expires_in", 0) if data.get("expires_in") else None,
            refresh_token=data.get("refresh_token"),
        )
        return token_data

    async def get_user_info(self, access_token: str) -> GitHubUserInfo:
        """Fetch authenticated user's GitHub profile."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            # Also fetch email if not public (must stay inside the client's context)
            email = data.get("email")
            if not email:
                email_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
                    timeout=10.0,
                )
                if email_resp.is_success:
                    emails = email_resp.json()
                    primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
                    if primary:
                        email = primary.get("email")

        return GitHubUserInfo(
            login=data["login"],
            id=data["id"],
            email=email,
            name=data.get("name"),
            avatar_url=data.get("avatar_url"),
        )

    # =========================================================================
    # Token Storage
    # =========================================================================

    def store_token(self, user_id: str, token_data: GitHubTokenData) -> None:
        """Store encrypted token for a user."""
        encrypted = self._encrypt_token(token_data)
        self._token_store[user_id] = encrypted
        logger.info(f"Stored GitHub token for user {user_id}")

    def get_token(self, user_id: str) -> Optional[GitHubTokenData]:
        """Retrieve and decrypt token for a user."""
        encrypted = self._token_store.get(user_id)
        if not encrypted:
            return None
        try:
            return self._decrypt_token(encrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt token for user {user_id}: {e}")
            return None

    def delete_token(self, user_id: str) -> bool:
        """Delete stored token for a user."""
        if user_id in self._token_store:
            del self._token_store[user_id]
            return True
        return False

    def has_token(self, user_id: str) -> bool:
        """Check if user has a stored token."""
        return user_id in self._token_store

    def get_connection_status(self, user_id: str) -> dict:
        """Get GitHub connection status for a user."""
        token_data = self.get_token(user_id)
        if not token_data:
            return {"connected": False, "username": None, "scopes": []}

        # Token exists - optionally validate it's still good
        return {
            "connected": True,
            "username": None,  # Would need API call to get
            "scopes": token_data.scope.split(",") if token_data.scope else [],
            "expires_at": token_data.expires_at,
        }

    # =========================================================================
    # Repository Operations
    # =========================================================================

    async def _get_headers(self, access_token: str) -> dict:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def create_or_update_files(
        self,
        access_token: str,
        owner: str,
        repo: str,
        branch: str,
        files: dict[str, str],  # path -> content
        commit_message: str,
        path_prefix: str = "",
    ) -> GitHubExportResult:
        """
        Create or update multiple files in a repository in a single commit.

        Uses the GitHub Contents API with a commit tree.
        """
        headers = await self._get_headers(access_token)

        async with httpx.AsyncClient() as client:
            # 1. Get the latest commit SHA on the branch
            ref_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{branch}",
                headers=headers,
                timeout=10.0,
            )
            if ref_resp.status_code == 404:
                # Branch doesn't exist - create from default branch
                default_branch_resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}",
                    headers=headers,
                    timeout=10.0,
                )
                default_branch_resp.raise_for_status()
                default_branch = default_branch_resp.json()["default_branch"]

                ref_resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{default_branch}",
                    headers=headers,
                    timeout=10.0,
                )
                if ref_resp.status_code == 404:
                    raise ValueError(f"Repository {owner}/{repo} has no commits")

                # Create the new branch
                base_sha = ref_resp.json()["object"]["sha"]
                create_ref_resp = await client.post(
                    f"https://api.github.com/repos/{owner}/{repo}/git/refs",
                    headers=headers,
                    json={"ref": f"refs/heads/{branch}", "sha": base_sha},
                    timeout=10.0,
                )
                create_ref_resp.raise_for_status()
            else:
                ref_resp.raise_for_status()
                base_sha = ref_resp.json()["object"]["sha"]

            # 2. Get the base tree
            commit_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/git/commits/{base_sha}",
                headers=headers,
                timeout=10.0,
            )
            commit_resp.raise_for_status()
            base_tree_sha = commit_resp.json()["tree"]["sha"]

            # 3. Create blobs for each file
            tree_items = []
            for path, content in files.items():
                full_path = f"{path_prefix}{path}".lstrip("/")
                blob_resp = await client.post(
                    f"https://api.github.com/repos/{owner}/{repo}/git/blobs",
                    headers=headers,
                    json={"content": content, "encoding": "utf-8"},
                    timeout=10.0,
                )
                blob_resp.raise_for_status()
                blob_sha = blob_resp.json()["sha"]

                tree_items.append({
                    "path": full_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                })

            # 4. Create a new tree
            tree_resp = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/git/trees",
                headers=headers,
                json={"base_tree": base_tree_sha, "tree": tree_items},
                timeout=10.0,
            )
            tree_resp.raise_for_status()
            new_tree_sha = tree_resp.json()["sha"]

            # 5. Create a new commit
            commit_resp = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/git/commits",
                headers=headers,
                json={
                    "message": commit_message,
                    "tree": new_tree_sha,
                    "parents": [base_sha],
                },
                timeout=10.0,
            )
            commit_resp.raise_for_status()
            new_commit_sha = commit_resp.json()["sha"]

            # 6. Update the branch reference
            update_ref_resp = await client.patch(
                f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{branch}",
                headers=headers,
                json={"sha": new_commit_sha, "force": True},
                timeout=10.0,
            )
            update_ref_resp.raise_for_status()

            return GitHubExportResult(
                commit_sha=new_commit_sha,
                html_url=f"https://github.com/{owner}/{repo}/commit/{new_commit_sha}",
                files_pushed=len(files),
            )

    async def export_checkpoint(
        self,
        user_id: str,
        checkpoint_data: dict[str, Any],
        github_owner: str,
        github_repo: str,
        branch: str = "main",
        commit_message: Optional[str] = None,
        path_prefix: str = "",
    ) -> GitHubExportResult:
        """
        Export a checkpoint to a GitHub repository.

        Args:
            user_id: User initiating the export (must have stored token).
            checkpoint_data: Checkpoint manifest with 'files' and 'plan' keys.
            github_owner: GitHub username or organization.
            github_repo: Repository name.
            branch: Target branch.
            commit_message: Custom commit message.
            path_prefix: Path prefix in repo (e.g., 'mux-exports/').

        Returns:
            GitHubExportResult with commit info.
        """
        token_data = self.get_token(user_id)
        if not token_data:
            raise ValueError("No GitHub token stored for user. Connect GitHub first.")

        files = checkpoint_data.get("files", {})
        plan = checkpoint_data.get("plan", [])

        if not files and not plan:
            raise ValueError("Checkpoint has no files or plan to export")

        # Prepare files to push
        export_files = dict(files)

        # Add plan as a JSON file if present
        if plan:
            export_files["PLAN.json"] = json.dumps(plan, indent=2)

        # Default commit message
        if not commit_message:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            commit_message = f"MUX export: checkpoint from {ts}"

        return await self.create_or_update_files(
            access_token=token_data.access_token,
            owner=github_owner,
            repo=github_repo,
            branch=branch,
            files=export_files,
            commit_message=commit_message,
            path_prefix=path_prefix,
        )


# Global instance (initialized on first use)
_github_integration: Optional[GitHubIntegration] = None


def get_github_integration() -> GitHubIntegration:
    """Get or create the global GitHub integration instance."""
    global _github_integration
    if _github_integration is None:
        _github_integration = GitHubIntegration()
    return _github_integration