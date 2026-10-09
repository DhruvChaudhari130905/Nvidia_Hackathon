"""Room secrets (MCP server tokens, room AI provider keys), stored encrypted with ROOM_SECRETS_KEY."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from mux.config import settings


class SecretsUnavailable(RuntimeError):
    pass


def _fernet() -> MultiFernet:
    """Encrypts with ROOM_SECRETS_KEY (else the old MCP_ENCRYPTION_KEY) and decrypts with either, so values
    saved under the old key still read after the new one is set."""
    keys = [k for k in (settings.room_secrets_key, settings.mcp_encryption_key) if k]
    if not keys:
        raise SecretsUnavailable("Set ROOM_SECRETS_KEY on the server to save keys and tokens")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except ValueError as e:
        raise SecretsUnavailable("ROOM_SECRETS_KEY isn't a valid Fernet key") from e


def encrypt_value(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as e:
        raise SecretsUnavailable("Saved keys can't be read with the current ROOM_SECRETS_KEY") from e


def encrypt_values(values: dict[str, str]) -> dict[str, str]:
    return {name: encrypt_value(value) for name, value in values.items()} if values else {}


def decrypt_values(values: dict[str, str]) -> dict[str, str]:
    return {name: decrypt_value(value) for name, value in values.items()} if values else {}
