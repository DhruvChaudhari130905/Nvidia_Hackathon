# Room AI Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A room's owner sets an OpenAI-compatible provider, their API key and a model per agent role; the room's agents use it, and rooms without one use the server's Token Factory key.

**Architecture:** `TokenFactoryLLM` becomes a general `OpenAILLM`. A per-room `RoomLLM` implements the existing `LLM` protocol and, on every call, uses the room's saved settings (a room event, key encrypted) or the server's default client. The coordinator and coder are unchanged; the runtime skips agent work when no model is available and posts throttled `ai.error` notices when the model fails. The encryption and URL-check modules move out of `mux/mcp/` so both features share them.

**Tech Stack:** Python 3.11+ / FastAPI / pydantic-settings, `openai` (AsyncOpenAI), `cryptography` Fernet; Next.js 15 / React / TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-09-room-ai-provider-design.md`

## Global Constraints

- Run backend commands from `mux/server` with `.venv/bin/python -m pytest`.
- Roles: `lightning`, `super`, `ultra` (`ModelRole` values). Lightning = coordinator, Super = coder, Ultra = coder's escalation.
- Provider labels, exactly: `token_factory`, `openai`, `anthropic`, `openrouter`, `groq`, `together`, `custom`. Only `token_factory` sends `chat_template_kwargs.enable_thinking`.
- Model ids: 1–200 chars, no whitespace. API key: 1–500 chars, visible ASCII (`\x21`–`\x7e`). Base URL: https and public unless `ALLOW_PRIVATE_URLS=true`.
- New settings `ROOM_SECRETS_KEY` and `ALLOW_PRIVATE_URLS`; the old `MCP_ENCRYPTION_KEY` / `MCP_ALLOW_PRIVATE_URLS` still work when the new ones are empty/false.
- The API key never appears in an API response, a socket payload, a log line or a feed notice (replaced by `[hidden]` in error text).
- `ai.error` notices: at most one per 60 s per room.
- No model at all (no room settings, no server default): no agent work and no notices.

## Review Focus

- **A provider error message that echoes the key** (some providers repeat it in 401 bodies): every error shown to the room or returned by the API has the key replaced. Test in Task 2 (`RoomLLM` wraps errors) and Task 4 (check errors).
- **The secrets key changes after a room saved its key**: the room's agents must not crash or fall back silently to the server's paid key; they report `ai.error` "can't read the room's API key". Test in Task 2.
- **The owner re-saves with the key field empty**: the saved key is kept and checked again, not replaced by an empty key. Test in Task 4.
- **A room whose settings change while the coordinator is mid-call**: the next call uses the new settings; the in-flight one finishes with the old client. Test in Task 2 (cache refresh after a new save).
- **Rooms on a server with no Token Factory key and no room key**: messages and approved tasks do nothing (as today) and produce no error spam; saving a key then starts approved tasks. Test in Task 5.

---

## File Structure

| File | Responsibility |
|---|---|
| `mux/server/mux/secrets.py` (moved from `mux/mcp/secrets.py`) | Fernet encrypt/decrypt of stored values |
| `mux/server/mux/urls.py` (moved from `mux/mcp/urls.py`) | public-https URL check |
| `mux/server/mux/config.py` | `room_secrets_key`, `allow_private_urls` |
| `mux/server/mux/agents/llm.py` | `OpenAILLM`, `TokenFactoryLLM()` factory, `ModelError`, `NoModel` |
| `mux/server/mux/agents/room_llm.py` | `RoomLLM`, `check_models`, `redact` |
| `mux/server/mux/events/models.py`, `events/wire.py`, `rooms/actor.py` | AI settings events and room state |
| `mux/server/mux/api/ai.py`, `main.py` | REST API; factory always builds runtimes |
| `mux/server/mux/rooms/runtime.py` | skip without a model, wake on save, `ai.error` |
| `mux/web/src/types/index.ts`, `lib/api.ts`, `lib/reducer.ts`, `components/room/AiModelDialog.tsx`, `components/room/TopBar.tsx` | UI |
| `mux/server/.env.example`, `docs/03-getting-started.md` | docs |

---

### Task 1: Shared secrets and URL modules, new setting names

**Files:**
- Move: `mux/server/mux/mcp/secrets.py` → `mux/server/mux/secrets.py`; `mux/server/mux/mcp/urls.py` → `mux/server/mux/urls.py`
- Modify: `mux/server/mux/config.py`, `mux/server/mux/mcp/catalog.py`, `mux/server/mux/mcp/toolset.py`, `mux/server/mux/api/mcp.py`, `mux/server/mux/events/models.py:233` (description only)
- Modify tests: `tests/test_mcp_config.py`, `tests/test_mcp_toolset.py`, `tests/test_mcp_http.py`, `tests/test_api.py`, `tests/conftest.py`
- Test: `mux/server/tests/test_secrets.py`

**Interfaces:**
- Produces: `mux.secrets.SecretsUnavailable`, `encrypt_values(values: dict[str, str]) -> dict[str, str]`, `decrypt_values(values: dict[str, str]) -> dict[str, str]`, `encrypt_value(value: str) -> str`, `decrypt_value(value: str) -> str`; `mux.urls.UrlNotAllowed`, `check_url(url)`, `async check_url_async(url)`; `settings.room_secrets_key: str`, `settings.allow_private_urls: bool`.

- [ ] **Step 1: Move the modules and point imports at them**

```bash
cd mux/server
git mv mux/mcp/secrets.py mux/secrets.py
git mv mux/mcp/urls.py mux/urls.py
sed -i '' 's/from mux\.mcp\.secrets import/from mux.secrets import/; s/from mux\.mcp\.urls import/from mux.urls import/' \
  mux/mcp/catalog.py mux/mcp/toolset.py mux/api/mcp.py tests/test_mcp_config.py
sed -i '' 's/encrypt_headers/encrypt_values/g; s/decrypt_headers/decrypt_values/g' \
  mux/secrets.py mux/mcp/catalog.py mux/api/mcp.py tests/test_mcp_config.py
sed -i '' 's#(mux/mcp/secrets.py)#(mux/secrets.py)#' mux/events/models.py
sed -i '' 's/"mcp_encryption_key"/"room_secrets_key"/g; s/"mcp_allow_private_urls"/"allow_private_urls"/g' \
  tests/test_mcp_config.py tests/test_mcp_toolset.py tests/test_mcp_http.py tests/test_api.py
```

In `tests/conftest.py`, after the `SERVER_DIR = ...` line, add an autouse fixture so a developer's `.env` can't leak the old names into tests that patch the new ones:

```python


@pytest.fixture(autouse=True)
def _no_legacy_secret_settings(monkeypatch):
    """Tests set ROOM_SECRETS_KEY / ALLOW_PRIVATE_URLS; the old names (still read as fallbacks) start empty."""
    monkeypatch.setattr(settings, "mcp_encryption_key", "")
    monkeypatch.setattr(settings, "mcp_allow_private_urls", False)
```

- [ ] **Step 2: Write the failing test**

Create `mux/server/tests/test_secrets.py`:

```python
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
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_secrets.py -q`
Expected: FAIL with `ImportError: cannot import name 'decrypt_value'`

- [ ] **Step 4: Implement**

In `mux/server/mux/config.py`, replace the MCP settings block (the comment lines and the three `mcp_*` fields) with:

```python
    # Room secrets (MCP server tokens, room AI keys) are encrypted with room_secrets_key (a Fernet key).
    # allow_private_urls lets rooms use http:// and private-network addresses: local development only.
    # The mcp_* names are the old ones, still read when the new ones are empty/false.
    room_secrets_key: str = ""
    allow_private_urls: bool = False
    mcp_config_path: str = "mcp.json"
    mcp_encryption_key: str = ""
    mcp_allow_private_urls: bool = False
```

Replace `mux/server/mux/secrets.py` with:

```python
"""Room secrets (MCP server tokens, room AI provider keys), stored encrypted with ROOM_SECRETS_KEY."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from mux.config import settings


class SecretsUnavailable(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = settings.room_secrets_key or settings.mcp_encryption_key
    if not key:
        raise SecretsUnavailable("Set ROOM_SECRETS_KEY on the server to save keys and tokens")
    try:
        return Fernet(key.encode())
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
```

In `mux/server/mux/urls.py`, change `if settings.mcp_allow_private_urls:` to `if settings.allow_private_urls or settings.mcp_allow_private_urls:` and the docstring line `MCP_ALLOW_PRIVATE_URLS=true (local development) allows http and private addresses.` to `ALLOW_PRIVATE_URLS=true (local development) allows http and private addresses.`

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd mux/server && .venv/bin/python -m pytest -q`
Expected: all pass (306 before + 3 new = 309). The `test_headers_need_a_key` assertion on the message may need `"ROOM_SECRETS_KEY"`; if a test asserted `"MCP_ENCRYPTION_KEY"` / `"SUPABASE"` text, `grep -n "MCP_ENCRYPTION_KEY" tests/` and update the expected text only.

- [ ] **Step 6: Commit**

```bash
git add -A mux/server/mux/secrets.py mux/server/mux/urls.py mux/server/mux/mcp mux/server/mux/api/mcp.py mux/server/mux/config.py mux/server/mux/events/models.py mux/server/tests
git commit -m "Share room secret storage and URL checks between MCP and AI providers"
```

---

### Task 2: `OpenAILLM`, `RoomLLM` and model checks

**Files:**
- Modify: `mux/server/mux/agents/llm.py:1` (docstring), `:59-72` (`TokenFactoryLLM` class → `OpenAILLM`), `:86-88` (thinking)
- Create: `mux/server/mux/agents/room_llm.py`
- Test: `mux/server/tests/test_room_llm.py`

**Interfaces:**
- Consumes: `mux.secrets.decrypt_value`, `SecretsUnavailable` (T1).
- Produces: `llm.OpenAILLM(base_url: str, api_key: str, models: dict[ModelRole, str], *, thinking: bool = False, client: Any = None)` with `async chat(...)` (same signature as before); `llm.TokenFactoryLLM() -> OpenAILLM`; `llm.ModelError(Exception)`; `llm.NoModel(ModelError)`; `room_llm.PROVIDERS: tuple[str, ...]`; `room_llm.redact(text: str, secret: str) -> str`; `room_llm.RoomLLM(actor, default: OpenAILLM | None, *, make: Callable[..., OpenAILLM] = OpenAILLM)` with `available() -> bool` and `async chat(...)`; `async room_llm.check_models(llm: LLM, models: dict[ModelRole, str], secret: str) -> dict[str, str]` (role value → error text; empty dict when all pass). Actor attribute read: `actor.ai_settings: dict | None` with keys `provider, base_url, api_key (encrypted), models {lightning, super, ultra}, version`.

- [ ] **Step 1: Write the failing tests**

Create `mux/server/tests/test_room_llm.py`:

```python
"""Which model a room's agents use: the room's own provider, else the server's."""

from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.fernet import Fernet

from mux.agents.llm import LLMReply, ModelError, ModelRole, NoModel, OpenAILLM, Usage
from mux.agents.room_llm import RoomLLM, check_models, redact
from mux.config import settings
from mux.secrets import encrypt_value

MODELS = {"lightning": "fast-1", "super": "smart-1", "ultra": "smart-1"}


class FakeCompletions:
    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = fail

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.fail:
            raise self.fail
        message = SimpleNamespace(content="OK", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1))


def fake_client(fail: Exception | None = None) -> Any:
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(fail)))


class Recorder:
    """Stands in for OpenAILLM: records what it was built with and answers every call."""
    built: list[tuple[str, str, dict, bool]] = []

    def __init__(self, base_url: str, api_key: str, models: dict, *, thinking: bool = False) -> None:
        Recorder.built.append((base_url, api_key, {r.value: m for r, m in models.items()}, thinking))
        self.api_key = api_key

    async def chat(self, role: ModelRole, messages: list, **kw: Any) -> LLMReply:
        if self.api_key == "sk-bad":
            raise ModelError("401 invalid key sk-bad")
        return LLMReply(text=f"room:{role.value}", model="m", usage=Usage(1, 1))


class Default:
    async def chat(self, role: ModelRole, messages: list, **kw: Any) -> LLMReply:
        return LLMReply(text="server", model="m", usage=Usage(1, 1))


@pytest.fixture
def secrets_key(monkeypatch):
    monkeypatch.setattr(settings, "room_secrets_key", Fernet.generate_key().decode())
    Recorder.built = []


def room(settings_: dict | None) -> Any:
    return SimpleNamespace(ai_settings=settings_, room_id="room_x")


def saved(key: str = "sk-room", version: str = "v1", provider: str = "openai") -> dict:
    return {"provider": provider, "base_url": "https://api.example.com/v1", "api_key": encrypt_value(key),
            "models": MODELS, "version": version}


async def test_room_settings_win_over_the_server(secrets_key):
    llm = RoomLLM(room(saved()), Default(), make=Recorder)  # type: ignore[arg-type]
    assert llm.available()
    assert (await llm.chat(ModelRole.SUPER, [])).text == "room:super"
    assert Recorder.built == [("https://api.example.com/v1", "sk-room", MODELS, False)]


async def test_server_default_and_no_model(secrets_key):
    assert (await RoomLLM(room(None), Default()).chat(ModelRole.SUPER, [])).text == "server"  # type: ignore[arg-type]
    none = RoomLLM(room(None), None)
    assert not none.available()
    with pytest.raises(NoModel):
        await none.chat(ModelRole.SUPER, [])


async def test_client_is_rebuilt_only_when_settings_change(secrets_key):
    actor = room(saved(version="v1"))
    llm = RoomLLM(actor, None, make=Recorder)
    await llm.chat(ModelRole.SUPER, [])
    await llm.chat(ModelRole.LIGHTNING, [])
    actor.ai_settings = saved(key="sk-new", version="v2")
    await llm.chat(ModelRole.SUPER, [])
    assert [b[1] for b in Recorder.built] == ["sk-room", "sk-new"]


async def test_token_factory_gets_thinking(secrets_key):
    llm = RoomLLM(room(saved(provider="token_factory")), None, make=Recorder)
    await llm.chat(ModelRole.SUPER, [])
    assert Recorder.built[0][3] is True


async def test_errors_hide_the_key(secrets_key):
    llm = RoomLLM(room(saved(key="sk-bad")), Default(), make=Recorder)  # type: ignore[arg-type]
    with pytest.raises(ModelError) as caught:
        await llm.chat(ModelRole.SUPER, [])
    assert "sk-bad" not in str(caught.value) and "[hidden]" in str(caught.value)


async def test_unreadable_key_never_falls_back_to_the_server(secrets_key, monkeypatch):
    actor = room(saved())
    monkeypatch.setattr(settings, "room_secrets_key", Fernet.generate_key().decode())
    llm = RoomLLM(actor, Default(), make=Recorder)  # type: ignore[arg-type]
    with pytest.raises(NoModel, match="can't read"):
        await llm.chat(ModelRole.SUPER, [])


async def test_openai_llm_sends_thinking_only_when_asked():
    plain = OpenAILLM("https://x/v1", "k", {ModelRole.SUPER: "m"}, client=fake_client())
    await plain.chat(ModelRole.SUPER, [], reasoning=True)
    thinking = OpenAILLM("https://x/v1", "k", {ModelRole.SUPER: "m"}, thinking=True, client=fake_client())
    await thinking.chat(ModelRole.SUPER, [], reasoning=True)
    assert "extra_body" not in plain._client.chat.completions.calls[0]
    assert thinking._client.chat.completions.calls[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}


async def test_check_models_tries_each_distinct_model_once():
    llm = OpenAILLM("https://x/v1", "k", {ModelRole(r): m for r, m in MODELS.items()}, client=fake_client())
    assert await check_models(llm, {ModelRole(r): m for r, m in MODELS.items()}, "k") == {}
    assert [c["model"] for c in llm._client.chat.completions.calls] == ["fast-1", "smart-1"]


async def test_check_models_reports_per_role_with_the_key_hidden():
    failing = OpenAILLM("https://x/v1", "sk-1", {ModelRole(r): m for r, m in MODELS.items()},
                        client=fake_client(RuntimeError("401 Incorrect API key: sk-1")))
    errors = await check_models(failing, {ModelRole(r): m for r, m in MODELS.items()}, "sk-1")
    assert set(errors) == {"lightning", "super", "ultra"}
    assert all("sk-1" not in e and "[hidden]" in e for e in errors.values())


def test_redact():
    assert redact("key sk-1 and 'sk-1'", "sk-1") == "key [hidden] and '[hidden]'"
    assert redact("nothing", "") == "nothing"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_room_llm.py -q`
Expected: FAIL with `ImportError: cannot import name 'ModelError'`

- [ ] **Step 3: Generalise the client in `llm.py`**

Change the module docstring to `"""OpenAI-compatible model client (Token Factory by default). Model selection, reasoning on/off, usage tracking."""`.

Replace:

```python
class TokenFactoryLLM:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url = settings.token_factory_base_url,
            api_key = settings.token_factory_api_key,
            max_retries =3,
            timeout = 120,
        )
        self._models = {
            ModelRole.LIGHTNING: settings.model_lightning,
            ModelRole.SUPER: settings.model_super,
            ModelRole.ULTRA: settings.model_ultra,
        }
```

with:

```python
class ModelError(Exception):
    """A model call failed (bad key, unknown model, rate limit, provider down). The text is safe to show."""


class NoModel(ModelError):
    """The room has no model to use."""


class OpenAILLM:
    """Any OpenAI-compatible chat completions API. `thinking` sends Nemotron's switch (Token Factory only)."""

    def __init__(self, base_url: str, api_key: str, models: dict[ModelRole, str], *, thinking: bool = False,
                 client: Any = None) -> None:
        self._client = client or AsyncOpenAI(base_url=base_url, api_key=api_key, max_retries=3, timeout=120)
        self._models = models
        self._thinking = thinking
```

and after the class (before `def _usage`) add:

```python
def TokenFactoryLLM() -> OpenAILLM:
    """The server's own model client, from the TOKEN_FACTORY_* and MODEL_* settings."""
    return OpenAILLM(
        settings.token_factory_base_url, settings.token_factory_api_key,
        {ModelRole.LIGHTNING: settings.model_lightning, ModelRole.SUPER: settings.model_super,
         ModelRole.ULTRA: settings.model_ultra},
        thinking=True,
    )
```

In `chat`, change `if reasoning is not None:` to `if reasoning is not None and self._thinking:`.

- [ ] **Step 4: Implement `RoomLLM` and `check_models`**

Create `mux/server/mux/agents/room_llm.py`:

```python
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
        if tried[model] is not None:
            errors[role.value] = tried[model]  # type: ignore[assignment]
    return errors
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_room_llm.py -q && .venv/bin/python -m pytest -q`
Expected: `10 passed`, then the full suite passes.

- [ ] **Step 6: Commit**

```bash
git add mux/server/mux/agents/llm.py mux/server/mux/agents/room_llm.py mux/server/tests/test_room_llm.py
git commit -m "Add per-room model selection over any OpenAI-compatible provider"
```

---

### Task 3: Room AI settings as room events

**Files:**
- Modify: `mux/server/mux/events/models.py` (EventType after `ROOM_MCP_ADMIN_TOGGLED`; classes after `RoomMcpAdminToggledEvent`; `Event` union; `__all__`)
- Modify: `mux/server/mux/events/wire.py` (imports; `_payload` after the MCP branches)
- Modify: `mux/server/mux/rooms/actor.py` (imports; `__init__`; methods after `set_mcp_admin`; replay after the MCP branches)
- Modify: `mux/web/src/types/index.ts` (event-type union: `'ai.changed'`, `'ai.error'`)
- Test: `mux/server/tests/test_room_ai.py`

**Interfaces:**
- Produces: events `RoomAiSettingsSavedEvent(provider, base_url, api_key, models)` / `RoomAiSettingsClearedEvent()`; `actor.ai_settings: dict | None` (`provider, base_url, api_key, models, version` where `version = str(event.id)`); `async actor.save_ai_settings(provider, base_url, api_key_encrypted, models: dict[str, str], user_id)`; `async actor.clear_ai_settings(user_id) -> bool`; wire type `ai.changed`.

- [ ] **Step 1: Write the failing test**

Create `mux/server/tests/test_room_ai.py`:

```python
"""Room AI settings survive restarts and never send the key to browsers."""

import json

import pytest

import mux.rooms.registry as room_registry
from mux.events.log import InMemoryEventLog
from mux.events.wire import to_envelope
from mux.rooms.registry import RoomRegistry

MODELS = {"lightning": "fast-1", "super": "smart-1", "ultra": "smart-2"}


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logs: dict[str, InMemoryEventLog] = {}
    monkeypatch.setattr(room_registry, "get_event_log", lambda rid: logs.setdefault(rid, InMemoryEventLog(rid)))
    return RoomRegistry(), logs


async def test_ai_settings_replay_and_stay_off_the_wire(registry):
    reg, logs = registry
    actor = await reg.create_room("room_ai1", "alice", name="Docs")
    assert actor.ai_settings is None
    await actor.save_ai_settings("openai", "https://api.openai.com/v1", "ENCRYPTED-KEY", MODELS, "alice")
    first = actor.ai_settings
    assert first is not None and first["models"] == MODELS and first["version"]

    wire = json.dumps([to_envelope(e) for e in logs["room_ai1"]._events])
    assert "ENCRYPTED-KEY" not in wire and '"has_key": true' in wire

    await reg.stop_room("room_ai1")
    again = await reg.get_room_or_rehydrate("room_ai1")
    assert again is not None and again.ai_settings == first
    assert await again.clear_ai_settings("alice") is True
    assert again.ai_settings is None and await again.clear_ai_settings("alice") is False
    await reg.shutdown_all()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_room_ai.py -q`
Expected: FAIL with `AttributeError: 'RoomActor' object has no attribute 'ai_settings'`

- [ ] **Step 3: Events**

In `mux/server/mux/events/models.py`, in `EventType` after `ROOM_MCP_ADMIN_TOGGLED = "room_mcp_admin_toggled"`:

```python
    ROOM_AI_SETTINGS_SAVED = "room_ai_settings_saved"
    ROOM_AI_SETTINGS_CLEARED = "room_ai_settings_cleared"
```

After the `RoomMcpAdminToggledEvent` class:

```python


class RoomAiSettingsSavedEvent(BaseEvent):
    """The owner set the room's AI provider. The key is encrypted (mux/secrets.py) and never sent to clients."""
    type: EventType = EventType.ROOM_AI_SETTINGS_SAVED
    provider: str = Field(..., description="Preset label (mux/agents/room_llm.py PROVIDERS)")
    base_url: str = Field(..., description="OpenAI-compatible API base URL")
    api_key: str = Field(..., description="Encrypted API key")
    models: Dict[str, str] = Field(..., description="Role (lightning, super, ultra) -> model id")


class RoomAiSettingsClearedEvent(BaseEvent):
    """The owner switched the room back to the server's model."""
    type: EventType = EventType.ROOM_AI_SETTINGS_CLEARED
```

Add `RoomAiSettingsSavedEvent,` and `RoomAiSettingsClearedEvent,` to the `Event` union after `RoomMcpAdminToggledEvent,`, and the two names as strings to `__all__` after `"RoomMcpAdminToggledEvent",`.

- [ ] **Step 4: Wire format**

In `mux/server/mux/events/wire.py` add `RoomAiSettingsSavedEvent,` to the models import (alphabetical), and before `# Invites (room_invite_*) aren't sent`:

```python
    if t == EventType.ROOM_AI_SETTINGS_SAVED:
        e = cast(RoomAiSettingsSavedEvent, event)
        return "ai.changed", {"provider": e.provider, "base_url": e.base_url, "models": e.models, "has_key": True}
    if t == EventType.ROOM_AI_SETTINGS_CLEARED:
        return "ai.changed", {"cleared": True}
```

In `mux/web/src/types/index.ts`, after `| 'mcp.unavailable'` add:

```ts
  | 'ai.changed'
  | 'ai.error'
```

- [ ] **Step 5: Actor**

In `mux/server/mux/rooms/actor.py` add to the models import after `RoomMcpAdminToggledEvent,`:

```python
    RoomAiSettingsSavedEvent,
    RoomAiSettingsClearedEvent,
```

In `__init__`, after `self.mcp_admin: dict[str, dict[str, Any]] = {}`:

```python
        # The room's own AI provider (mux/agents/room_llm.py): provider, base_url, encrypted api_key, models,
        # version (the saving event's id, so clients are rebuilt when it changes). None: the server's model.
        self.ai_settings: Optional[dict[str, Any]] = None
```

After `set_mcp_admin`:

```python

    async def save_ai_settings(self, provider: str, base_url: str, api_key: str, models: dict[str, str],
                               user_id: str) -> None:
        """Set the room's AI provider. `api_key` must already be encrypted."""
        async with self._lock:
            event = RoomAiSettingsSavedEvent(
                **self._event_fields(user_id), provider=provider, base_url=base_url, api_key=api_key, models=models,
            )
            self.ai_settings = {"provider": provider, "base_url": base_url, "api_key": api_key, "models": models,
                                "version": str(event.id)}
            await self._emit(event)

    async def clear_ai_settings(self, user_id: str) -> bool:
        async with self._lock:
            if self.ai_settings is None:
                return False
            self.ai_settings = None
            await self._emit(RoomAiSettingsClearedEvent(**self._event_fields(user_id)))
            return True
```

In the replay method after the `ROOM_MCP_ADMIN_TOGGLED` branch:

```python
            elif t == EventType.ROOM_AI_SETTINGS_SAVED:
                e = cast(RoomAiSettingsSavedEvent, event)
                self.ai_settings = {"provider": e.provider, "base_url": e.base_url, "api_key": e.api_key,
                                    "models": e.models, "version": str(e.id)}
            elif t == EventType.ROOM_AI_SETTINGS_CLEARED:
                self.ai_settings = None
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_room_ai.py tests/test_api.py -q`
Expected: all pass (the catalog-type test in `test_api.py` passes because the web union now has `ai.changed`).

- [ ] **Step 7: Commit**

```bash
git add mux/server/mux/events/models.py mux/server/mux/events/wire.py mux/server/mux/rooms/actor.py mux/server/tests/test_room_ai.py mux/web/src/types/index.ts
git commit -m "Keep each room's AI provider settings as room events"
```

---

### Task 4: REST API

**Files:**
- Create: `mux/server/mux/api/ai.py`
- Modify: `mux/server/mux/main.py` (import list on line 10; mount after the MCP router)
- Test: `mux/server/tests/test_api.py` (append)

**Interfaces:**
- Consumes: `encrypt_value`, `decrypt_value`, `SecretsUnavailable` (T1); `check_url_async`, `UrlNotAllowed` (T1); `OpenAILLM`, `ModelRole` (T2); `room_llm.check_models`, `room_llm.PROVIDERS` (T2 — call as `room_llm.check_models` so tests can monkeypatch `mux.agents.room_llm.check_models`); actor `ai_settings`, `save_ai_settings`, `clear_ai_settings` (T3).
- Produces: `GET /rooms/{id}/ai` (viewer) → `{"source": "room"|"server"|"none", "provider", "base_url", "models", "has_key"}`; `PUT /rooms/{id}/ai` (owner) body `{provider, base_url, api_key?, models: {lightning, super, ultra}}` → same view, or 400 with `detail` text or `detail: {"errors": {role: text}}`; `DELETE /rooms/{id}/ai` (owner) → view. `ai.server_view()` reads whether the server has a default from `settings.token_factory_api_key and settings.token_factory_base_url and settings.model_super`.

- [ ] **Step 1: Write the failing tests**

Append to `mux/server/tests/test_api.py`:

```python


# --- Room AI provider ----------------------------------------------------------

AI_BODY = {"provider": "openai", "base_url": "https://93.184.216.34/v1", "api_key": "sk-room-secret",
           "models": {"lightning": "fast-1", "super": "smart-1", "ultra": "smart-2"}}


@pytest.fixture
def ai_checks(monkeypatch):
    """check_models stand-in: records the key it was given, fails roles listed in `failing`."""
    from cryptography.fernet import Fernet

    import mux.agents.room_llm as room_llm
    seen: dict = {"keys": [], "failing": {}}

    async def fake_check(llm, models, secret):
        seen["keys"].append(secret)
        return dict(seen["failing"])

    monkeypatch.setattr(room_llm, "check_models", fake_check)
    monkeypatch.setattr(settings, "room_secrets_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "allow_private_urls", False)
    return seen


def test_owner_sets_the_room_ai_provider(client, ai_checks):
    rid = create_room(client)
    assert client.get(f"/rooms/{rid}/ai", headers=auth("alice")).json()["source"] == "none"
    r = client.put(f"/rooms/{rid}/ai", json=AI_BODY, headers=auth("alice"))
    assert r.status_code == 200, r.text
    view = r.json()
    assert view == {"source": "room", "provider": "openai", "base_url": AI_BODY["base_url"],
                    "models": AI_BODY["models"], "has_key": True}
    assert ai_checks["keys"] == ["sk-room-secret"]
    # Others can read it, never the key; only the owner changes it
    client.post(f"/rooms/{rid}/members", json={"user_id": "bob", "role": "editor"}, headers=auth("alice"))
    assert client.get(f"/rooms/{rid}/ai", headers=auth("bob")).json()["provider"] == "openai"
    assert client.put(f"/rooms/{rid}/ai", json=AI_BODY, headers=auth("bob")).status_code == 403
    assert "sk-room-secret" not in client.get(f"/rooms/{rid}/ai", headers=auth("alice")).text
    with client.websocket_connect(f"/rooms/{rid}/ws?since=0&token={token('alice')}") as ws:
        assert "sk-room-secret" not in ws.receive_text()


def test_empty_key_keeps_the_saved_one(client, ai_checks):
    rid = create_room(client)
    assert client.put(f"/rooms/{rid}/ai", json={**AI_BODY, "api_key": ""}, headers=auth("alice")).status_code == 400
    client.put(f"/rooms/{rid}/ai", json=AI_BODY, headers=auth("alice"))
    r = client.put(f"/rooms/{rid}/ai", json={**AI_BODY, "api_key": "", "models": {**AI_BODY["models"], "super": "smart-9"}},
                   headers=auth("alice"))
    assert r.status_code == 200 and r.json()["models"]["super"] == "smart-9"
    assert ai_checks["keys"] == ["sk-room-secret", "sk-room-secret"]


def test_bad_ai_settings_save_nothing(client, ai_checks, monkeypatch):
    rid = create_room(client)
    assert client.put(f"/rooms/{rid}/ai", json={**AI_BODY, "base_url": "https://10.0.0.5/v1"}, headers=auth("alice")).status_code == 400
    assert client.put(f"/rooms/{rid}/ai", json={**AI_BODY, "provider": "nope"}, headers=auth("alice")).status_code == 422
    assert client.put(f"/rooms/{rid}/ai", json={**AI_BODY, "models": {**AI_BODY["models"], "ultra": "has space"}},
                      headers=auth("alice")).status_code == 422
    ai_checks["failing"] = {"ultra": "NotFoundError: model smart-2 not found"}
    r = client.put(f"/rooms/{rid}/ai", json=AI_BODY, headers=auth("alice"))
    assert r.status_code == 400 and r.json()["detail"] == {"errors": {"ultra": "NotFoundError: model smart-2 not found"}}
    ai_checks["failing"] = {}
    monkeypatch.setattr(settings, "room_secrets_key", "")
    assert client.put(f"/rooms/{rid}/ai", json=AI_BODY, headers=auth("alice")).status_code == 400
    assert client.get(f"/rooms/{rid}/ai", headers=auth("alice")).json()["source"] == "none"


def test_clearing_and_restart(client, ai_checks, monkeypatch):
    rid = create_room(client)
    client.put(f"/rooms/{rid}/ai", json=AI_BODY, headers=auth("alice"))
    registry_call(client, room_registry.get_registry().stop_room, rid)
    assert client.get(f"/rooms/{rid}/ai", headers=auth("alice")).json()["source"] == "room"
    monkeypatch.setattr(settings, "token_factory_api_key", "tf-key")
    monkeypatch.setattr(settings, "token_factory_base_url", "https://tf.example/v1")
    monkeypatch.setattr(settings, "model_super", "nemotron")
    r = client.delete(f"/rooms/{rid}/ai", headers=auth("alice"))
    assert r.status_code == 200 and r.json() == {"source": "server", "provider": None, "base_url": None,
                                                 "models": None, "has_key": False}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_api.py -q -k "ai_provider or saved_one or ai_settings or clearing"`
Expected: FAIL (404 on `/rooms/{id}/ai`)

- [ ] **Step 3: Implement**

Create `mux/server/mux/api/ai.py`:

```python
"""A room's AI provider (mux/agents/room_llm.py): everyone in the room sees it, only the owner sets it."""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

import mux.agents.room_llm as room_llm
from mux.agents.llm import ModelRole, OpenAILLM
from mux.api.deps import User, get_room_actor_dep, require_owner, require_viewer
from mux.config import settings
from mux.rooms.actor import RoomActor
from mux.secrets import SecretsUnavailable, decrypt_value, encrypt_value
from mux.urls import UrlNotAllowed, check_url_async

router = APIRouter()

Provider = Literal["token_factory", "openai", "anthropic", "openrouter", "groq", "together", "custom"]
_MODEL_ID = re.compile(r"^\S{1,200}$")
_API_KEY = re.compile(r"^[\x21-\x7e]{1,500}$")


class Models(BaseModel):
    lightning: str
    super: str
    ultra: str

    @field_validator("lightning", "super", "ultra")
    @classmethod
    def _model_id(cls, value: str) -> str:
        if not _MODEL_ID.fullmatch(value):
            raise ValueError("model ids are 1-200 characters with no spaces")
        return value


class AiSettingsRequest(BaseModel):
    provider: Provider
    base_url: str = Field(..., min_length=8, max_length=500)
    api_key: str = Field("", max_length=500, description="Empty: keep the saved key")
    models: Models

    @field_validator("api_key")
    @classmethod
    def _key(cls, value: str) -> str:
        if value and not _API_KEY.fullmatch(value):
            raise ValueError("the API key has characters that aren't allowed")
        return value


def server_has_model() -> bool:
    return bool(settings.token_factory_api_key and settings.token_factory_base_url and settings.model_super)


def ai_view(actor: RoomActor) -> dict[str, Any]:
    ai = actor.ai_settings
    if ai is not None:
        return {"source": "room", "provider": ai["provider"], "base_url": ai["base_url"], "models": ai["models"],
                "has_key": True}
    return {"source": "server" if server_has_model() else "none", "provider": None, "base_url": None, "models": None,
            "has_key": False}


@router.get("/{room_id}/ai")
async def get_ai(room_id: str, current_user: User = Depends(require_viewer),
                 actor: RoomActor = Depends(get_room_actor_dep)) -> dict[str, Any]:
    return ai_view(actor)


@router.put("/{room_id}/ai")
async def set_ai(room_id: str, request: AiSettingsRequest, current_user: User = Depends(require_owner),
                 actor: RoomActor = Depends(get_room_actor_dep)) -> dict[str, Any]:
    try:
        await check_url_async(request.base_url)
    except UrlNotAllowed as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    try:
        if request.api_key:
            key, stored = request.api_key, encrypt_value(request.api_key)
        elif actor.ai_settings is not None:
            stored = actor.ai_settings["api_key"]
            key = decrypt_value(stored)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter the API key")
    except SecretsUnavailable as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    models = {ModelRole(role): model for role, model in request.models.model_dump().items()}
    llm = OpenAILLM(request.base_url, key, models, thinking=request.provider == "token_factory")
    errors = await room_llm.check_models(llm, models, key)
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": errors})
    await actor.save_ai_settings(request.provider, request.base_url, stored, request.models.model_dump(), current_user.id)
    return ai_view(actor)


@router.delete("/{room_id}/ai")
async def clear_ai(room_id: str, current_user: User = Depends(require_owner),
                   actor: RoomActor = Depends(get_room_actor_dep)) -> dict[str, Any]:
    await actor.clear_ai_settings(current_user.id)
    return ai_view(actor)

```

In `mux/server/mux/main.py`, change `from mux.api import rooms, files, commands, export, ws, mcp` to `from mux.api import rooms, files, commands, export, ws, mcp, ai` and after the MCP `include_router` line add:

```python
    app.include_router(ai.router, prefix="/rooms", tags=["ai"])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_api.py -q`
Expected: all pass, including the 4 new tests.

- [ ] **Step 5: Commit**

```bash
git add mux/server/mux/api/ai.py mux/server/mux/main.py mux/server/tests/test_api.py
git commit -m "Add the room AI provider API with a key check on save"
```

---

### Task 5: Runtime and app wiring

**Files:**
- Modify: `mux/server/mux/main.py:39-55` (`agent_runtime_factory`)
- Modify: `mux/server/mux/rooms/runtime.py` (imports; `__init__`; `_consume`; `_handle`; `_coder`; `_run`'s `except Exception`)
- Test: `mux/server/tests/test_runtime.py` (append)

**Interfaces:**
- Consumes: `RoomLLM`, `ModelError`, `NoModel`, `TokenFactoryLLM` (T2); `actor.save_ai_settings` (T3); `EventType.ROOM_AI_SETTINGS_SAVED` (T3).
- Produces: feed notice `ai.error` with `{"error": str}`; `RoomRuntime.model_error_interval: float = 60.0` (constructor keyword, tests pass a small value).

- [ ] **Step 1: Write the failing tests**

Append to `mux/server/tests/test_runtime.py`:

```python


# --- room AI provider -------------------------------------------------------------

class SwitchableLLM(FakeLLM):
    """FakeLLM with RoomLLM's available() switch, and an optional error for every call."""

    def __init__(self) -> None:
        super().__init__()
        self.on = False
        self.error: Exception | None = None

    def available(self) -> bool:
        return self.on

    async def chat(self, *args, **kwargs):
        if self.error is not None:
            raise self.error
        return await super().chat(*args, **kwargs)


@pytest.fixture
def switchable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logs: dict[str, InMemoryEventLog] = {}
    monkeypatch.setattr(room_registry, "get_event_log", lambda rid: logs.setdefault(rid, InMemoryEventLog(rid)))
    llm = SwitchableLLM()

    def factory(actor: RoomActor) -> RoomRuntime:
        return RoomRuntime(actor, llm, vote_timeout=30, question_timeout=30, max_turns=3, model_error_interval=60)

    return RoomRegistry(runtime_factory=factory), llm, logs


@pytest.mark.asyncio
async def test_no_model_means_no_agent_work_until_a_key_is_saved(switchable):
    registry, llm, logs = switchable
    actor = await new_room(registry, llm, logs)
    log = logs[actor.room_id]
    await actor.approve_plan_items(["t1"], "alice")
    await actor.add_message("chat", "hello", message_id="m1", user_id="alice", enqueue=False)
    await asyncio.sleep(0.2)
    assert llm.calls == [] and not notices(log, "ai.error")
    assert (await actor.get_plan())[0]["status"] == "todo"

    llm.on = True
    llm.push(tool_reply(("finish_task", {"summary": "done"})))
    await actor.save_ai_settings("openai", "https://api.example.com/v1", "ENC", {"lightning": "a", "super": "b", "ultra": "b"}, "alice")
    await until(lambda: of_type(log, EventType.CHECKPOINT_CREATED))
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_model_errors_reach_the_room_once_a_minute(switchable):
    from mux.agents.llm import ModelError
    registry, llm, logs = switchable
    actor = await new_room(registry, llm, logs, plan=None)
    log = logs[actor.room_id]
    llm.on = True
    llm.error = ModelError("401 invalid key [hidden]")
    await actor.add_message("chat", "one", message_id="m1", user_id="alice", enqueue=False)
    await actor.add_message("chat", "two", message_id="m2", user_id="alice", enqueue=False)
    await until(lambda: notices(log, "ai.error"))
    await asyncio.sleep(0.2)
    assert notices(log, "ai.error") == [{"error": "401 invalid key [hidden]"}]
    await registry.shutdown_all()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_runtime.py -q -k "no_model or once_a_minute"`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'model_error_interval'`)

- [ ] **Step 3: Implement the runtime changes**

In `mux/server/mux/rooms/runtime.py`:

Add `import time` to the stdlib imports and change `from mux.agents.llm import LLM, Usage` to `from mux.agents.llm import LLM, ModelError, Usage`.

In `RoomRuntime.__init__`, add the keyword parameter `model_error_interval: float = 60.0,` after `max_turns: int = 25,`, and in the body after `self.max_turns = max_turns`:

```python
        self.model_error_interval = model_error_interval
        self._last_model_error = float("-inf")
```

Add these methods to `RoomRuntime` (before `# ---- events ----`):

```python
    def _model_available(self) -> bool:
        """False when the room has no model (no room key, no server key): agents stay off, quietly."""
        available = getattr(self.llm, "available", None)
        return bool(available()) if callable(available) else True

    async def _model_error(self, error: ModelError) -> None:
        """Tell the room its model failed, at most once per model_error_interval."""
        now = time.monotonic()
        if now - self._last_model_error < self.model_error_interval:
            return
        self._last_model_error = now
        await self.actor.post_notice("ai.error", {"error": str(error)[:300]})
```

In `_consume`, add before `except Exception:`:

```python
            except ModelError as e:
                await self._model_error(e)
```

At the top of `_handle`, after `t = event.type`:

```python
        if t == EventType.ROOM_AI_SETTINGS_SAVED:
            self._wake.set()  # approved tasks waiting for a model can start
            return
        if not self._model_available():
            return
```

In `_coder`, change `if task is None or not await self.actor.check_budget_allowance():` to:

```python
                if task is None or not self._model_available() or not await self.actor.check_budget_allowance():
```

In `_run`, change:

```python
        except Exception as e:
            logger.exception(f"Room {self.actor.room_id}: coder failed on {task_id}")
            await self._park(item, f"error: {e}")
```

to:

```python
        except Exception as e:
            logger.exception(f"Room {self.actor.room_id}: coder failed on {task_id}")
            if isinstance(e, ModelError):
                await self._model_error(e)
            await self._park(item, f"error: {e}")
```

- [ ] **Step 4: Always build room runtimes**

In `mux/server/mux/main.py`, replace `agent_runtime_factory` with:

```python
def agent_runtime_factory() -> Callable[[RoomActor], RoomRuntime]:
    """The room agents. Each room uses its owner's AI provider, else Token Factory when configured; a room
    with neither has its agents off (RoomLLM.available() is False)."""
    from mux.agents.coder.prompts import load_conventions
    from mux.agents.llm import TokenFactoryLLM
    from mux.agents.room_llm import RoomLLM
    from mux.integrations.tavily import TavilySearch

    default = None
    if settings.token_factory_api_key and settings.token_factory_base_url and settings.model_super:
        default = TokenFactoryLLM()
    else:
        logger.warning("Token Factory is not configured (TOKEN_FACTORY_* / MODEL_SUPER): only rooms with their own AI key run agents")
    conventions = load_conventions(STARTER_TEMPLATE)

    def make(actor: RoomActor) -> RoomRuntime:
        search = TavilySearch() if settings.tavily_api_key else None  # one per room: the cache is per room
        return RoomRuntime(actor, RoomLLM(actor, default), search=search, conventions=conventions,
                           publish=event_bus.publish_json)

    return make
```

If `Optional` is no longer used in `main.py`, remove it from the typing import.

- [ ] **Step 5: Run the tests**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_runtime.py -q && .venv/bin/python -m pytest -q && .venv/bin/pyright mux tests scripts`
Expected: runtime tests pass; full suite passes; pyright `0 errors`.

- [ ] **Step 6: Commit**

```bash
git add mux/server/mux/rooms/runtime.py mux/server/mux/main.py mux/server/tests/test_runtime.py
git commit -m "Run each room's agents on its own AI provider and report model errors"
```

---

### Task 6: Web: AI model dialog

**Files:**
- Modify: `mux/web/src/types/index.ts` (after `RoomMcp`)
- Modify: `mux/web/src/lib/api.ts` (imports; `demoFetch`; methods after `refreshMcpAdmin`)
- Modify: `mux/web/src/lib/reducer.ts` (cases before `case 'mcp.changed':`)
- Create: `mux/web/src/components/room/AiModelDialog.tsx`
- Modify: `mux/web/src/components/room/TopBar.tsx`

**Interfaces:**
- Consumes: T4 API shapes.
- Produces: `RoomAi` type; `api.getAi`, `api.setAi`, `api.clearAi`.

- [ ] **Step 1: Types and API client**

In `mux/web/src/types/index.ts` after the `RoomMcp` interface:

```ts
// The AI provider a room's agents use: the owner's own key, the MUX server's model, or none
export type AiRole = 'lightning' | 'super' | 'ultra';

export interface RoomAi {
  source: 'room' | 'server' | 'none';
  provider: string | null;
  base_url: string | null;
  models: Record<AiRole, string> | null;
  has_key: boolean;
}
```

In `mux/web/src/lib/api.ts`, add `AiRole, RoomAi` to the `@/types` import; in `demoFetch` before the `/mcp` line:

```ts
  if (roomMatch && roomMatch[2] === '/ai') return { source: 'server', provider: null, base_url: null, models: null, has_key: false } as T;
```

and after `refreshMcpAdmin`:

```ts

  // The room's AI provider: anyone in the room reads it, only the owner sets it (the key is never returned)
  getAi: (id: string) => fetchWithAuth<RoomAi>(`/rooms/${id}/ai`),
  setAi: (id: string, data: { provider: string; base_url: string; api_key: string; models: Record<AiRole, string> }) =>
    fetchWithAuth<RoomAi>(`/rooms/${id}/ai`, { method: 'PUT', body: JSON.stringify(data) }),
  clearAi: (id: string) => fetchWithAuth<RoomAi>(`/rooms/${id}/ai`, { method: 'DELETE' }),
```

`fetchWithAuth` throws `ApiError` whose message is `JSON.stringify(detail)` for an object detail; the dialog parses it.

- [ ] **Step 2: Feed notice**

In `mux/web/src/lib/reducer.ts`, before `case 'mcp.changed':`:

```ts
    case 'ai.error': {
      const { error } = (event as unknown as { payload: { error: string } }).payload;
      newState.messages = [...newState.messages, {
        id: `ai-${event.seq}`,
        room_id: newState.room.id,
        user_id: 'coordinator',
        text: `The AI model failed (${error}). The room's owner can change it in AI model.`,
        created_at: event.ts,
        user: { id: 'coordinator', email: '', name: 'Coordinator', initials: 'CO', color: 'hsl(190, 70%, 60%)' },
      } as Message];
      break;
    }
    case 'ai.changed':
      // The AI model dialog loads the settings when it opens
      break;
```

- [ ] **Step 3: The dialog**

Create `mux/web/src/components/room/AiModelDialog.tsx`:

```tsx
'use client';

import React, { useEffect, useState } from 'react';
import { X, Bot } from 'lucide-react';
import type { AiRole, RoomAi } from '@/types';
import { api, ApiError } from '@/lib/api';

interface AiModelDialogProps {
  isOpen: boolean;
  onClose: () => void;
  roomId: string;
  isOwner: boolean;
}

const ROLES: { role: AiRole; label: string; hint: string }[] = [
  { role: 'lightning', label: 'Coordinator', hint: 'fast; labels every message' },
  { role: 'super', label: 'Coder', hint: 'writes the code' },
  { role: 'ultra', label: 'Coder when stuck', hint: 'the strongest model' },
];

const PRESETS: Record<string, { label: string; base_url: string; models: Record<AiRole, string> }> = {
  token_factory: { label: 'Nebius Token Factory', base_url: 'https://api.tokenfactory.nebius.com/v1', models: { lightning: '', super: '', ultra: '' } },
  openai: { label: 'OpenAI', base_url: 'https://api.openai.com/v1', models: { lightning: '', super: '', ultra: '' } },
  anthropic: { label: 'Anthropic', base_url: 'https://api.anthropic.com/v1', models: { lightning: 'claude-haiku-4-5-20251001', super: 'claude-sonnet-5-5', ultra: 'claude-opus-5-5' } },
  openrouter: { label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1', models: { lightning: '', super: '', ultra: '' } },
  groq: { label: 'Groq', base_url: 'https://api.groq.com/openai/v1', models: { lightning: '', super: '', ultra: '' } },
  together: { label: 'Together', base_url: 'https://api.together.xyz/v1', models: { lightning: '', super: '', ultra: '' } },
  custom: { label: 'Custom (OpenAI-compatible)', base_url: '', models: { lightning: '', super: '', ultra: '' } },
};

const field = 'w-full bg-[var(--bg)] border border-[var(--line)] rounded px-3 py-2 text-sm';

function describe(ai: RoomAi): string {
  if (ai.source === 'room') return `This room's own key · ${PRESETS[ai.provider ?? '']?.label ?? ai.provider}`;
  if (ai.source === 'server') return "The MUX server's model";
  return 'No AI model, so the agents are off';
}

export function AiModelDialog({ isOpen, onClose, roomId, isOwner }: AiModelDialogProps) {
  const [ai, setAi] = useState<RoomAi | null>(null);
  const [provider, setProvider] = useState('openai');
  const [baseUrl, setBaseUrl] = useState(PRESETS.openai.base_url);
  const [apiKey, setApiKey] = useState('');
  const [models, setModels] = useState<Record<AiRole, string>>(PRESETS.openai.models);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [roleErrors, setRoleErrors] = useState<Partial<Record<AiRole, string>>>({});

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setRoleErrors({});
    api.getAi(roomId).then(view => {
      setAi(view);
      if (view.source === 'room' && view.provider && view.base_url && view.models) {
        setProvider(view.provider);
        setBaseUrl(view.base_url);
        setModels(view.models);
      }
    }).catch(e => setError(e instanceof Error ? e.message : 'Could not load the AI model'));
  }, [isOpen, roomId]);

  if (!isOpen) return null;

  const choosePreset = (name: string) => {
    setProvider(name);
    setBaseUrl(PRESETS[name].base_url);
    setModels(PRESETS[name].models);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setRoleErrors({});
    try {
      setAi(await api.setAi(roomId, { provider, base_url: baseUrl.trim(), api_key: apiKey.trim(), models }));
      setApiKey('');
    } catch (err) {
      // A failed model check comes back as {"errors": {role: text}}
      try {
        const detail = JSON.parse(err instanceof ApiError ? err.message : '');
        if (detail && typeof detail === 'object' && detail.errors) {
          setRoleErrors(detail.errors);
          setError('Nothing was saved: some models did not answer.');
          return;
        }
      } catch {
        // not JSON: a plain message
      }
      setError(err instanceof Error ? err.message : 'Could not save');
    } finally {
      setBusy(false);
    }
  };

  const useServer = async () => {
    setBusy(true);
    setError(null);
    try {
      setAi(await api.clearAi(roomId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not switch');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-[var(--panel)] rounded-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="ai-title">
        <div className="flex items-center justify-between mb-2">
          <h2 id="ai-title" className="text-lg font-semibold flex items-center gap-2"><Bot className="w-5 h-5" /> AI model</h2>
          <button className="btn p-2" onClick={onClose} type="button" aria-label="Close"><X className="w-5 h-5" /></button>
        </div>
        {ai && <p className="mb-1 text-sm font-medium">{describe(ai)}</p>}
        {ai?.source === 'room' && ai.models && (
          <p className="mb-4 font-mono text-xs text-[var(--muted)]">
            {ROLES.map(r => `${r.label}: ${ai.models?.[r.role]}`).join(' · ')}
          </p>
        )}
        {!isOwner && <p className="mb-4 text-sm text-[var(--muted)]">Only the room&apos;s owner can change it.</p>}
        {error && <p className="mb-3 text-sm text-[var(--conflict)]" role="alert">{error}</p>}

        {isOwner && (
          <form onSubmit={save} className="space-y-3 p-4 bg-[var(--raised)] rounded-lg">
            <p className="text-sm text-[var(--muted)]">Use your own key: this room&apos;s agents run on it and you pay the provider.</p>
            <label className="block text-sm">Provider
              <select className={`${field} mt-1`} value={provider} onChange={e => choosePreset(e.target.value)}>
                {Object.entries(PRESETS).map(([name, p]) => <option key={name} value={name}>{p.label}</option>)}
              </select>
            </label>
            <label className="block text-sm">Base URL
              <input className={`${field} mt-1 font-mono`} value={baseUrl} onChange={e => setBaseUrl(e.target.value)} type="url" required placeholder="https://…/v1" />
            </label>
            <label className="block text-sm">API key
              <input className={`${field} mt-1`} value={apiKey} onChange={e => setApiKey(e.target.value)} type="password" autoComplete="off"
                required={ai?.source !== 'room'} placeholder={ai?.source === 'room' ? 'Leave empty to keep the saved key' : 'sk-…'} />
            </label>
            {ROLES.map(({ role, label, hint }) => (
              <label key={role} className="block text-sm">{label} <span className="text-[var(--muted)]">({hint})</span>
                <input className={`${field} mt-1 font-mono`} value={models[role]} required
                  onChange={e => setModels(m => ({ ...m, [role]: e.target.value.trim() }))} placeholder="model id" />
                {roleErrors[role] && <span className="mt-1 block text-xs text-[var(--conflict)]">{roleErrors[role]}</span>}
              </label>
            ))}
            <p className="text-xs text-[var(--muted)]">Saving sends one tiny request to each model to check the key and model ids.</p>
            <div className="flex flex-wrap gap-2">
              <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Checking…' : 'Save'}</button>
              {ai?.source === 'room' && (
                <button type="button" className="btn" onClick={useServer} disabled={busy}>Use the server&apos;s model</button>
              )}
            </div>
          </form>
        )}
        <div className="flex justify-end mt-4"><button className="btn" onClick={onClose} type="button">Done</button></div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: The button**

In `mux/web/src/components/room/TopBar.tsx`: add `Bot` to the lucide import list; add `import { AiModelDialog } from './AiModelDialog';` after the `ToolsDialog` import; add `const [showAi, setShowAi] = React.useState(false);` after `showTools`; before the Tools button:

```tsx
        <button className="btn flex items-center gap-1.5" onClick={() => setShowAi(true)} type="button" title="The AI model this room's agents use">
          <Bot className="w-4 h-4" />
          <span className="hidden sm:inline">AI model</span>
        </button>
```

and after the `<ToolsDialog ... />` line:

```tsx
      <AiModelDialog isOpen={showAi} onClose={() => setShowAi(false)} roomId={room.id} isOwner={isOwner} />
```

- [ ] **Step 5: Type-check, lint, build**

Run: `cd mux/web && npx tsc --noEmit && npm run lint -- --max-warnings=0 && NEXT_DIST_DIR=.next-build npm run build`
Expected: no errors; `✓ Compiled successfully`.

- [ ] **Step 6: Commit**

```bash
git add mux/web/src/types/index.ts mux/web/src/lib/api.ts mux/web/src/lib/reducer.ts mux/web/src/components/room/AiModelDialog.tsx mux/web/src/components/room/TopBar.tsx
git commit -m "Add the room AI model dialog"
```

---

### Task 7: Docs and settings examples

**Files:**
- Modify: `mux/server/.env.example`, `docs/03-getting-started.md`

- [ ] **Step 1: `.env.example`**

Replace the MCP block (from `# MCP servers for the coder.` through `MCP_ALLOW_PRIVATE_URLS=false`) with:

```
# Room secrets: MCP server tokens and the AI keys room owners save are encrypted with this Fernet key.
# Make one: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# (MCP_ENCRYPTION_KEY, the old name, still works.)
ROOM_SECRETS_KEY=
# Local development only: let rooms use http:// and private-network addresses (an Ollama on this machine,
# a local MCP server). MCP_ALLOW_PRIVATE_URLS, the old name, still works.
ALLOW_PRIVATE_URLS=false
# Server-wide MCP servers: copy mcp.example.json to mcp.json (read at startup).
MCP_CONFIG_PATH=mcp.json
```

- [ ] **Step 2: Getting-started section**

In `docs/03-getting-started.md`, in the MCP section replace `Set \`MCP_ENCRYPTION_KEY\`` with `Set \`ROOM_SECRETS_KEY\`` and `\`MCP_ALLOW_PRIVATE_URLS=true\`` with `\`ALLOW_PRIVATE_URLS=true\``, then add after the MCP section:

```markdown
## 🤖 A room's own AI model

By default every room's agents use the server's Token Factory settings (`TOKEN_FACTORY_*`, `MODEL_*`). A room's owner can use their own provider instead: **AI model** in the room's top bar → pick a provider (Nebius Token Factory, OpenAI, Anthropic, OpenRouter, Groq, Together, or any OpenAI-compatible URL), paste the API key and choose a model for each role:

| Role | Used by |
|---|---|
| Coordinator | Labels every message; pick a fast model |
| Coder | Writes the code |
| Coder when stuck | The model the coder switches to after repeated failures; pick the strongest |

**Save** sends one tiny request to each model and saves only if all answer. The key is encrypted with `ROOM_SECRETS_KEY` and never shown again; leave the key field empty later to keep it. The owner's provider bills the room's usage. **Use the server's model** goes back to the default.

If the model fails during work (wrong key, quota, rate limit), the feed says so (at most once a minute). A server with no Token Factory settings still runs agents in rooms that have their own key; other rooms have their agents off.
```

- [ ] **Step 3: Final verification and commit**

Run: `cd mux/server && .venv/bin/python -m pytest -q && cd ../web && npx tsc --noEmit && npm run lint -- --max-warnings=0`
Expected: all pass, no errors.

```bash
git add mux/server/.env.example docs/03-getting-started.md
git commit -m "Document room AI models and the shared ROOM_SECRETS_KEY"
```
