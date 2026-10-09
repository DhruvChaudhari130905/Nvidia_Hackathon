"""Stored secrets and URL checks shared by MCP servers and room AI providers."""

import pytest
from cryptography.fernet import Fernet

from mux.config import settings
from mux.secrets import SecretsUnavailable, decrypt_value, encrypt_value
from mux.urls import UrlNotAllowed, check_url


def test_single_values_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "room_secrets_key", Fernet.generate_key().decode())
    stored = encrypt_value("sk-secret")
    assert "sk-secret" not in stored and decrypt_value(stored) == "sk-secret"


def test_old_setting_names_still_work(monkeypatch):
    monkeypatch.setattr(settings, "room_secrets_key", "")
    monkeypatch.setattr(settings, "mcp_encryption_key", Fernet.generate_key().decode())
    assert decrypt_value(encrypt_value("x")) == "x"
    monkeypatch.setattr(settings, "allow_private_urls", False)
    monkeypatch.setattr(settings, "mcp_allow_private_urls", True)
    check_url("http://localhost:11434/v1")


def test_new_names_take_over(monkeypatch):
    monkeypatch.setattr(settings, "room_secrets_key", "")
    with pytest.raises(SecretsUnavailable):
        encrypt_value("x")
    monkeypatch.setattr(settings, "allow_private_urls", False)
    with pytest.raises(UrlNotAllowed):
        check_url("http://localhost:11434/v1")
