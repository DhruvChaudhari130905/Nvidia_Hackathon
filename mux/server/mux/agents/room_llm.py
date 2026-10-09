"""The model a room's agents use: the room's own provider when its owner set one, else the server's."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from mux.agents.llm import LLM, LLMReply, ModelError, ModelRole, NoModel, OpenAILLM
from mux.secrets import SecretsUnavailable, decrypt_value

logger = logging.getLogger(__name__)

PROVIDERS = ("token_factory", "openai", "anthropic", "openrouter", "groq", "together", "custom")


def redact(text: str, secret: str) -> str:
    """`text` with `secret` (as typed, or as repr shows it) replaced by [hidden]."""
    if not secret:
        return text
    for form in {secret, repr(secret)[1:-1]}:
        text = text.replace(form, "[hidden]")
    return text


class RoomLLM:
    """Implements LLM for one room. Each call reads the room's current settings, so a change applies at once."""

    def __init__(self, actor: Any, default: Optional[LLM], *, make: Callable[..., Any] = OpenAILLM) -> None:
        self.actor = actor
        self.default = default
        self._make = make
        self._client: Any = None
        self._version: Optional[str] = None
        self._key = ""

    def available(self) -> bool:
        return self.actor.ai_settings is not None or self.default is not None

    def _room_client(self, ai: dict[str, Any]) -> Any:
        if self._client is None or self._version != ai["version"]:
            try:
                self._key = decrypt_value(ai["api_key"])
            except SecretsUnavailable as e:
                # Never fall back to the server's key: the owner chose to pay for this room themselves
                raise NoModel(f"can't read the room's API key ({e}); the owner can save it again") from e
            models = {ModelRole(role): model for role, model in ai["models"].items()}
            self._client = self._make(ai["base_url"], self._key, models, thinking=ai["provider"] == "token_factory")
            self._version = ai["version"]
        return self._client

    async def chat(self, role: ModelRole, messages: list[dict[str, Any]], **kwargs: Any) -> LLMReply:
        ai = self.actor.ai_settings
        if ai is not None:
            client, secret = self._room_client(ai), self._key
        elif self.default is not None:
            client, secret = self.default, ""
        else:
            raise NoModel("no AI model is set up for this room")
        try:
            return await client.chat(role, messages, **kwargs)
        except ModelError as e:
            raise ModelError(redact(str(e), secret)) from e
        except Exception as e:  # openai.APIError and transport errors
            raise ModelError(redact(f"{type(e).__name__}: {e}", secret)) from e


async def check_models(llm: Any, models: dict[ModelRole, str], secret: str) -> dict[str, str]:
    """One tiny request per distinct model id. Role -> error text (key hidden); empty when all work."""
    errors: dict[str, str] = {}
    tried: dict[str, Optional[str]] = {}
    for role, model in models.items():
        if model not in tried:
            try:
                await llm.chat(role, [{"role": "user", "content": "Reply with OK"}], max_tokens=5)
                tried[model] = None
            except Exception as e:
                tried[model] = redact(f"{type(e).__name__}: {e}", secret)[:300]
        error = tried[model]
        if error is not None:
            errors[role.value] = error
    return errors
