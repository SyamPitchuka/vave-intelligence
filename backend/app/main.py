"""VAVE Intelligence API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api, health
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.seed import seed_demo_content
from app.db.session import get_session_factory
from app.services.llm_providers.base import OfflineModeBlocked, ProviderUnavailable

logger_name = "vave"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.seed_demo_data:
        db = get_session_factory()()
        try:
            seed_demo_content(db)
            db.commit()
        finally:
            db.close()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="AI-assisted VAVE idea management, duplicate detection, and engineering knowledge copilot.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(LookupError)
    async def missing(_request: Request, exc: LookupError):
        return JSONResponse(status_code=404, content={"detail": {"code": "not_found", "message": str(exc)}})

    @app.exception_handler(ValueError)
    async def invalid(_request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": {"code": "invalid", "message": str(exc)}})

    @app.exception_handler(ProviderUnavailable)
    async def provider(_request: Request, exc: ProviderUnavailable):
        return JSONResponse(status_code=409, content={"detail": {"code": "provider_unavailable", "message": str(exc)}})

    @app.exception_handler(OfflineModeBlocked)
    async def offline(_request: Request, exc: OfflineModeBlocked):
        return JSONResponse(status_code=409, content={"detail": {"code": "offline_blocked", "message": str(exc)}})

    app.include_router(api)
    app.add_api_route("/health", health, methods=["GET"], tags=["health"])
    return app


app = create_app()
