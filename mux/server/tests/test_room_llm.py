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
    plain_client, thinking_client = fake_client(), fake_client()
    await OpenAILLM("https://x/v1", "k", {ModelRole.SUPER: "m"}, client=plain_client).chat(ModelRole.SUPER, [], reasoning=True)
    await OpenAILLM("https://x/v1", "k", {ModelRole.SUPER: "m"}, thinking=True, client=thinking_client).chat(
        ModelRole.SUPER, [], reasoning=True)
    assert "extra_body" not in plain_client.chat.completions.calls[0]
    assert thinking_client.chat.completions.calls[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}


async def test_check_models_tries_each_distinct_model_once():
    client = fake_client()
    llm = OpenAILLM("https://x/v1", "k", {ModelRole(r): m for r, m in MODELS.items()}, client=client)
    assert await check_models(llm, {ModelRole(r): m for r, m in MODELS.items()}, "k") == {}
    assert [c["model"] for c in client.chat.completions.calls] == ["fast-1", "smart-1"]


async def test_check_models_reports_per_role_with_the_key_hidden():
    failing = OpenAILLM("https://x/v1", "sk-1", {ModelRole(r): m for r, m in MODELS.items()},
                        client=fake_client(RuntimeError("401 Incorrect API key: sk-1")))
    errors = await check_models(failing, {ModelRole(r): m for r, m in MODELS.items()}, "sk-1")
    assert set(errors) == {"lightning", "super", "ultra"}
    assert all("sk-1" not in e and "[hidden]" in e for e in errors.values())


def test_redact():
    assert redact("key sk-1 and 'sk-1'", "sk-1") == "key [hidden] and '[hidden]'"
    assert redact("nothing", "") == "nothing"
