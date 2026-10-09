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
