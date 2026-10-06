"""FastAPI app: the room REST API at /api/rooms and the room WebSocket at /ws/rooms/{room_id}.

Run one worker (`uvicorn mux.main:app`): each room's actor, and so its seqs, live in this one process (DB1).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from tavily import AsyncTavilyClient

from mux.agents.llm import TokenFactoryLLM
from mux.integrations.tavily import TavilySearch
from mux.sandbox.client import TokenFactorySandboxClient
from mux.api import rooms, ws
from mux.config import settings
from mux.events.bus import event_bus
from mux.rooms.registry import init_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """One registry for the process; on shutdown every room's coordinator and background tick stop."""
    llm = TokenFactoryLLM() if settings.token_factory_api_key else None
    if llm is None:
        logger.warning("TOKEN_FACTORY_API_KEY is not set: messages to the agent will get no answer")
    search = None
    if settings.tavily_api_key:
        client = AsyncTavilyClient(api_key=settings.tavily_api_key)  # one client, one cache per room
        search = lambda: TavilySearch(client)  # noqa: E731
    else:
        logger.warning("TAVILY_API_KEY is not set: conflict votes open without research")
    sandbox = None
    if settings.sandbox_api_key:
        sandbox = TokenFactorySandboxClient(settings.sandbox_api_key, settings.sandbox_base_url)
    else:
        logger.warning("SANDBOX_API_KEY is not set: the coder cannot build or test")
    registry = init_registry(
        event_bus.publish, llm=llm, search=search, sandbox=sandbox, sandbox_image=settings.sandbox_image
    )
    yield
    await registry.close()


async def bad_request(request: Request, exc: Exception) -> JSONResponse:
    """A broken rule: a bad plan change, an invalid path, an open link with no permission."""
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)


async def conflict(request: Request, exc: Exception) -> JSONResponse:
    """Someone else holds the file's lock, or the caller does not."""
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_409_CONFLICT)


async def not_found(request: Request, exc: Exception) -> JSONResponse:
    """An unknown file or checkpoint."""
    return JSONResponse({"detail": "not found"}, status_code=status.HTTP_404_NOT_FOUND)


def create_app() -> FastAPI:
    app = FastAPI(title="MUX API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
    )
    app.add_exception_handler(ValueError, bad_request)
    app.add_exception_handler(PermissionError, conflict)
    app.add_exception_handler(KeyError, not_found)
    app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])
    app.include_router(ws.router, prefix="/ws")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
