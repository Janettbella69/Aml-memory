from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from . import __version__
from .config import Settings
from .models import AddRequest, AddResponse, HealthResponse, SearchRequest, SearchResponse
from .search import search as run_search
from .store import ConflictingRequestError, MemoryStore

LOGGER = logging.getLogger("aml_memory")


def create_app(settings: Settings | None = None, store: MemoryStore | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    logging.basicConfig(level=cfg.log_level)
    db = store or MemoryStore(cfg.database_path, retention_days=cfg.retention_days)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        removed = db.delete_expired()
        if removed:
            LOGGER.info("retention sweep removed %d chunks", removed)
        yield

    app = FastAPI(title="AML memory service", version=__version__, lifespan=lifespan)
    app.state.settings = cfg
    app.state.store = db

    def require_key(
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
    ) -> None:
        if not cfg.api_key:
            return
        presented = x_api_key
        if authorization:
            scheme, _, value = authorization.partition(" ")
            if scheme.lower() in {"bearer", "token"} and value:
                presented = value.strip()
        if not presented or not secrets.compare_digest(presented, cfg.api_key):
            raise HTTPException(status_code=401, detail="invalid or missing API key")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    def add_memory(payload: AddRequest, _: None = Depends(require_key)) -> AddResponse:
        try:
            db.add(payload)
        except ConflictingRequestError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return AddResponse(request_id=payload.request_id, user_id=payload.user_id, session_id=payload.session_id)

    def search_memory(payload: SearchRequest, _: None = Depends(require_key)) -> SearchResponse:
        data = run_search(db, cfg, payload.query, payload.options, payload.user_id, payload.top_k)
        # Never log query or memory text: evaluation data must stay out of logs.
        LOGGER.info("search user=%s results=%d", payload.user_id[:24], len(data))
        return SearchResponse(data=data)

    for path in ("/v1/memories/add", "/add"):
        app.add_api_route(path, add_memory, methods=["POST"], response_model=AddResponse)
    for path in ("/v1/memories/search", "/search"):
        app.add_api_route(path, search_memory, methods=["POST"], response_model=SearchResponse)
    return app


app = create_app()
