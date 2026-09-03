"""FastAPI entrypoint: mount routers, lifespan (DB/Redis pool), health check."""

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, Response
from sqlalchemy import text

from app.config import settings
from app.core.audit_middleware import AuditMiddleware
from app.core.exceptions import NotFoundError, UnauthorizedError, register_exception_handlers
from app.core.idempotency import IdempotencyMiddleware
from app.core.logging import setup_logging
from app.core.metrics import MetricsMiddleware
from app.core.metrics import render as render_metrics
from app.core.middleware import RateLimitMiddleware
from app.core.observability import RequestIdMiddleware, setup_sentry, setup_tracing
from app.database import engine
from app.domains.auth.router import router as auth_router
from app.domains.escrow.router import router as escrow_router
from app.domains.fraud.router import router as fraud_router
from app.domains.iam.router import router as iam_router
from app.domains.matching.router import router as matching_router
from app.domains.partners.router import router as partners_router
from app.domains.payments.router import router as payments_router
from app.domains.pricing.router import router as pricing_router
from app.domains.trips.router import ops_router as trips_ops_router
from app.domains.trips.router import router as trips_router
from app.domains.users.router import router as users_router
from app.redis_client import close_redis, get_redis
from app.websocket.connection_manager import manager
from app.websocket.router import router as ws_router

logger = logging.getLogger("goan")


@asynccontextmanager
async def lifespan(app_: FastAPI):
    setup_logging()
    sentry_on = setup_sentry()
    tracing_on = setup_tracing(app_)
    logger.info(
        "starting %s (env=%s, sentry=%s, otel=%s, metrics=%s)",
        settings.APP_NAME,
        settings.ENV,
        "on" if sentry_on else "off",
        "on" if tracing_on else "off",
        "on" if settings.METRICS_ENABLED else "off",
    )
    yield
    await manager.shutdown()
    await close_redis()
    await engine.dispose()


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)

# Thứ tự quan trọng: Starlette chạy middleware theo chiều NGƯỢC với thứ tự add_middleware.
# Thêm sau = chạy trước. Vậy chuỗi thực thi là:
#   Metrics -> RequestId -> RateLimit -> Idempotency -> Audit -> router
# Metrics ngoài cùng để con số đo được đúng bằng thứ khách chờ, gồm cả request bị rate limit
# chặn và request được idempotency phát lại; RequestId kế tiếp để mọi thứ phía sau (kể cả log
# của rate limit) đều có mã tra cứu; Audit trong cùng để thấy status code cuối cùng.
app.add_middleware(AuditMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)
if settings.METRICS_ENABLED:
    app.add_middleware(MetricsMiddleware)
register_exception_handlers(app)

api = APIRouter(prefix=settings.API_V1_PREFIX)
for r in (
    auth_router,
    users_router,
    pricing_router,
    trips_router,
    trips_ops_router,
    matching_router,
    escrow_router,
    payments_router,
    partners_router,
    fraud_router,
    iam_router,
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


# Không đưa vào OpenAPI: /metrics phục vụ Prometheus, không phải client — thêm vào schema chỉ
# làm bẩn api-client sinh tự động.
@app.get("/metrics", tags=["ops"], include_in_schema=False)
async def metrics(request: Request) -> Response:
    """Số liệu cho Prometheus scrape.

    Không có PII trong nhãn, nhưng /metrics vẫn để lộ danh sách đường dẫn và tần suất gọi —
    đặt METRICS_TOKEN ở production để chỉ Prometheus đọc được.
    """
    if not settings.METRICS_ENABLED:
        raise NotFoundError("Số liệu đang tắt")
    if settings.METRICS_TOKEN and (
        request.headers.get("Authorization", "") != f"Bearer {settings.METRICS_TOKEN}"
    ):
        raise UnauthorizedError("Cần token để đọc số liệu")
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
