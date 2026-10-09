"""Verify Supabase JWTs. The browser uses Supabase for login only."""
import logging
import time
from typing import Optional, Dict, Any
import httpx
import jwt
from jwt import PyJWK, PyJWTError
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from mux.config import settings

logger = logging.getLogger(__name__)

class User:
    """Simple user model for authentication from Supabase JWT."""
    def __init__(self, id: str, email: Optional[str] = None, role: str = "authenticated", created_at: Optional[datetime] = None,
                 name: Optional[str] = None):
        self.id = id
        self.email = email
        self.role = role
        self.created_at = created_at
        self.name = name

    def __repr__(self):
        return f"User(id={self.id}, email={self.email}, role={self.role}, created_at={self.created_at})"

# Supabase JWT verification. Legacy projects sign with a shared secret (HS256);
# newer ones sign with asymmetric keys published at the project's JWKS endpoint.
SUPABASE_ALGORITHM = "HS256"
ASYMMETRIC_ALGORITHMS = ("ES256", "RS256")
JWKS_TTL_SECONDS = 600

_jwks_cache: Dict[str, Any] = {"url": None, "fetched_at": 0.0, "keys": []}


def _fetch_jwks(url: str) -> list:
    response = httpx.get(url, timeout=5)
    response.raise_for_status()
    return response.json().get("keys", [])


def _signing_key(kid: Optional[str]) -> Optional[Dict[str, Any]]:
    """The project's public key with this kid. Refetches when stale or when the kid is new (key rotation)."""
    url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"

    def find() -> Optional[Dict[str, Any]]:
        return next((k for k in _jwks_cache["keys"] if k.get("kid") == kid), None)

    fresh = _jwks_cache["url"] == url and time.monotonic() - _jwks_cache["fetched_at"] < JWKS_TTL_SECONDS
    key = find() if fresh else None
    if key is None:
        try:
            keys = _fetch_jwks(url)
        except (httpx.HTTPError, ValueError) as e:
            logger.warning(f"Could not fetch Supabase JWKS from {url}: {e}")
            return find() if _jwks_cache["url"] == url else None
        _jwks_cache.update(url=url, fetched_at=time.monotonic(), keys=keys)
        key = find()
    return key

def display_name(payload: Dict[str, Any]) -> Optional[str]:
    """The name to show for a Supabase user: their provider name, else the part of their email before the @."""
    metadata = payload.get("user_metadata") or {}
    for key in ("full_name", "name", "user_name", "preferred_username"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:100]
    email = payload.get("email")
    return email.split("@")[0] if isinstance(email, str) and "@" in email else None


# Security scheme
http_bearer = HTTPBearer(auto_error=False)


def verify_supabase_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Supabase JWT and return the payload if valid.

    Settings are read at call time so tests and config reloads take effect.
    Supabase access tokens carry ``aud: "authenticated"``. PyJWT rejects any token
    with an ``aud`` claim unless ``audience=`` is passed, so the audience is checked
    only when SUPABASE_JWT_AUDIENCE is configured.

    Args:
        token: The JWT token to verify

    Returns:
        Dict containing the token payload if valid, None otherwise
    """
    secret = settings.supabase_jwt_secret
    audience = settings.supabase_jwt_audience or None
    issuer = settings.supabase_jwt_issuer or None

    try:
        header = jwt.get_unverified_header(token)
    except PyJWTError as e:
        logger.warning(f"JWT header unreadable: {e}")
        return None
    alg = header.get("alg")

    if alg in ASYMMETRIC_ALGORITHMS and settings.supabase_url:
        key = _signing_key(header.get("kid"))
        if key is None or key.get("alg", alg) != alg:
            logger.warning("JWT signed with a key not in the project's JWKS")
            return None
        try:
            return jwt.decode(
                token,
                PyJWK(key, algorithm=alg).key,
                algorithms=[alg],
                audience=audience,
                issuer=issuer,
                options={"verify_exp": True, "verify_aud": audience is not None},
            )
        except PyJWTError as e:
            logger.warning(f"JWT verification failed: {e}")
            return None

    if not secret:
        # Unverified tokens only if explicitly allowed (local dev only)
        if settings.allow_unverified_tokens:
            logger.warning("Supabase JWT secret not set. Allowing unverified tokens (ALLOW_UNVERIFIED_TOKENS=true).")
            try:
                return jwt.decode(
                    token,
                    options={"verify_signature": False, "verify_aud": False, "verify_exp": True},
                )
            except PyJWTError as e:
                logger.warning(f"JWT decode failed: {e}")
                return None
        logger.error("Supabase JWT secret not set. Authentication will fail. Set SUPABASE_URL (JWKS keys), SUPABASE_JWT_SECRET, or ALLOW_UNVERIFIED_TOKENS=true for local dev.")
        return None

    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[SUPABASE_ALGORITHM],
            audience=audience,
            issuer=issuer,
            options={"verify_exp": True, "verify_aud": audience is not None},
        )
    except PyJWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer)
) -> User:
    """
    FastAPI dependency to get the current user from Supabase JWT.

    Args:
        credentials: HTTP Authorization credentials (Bearer token)

    Returns:
        User object representing the current user

    Raises:
        HTTPException: If token is missing, invalid, or user not found
    """
    if not credentials:
        logger.warning("Authentication attempt without credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = verify_supabase_token(token)

    if payload is None:
        logger.warning("Invalid or expired token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user information from Supabase JWT payload
    # Supabase JWT typically includes: sub (user ID), email, role, etc.
    user_id = payload.get("sub")
    email = payload.get("email")  # Can be None
    role = payload.get("role", "authenticated")

    if not user_id:
        logger.warning("Token missing user ID (sub claim)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract optional timestamps
    created_at = None
    if "iat" in payload:
        try:
            created_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        except Exception as e:
            logger.warning(f"Could not parse iat claim: {e}")

    # In a real implementation, you might fetch the user from your database
    # For now, we'll create a User object from the token data
    try:
        user = User(
            id=user_id,
            email=email,
            role=role,
            created_at=created_at,
            name=display_name(payload),
        )
        return user
    except Exception as e:
        logger.error(f"Could not process user information: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not process user information: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer)
) -> Optional[User]:
    """
    FastAPI dependency to get the current user from Supabase JWT (optional).
    Returns None if no valid token is provided, rather than raising an exception.

    Args:
        credentials: HTTP Authorization credentials (Bearer token)

    Returns:
        User object if valid token provided, None otherwise
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = verify_supabase_token(token)

    if payload is None:
        return None

    user_id = payload.get("sub")
    email = payload.get("email")
    role = payload.get("role", "authenticated")

    if not user_id:
        return None

    try:
        created_at = None
        if "iat" in payload:
            try:
                created_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
            except Exception:
                pass

        return User(
            id=user_id,
            email=email,
            role=role,
            created_at=created_at,
            name=display_name(payload),
        )
    except Exception:
        return None
