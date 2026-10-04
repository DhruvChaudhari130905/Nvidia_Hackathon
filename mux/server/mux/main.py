"""FastAPI app factory. Mounts the API routers and the WebSocket endpoint, and starts the room registry on startup."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mux import dbsession
from mux.api import rooms, files, commands, export, ws
from mux.api.ws import emit_event_with_alias
from mux.events.log import EventLog, InMemoryEventLog
from mux.events.models import BaseEvent
import mux.rooms.registry as room_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Per-room event logs storage
_room_event_logs: dict[str, EventLog] = {}

def get_event_log(room_id: str) -> EventLog:
    """Get or create an event log for a specific room."""
    if room_id not in _room_event_logs:
        _room_event_logs[room_id] = InMemoryEventLog(room_id)
    return _room_event_logs[room_id]

# Make get_event_log available for dependency injection
room_registry.get_event_log = get_event_log

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MUX server...")
    await dbsession.init_db()
    logger.info("Database initialized")

    # Initialize room registry with event bus callback for real-time WebSocket broadcasts
    async def on_event_callback(event: BaseEvent) -> None:
        """Publish actor events to WebSocket event bus with frontend-compatible aliases."""
        await emit_event_with_alias(event.room_id, event)

    # EventLog is per-room; on_event publishes to event bus
    registry = await room_registry.init_registry(on_event=on_event_callback)
    await registry.start()
    logger.info("Room registry started")
    yield
    logger.info("Shutting down MUX server...")
    await room_registry.shutdown_registry()
    logger.info("Room registry stopped")
    await dbsession.close_db()

def create_app() -> FastAPI:
    app = FastAPI(
        title="MUX API",
        description="AI-powered collaborative coding platform",
        version="0.1.0",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        # Credentials can't be combined with a wildcard origin; auth uses bearer tokens
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        """Domain validation errors (bad plan items, unknown ids, ...) are client errors."""
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])
    app.include_router(files.router, prefix="/api/files", tags=["files"])
    app.include_router(commands.router, prefix="/api/commands", tags=["commands"])
    app.include_router(export.router, prefix="/api/export", tags=["export"])
    app.include_router(ws.router, prefix="/ws", tags=["websocket"])

    @app.get("/")
    async def root():
        return {"message": "MUX API is running"}

    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "mux.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
