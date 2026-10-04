"""Verify Supabase JWTs. The browser uses Supabase for login only."""
import logging
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from mux.config import settings

logger = logging.getLogger(__name__)

class User:
    """Simple user model for authentication from Supabase JWT."""
    def __init__(self, id: str, email: Optional[str] = None, role: str = "authenticated", created_at: Optional[datetime] = None):
        self.id = id
        self.email = email
        self.role = role
        self.created_at = created_at

    def __repr__(self):
        return f"User(id={self.id}, email={self.email}, role={self.role}, created_at={self.created_at})"

# Supabase JWT verification
SUPABASE_ALGORITHM = "HS256"

# Security scheme
http_bearer = HTTPBearer(auto_error=False)


def verify_supabase_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Supabase JWT and return the payload if valid.

    Settings are read at call time so tests and config reloads take effect.
    Supabase access tokens carry ``aud: "authenticated"``. python-jose rejects any
    token with an ``aud`` claim unless ``audience=`` is passed, so the audience is
    checked only when SUPABASE_JWT_AUDIENCE is configured.

    Args:
        token: The JWT token to verify

    Returns:
        Dict containing the token payload if valid, None otherwise
    """
    secret = settings.supabase_jwt_secret
    audience = settings.supabase_jwt_audience or None
    issuer = settings.supabase_jwt_issuer or None

    if not secret:
        # Unverified tokens only if explicitly allowed (local dev only)
        if settings.allow_unverified_tokens:
            logger.warning("Supabase JWT secret not set. Allowing unverified tokens (ALLOW_UNVERIFIED_TOKENS=true).")
            try:
                return jwt.decode(
                    token,
                    key="",
                    options={"verify_signature": False, "verify_aud": False, "verify_exp": True},
                )
            except JWTError as e:
                logger.warning(f"JWT decode failed: {e}")
                return None
        logger.error("Supabase JWT secret not set. Authentication will fail. Set SUPABASE_JWT_SECRET or ALLOW_UNVERIFIED_TOKENS=true for local dev.")
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
    except JWTError as e:
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
            # Add other fields as needed from your User model
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
        )
    except Exception:
        return None


# Optional: Function to get Supabase client for server-side operations
def get_supabase_client():
    """
    Get a Supabase client for server-side operations.
    This would be used when the backend needs to interact with Supabase directly
    (e.g., for admin operations, database access, etc.).

    Returns:
        Supabase client instance
    """
    try:
        from supabase import create_client, Client

        supabase_url = settings.supabase_url
        supabase_key = settings.supabase_service_role_key  # Use service role for backend

        missing = []
        if not supabase_url:
            missing.append("SUPABASE_URL")
        if not supabase_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")

        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

        return create_client(supabase_url, supabase_key)
    except ImportError:
        logger.error("Supabase client not installed. Run: pip install supabase")
        raise RuntimeError("Supabase client not installed. Run: pip install supabase")
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        raise RuntimeError(f"Failed to create Supabase client: {e}")