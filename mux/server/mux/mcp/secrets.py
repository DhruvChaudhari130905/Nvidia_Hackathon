"""Room MCP servers' header values (tokens) are stored encrypted with MCP_ENCRYPTION_KEY."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from mux.config import settings


class SecretsUnavailable(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = settings.mcp_encryption_key
    if not key:
        raise SecretsUnavailable("Set MCP_ENCRYPTION_KEY on the server to save MCP server tokens")
    try:
        return Fernet(key.encode())
    except ValueError as e:
        raise SecretsUnavailable("MCP_ENCRYPTION_KEY isn't a valid Fernet key") from e


def encrypt_headers(headers: dict[str, str]) -> dict[str, str]:
    if not headers:
        return {}
    f = _fernet()
    return {name: f.encrypt(value.encode()).decode() for name, value in headers.items()}


def decrypt_headers(headers: dict[str, str]) -> dict[str, str]:
    if not headers:
        return {}
    f = _fernet()
    try:
        return {name: f.decrypt(value.encode()).decode() for name, value in headers.items()}
    except InvalidToken as e:
        raise SecretsUnavailable("Saved MCP tokens can't be read with the current MCP_ENCRYPTION_KEY") from e
