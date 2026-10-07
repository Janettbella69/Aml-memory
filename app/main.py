from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from . import __version__
from .config import Settings
from .models import AddRequest, AddResponse, HealthResponse, SearchRequest, SearchResponse
from .search import search as assemble_evidence
from .store import ConflictingRequestError, MemoryStore

log = logging.getLogger("aml_memory")


def create_app(settings: Settings | None = None, store: MemoryStore | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    logging.basicConfig(level=cfg.log_level)
    memory = store or MemoryStore(cfg.database_path, retention_days=cfg.retention_days)

    async def retention_loop() -> None:
        while True:
            try:
                removed = await asyncio.to_thread(memory.delete_expired)
                if removed:
                    log.info("retention sweep removed %d turns older than %d days", removed, cfg.retention_days)
            except Exception:  # never let the sweep take the service down
                log.exception("retention sweep failed")
            await asyncio.sleep(cfg.sweep_hours * 3600)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = asyncio.create_task(retention_loop())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="aml-memory", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = cfg
    app.state.store = memory

    def authenticate(
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
    ) -> None:
        if not cfg.api_key:
            return
        candidate = x_api_key or ""
        if authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() in ("bearer", "token"):
                candidate = token.strip()
        if not candidate or not secrets.compare_digest(candidate.encode(), cfg.api_key.encode()):
            raise HTTPException(status_code=401, detail="missing or invalid API key (X-Api-Key / Bearer / Token)")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    def add_memory(payload: AddRequest, _: None = Depends(authenticate)) -> AddResponse:
        try:
            memory.add(payload)
        except ConflictingRequestError as conflict:
            raise HTTPException(status_code=409, detail=str(conflict)) from conflict
        return AddResponse(request_id=payload.request_id, user_id=payload.user_id, session_id=payload.session_id)

    def search_memory(payload: SearchRequest, _: None = Depends(authenticate)) -> SearchResponse:
        data = assemble_evidence(memory, cfg, payload.query, payload.options, payload.user_id, payload.top_k)
        log.info("search results=%d top_k=%d", len(data), payload.top_k)  # never the query or memory text
        return SearchResponse(data=data)

    for path in ("/v1/memories/add", "/add"):
        app.add_api_route(path, add_memory, methods=["POST"], response_model=AddResponse)
    for path in ("/v1/memories/search", "/search"):
        app.add_api_route(path, search_memory, methods=["POST"], response_model=SearchResponse)
    return app

