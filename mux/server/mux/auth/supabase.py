"""Checks Supabase access tokens. The browser signs in with Supabase; the server only verifies its JWTs.

Supabase signs access tokens either with the project's legacy shared secret (HS256, SUPABASE_JWT_SECRET) or with
its asymmetric signing keys (ES256 or RS256), whose public keys are served at
SUPABASE_URL/auth/v1/.well-known/jwks.json. Both are accepted; each only when it is configured.
"""

import logging
from functools import lru_cache
from typing import Any

import jwt
from fastapi.security import HTTPBearer

from mux.config import settings

logger = logging.getLogger(__name__)

http_bearer = HTTPBearer(auto_error=False)

ASYMMETRIC = ("ES256", "RS256")
JWKS_CACHE_S = 600


@lru_cache(maxsize=4)
def _jwks(url: str) -> jwt.PyJWKClient:
    """The project's public keys, fetched on first use and cached for ten minutes."""
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=JWKS_CACHE_S, timeout=5)


def _issuer() -> str | None:
    if settings.supabase_jwt_issuer:
        return settings.supabase_jwt_issuer
    return f"{settings.supabase_url.rstrip('/')}/auth/v1" if settings.supabase_url else None


def unverified_allowed() -> bool:
    """Skipping the signature check needs both ALLOW_UNVERIFIED_TOKENS and DEBUG, so one stray flag in a
    production .env cannot turn authentication off."""
    return settings.allow_unverified_tokens and settings.debug


def verify_supabase_token(token: str) -> dict[str, Any] | None:
    """The token's claims if Supabase signed it and it has not expired, else None.

    The audience is checked when SUPABASE_JWT_AUDIENCE is set ("authenticated" by default), the issuer when
    SUPABASE_URL or SUPABASE_JWT_ISSUER is set.
    """
    try:
        alg = jwt.get_unverified_header(token).get("alg")
    except jwt.PyJWTError:
        return None

    if unverified_allowed():
        try:
            return jwt.decode(token, options={"verify_signature": False, "require": ["exp", "sub"]})
        except jwt.PyJWTError:
            return None

    try:
        if alg == "HS256" and settings.supabase_jwt_secret:
            key: Any = settings.supabase_jwt_secret
        elif alg in ASYMMETRIC and settings.supabase_url:
            jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            key = _jwks(jwks_url).get_signing_key_from_jwt(token).key
        else:
            return None  # an algorithm this server has no key for (or "none")
        audience = settings.supabase_jwt_audience or None
        return jwt.decode(
            token, key, algorithms=[alg], audience=audience, issuer=_issuer(),
            options={"require": ["exp", "sub"], "verify_aud": audience is not None},
        )
    except jwt.PyJWTError as e:
        logger.info("Rejected a token: %s", e)
        return None
