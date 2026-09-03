"""FastAPI entrypoint: mount routers, lifespan (DB/Redis pool), health check."""

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Response
from sqlalchemy import text

from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RateLimitMiddleware
from app.database import engine
from app.domains.auth.router import router as auth_router
from app.domains.escrow.router import router as escrow_router
from app.domains.fraud.router import router as fraud_router
from app.domains.matching.router import router as matching_router
from app.domains.partners.router import router as partners_router
from app.domains.payments.router import router as payments_router
from app.domains.pricing.router import router as pricing_router
from app.domains.trips.router import router as trips_router
from app.domains.users.router import router as users_router
from app.redis_client import close_redis, get_redis
from app.websocket.connection_manager import manager
from app.websocket.router import router as ws_router

logger = logging.getLogger("goan")


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    logger.info("starting %s (env=%s)", settings.APP_NAME, settings.ENV)
    yield
    await manager.shutdown()
    await close_redis()
    await engine.dispose()


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
register_exception_handlers(app)

api = APIRouter(prefix=settings.API_V1_PREFIX)
for r in (
    auth_router,
    users_router,
    pricing_router,
    trips_router,
    matching_router,
    escrow_router,
    payments_router,
    partners_router,
    fraud_router,
):
    api.include_router(r)

app.include_router(api)
app.include_router(ws_router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    """Liveness: tiến trình còn sống hay không. KHÔNG chạm DB/Redis.

    Load balancer và orchestrator dùng probe này để quyết định có restart container không —
    nếu nó phụ thuộc DB thì một sự cố DB sẽ khiến toàn bộ container bị restart vô ích.
    """
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}


@app.get("/ready", tags=["ops"])
async def ready(response: Response) -> dict:
    """Readiness: đủ điều kiện nhận traffic chưa (cần cả DB và Redis).

    Trả 503 khi chưa sẵn sàng để LB ngừng đẩy request vào instance này.
    """
    status: dict = {"database": "ok", "redis": "ok"}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        status["database"] = f"error: {type(exc).__name__}"
    try:
        await get_redis().ping()
    except Exception as exc:  # pragma: no cover
        status["redis"] = f"error: {type(exc).__name__}"

    status["ready"] = status["database"] == "ok" and status["redis"] == "ok"
    if not status["ready"]:
        response.status_code = 503
    return status
