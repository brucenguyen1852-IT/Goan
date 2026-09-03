"""Rate limiting bằng cửa sổ trượt trên Redis (SPEC 12 — hardening).

Vì sao cửa sổ trượt: cửa sổ cố định theo phút cho phép gửi gấp đôi hạn mức quanh ranh giới phút
(cuối phút N và đầu phút N+1). Với endpoint gửi OTP thì đó là kẽ hở thật — mỗi tin nhắn là tiền.

Cài đặt: sorted set theo scope, score = timestamp. Mỗi request xoá phần tử cũ hơn cửa sổ rồi đếm.
Toàn bộ chạy trong một pipeline để không phải round-trip nhiều lần.
"""

from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings
from app.redis_client import RATE_LIMIT_KEY, get_redis

EXEMPT_PATHS = {"/health", "/ready", "/docs", "/openapi.json", "/redoc", "/docs/oauth2-redirect"}

# Hạn mức riêng cho các endpoint tốn tiền hoặc dễ bị lạm dụng.
# (tiền tố đường dẫn, số request, cửa sổ tính bằng giây)
STRICT_RULES: tuple[tuple[str, int, int], ...] = (
    ("/api/v1/auth/request-otp", 5, 300),  # 5 tin OTP / 5 phút — mỗi tin là chi phí SMS thật
    ("/api/v1/auth/verify-otp", 10, 300),  # chặn dò mã OTP
    ("/api/v1/trips", 20, 60),  # chặn spam tạo chuyến
)


def _resolve_rule(path: str) -> tuple[str, int, int]:
    for prefix, limit, window in STRICT_RULES:
        if path.startswith(prefix):
            return prefix, limit, window
    return "default", settings.RATE_LIMIT_PER_MINUTE, 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.scope["type"] != "http" or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        bucket, limit, window = _resolve_rule(request.url.path)
        client_ip = request.client.host if request.client else "unknown"
        auth = request.headers.get("authorization", "")
        identity = f"{client_ip}:{auth[-16:]}" if auth else client_ip
        key = RATE_LIMIT_KEY.format(scope=f"{bucket}:{identity}")

        now = time.time()
        try:
            redis = get_redis()
            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zadd(key, {f"{now}:{uuid.uuid4().hex[:8]}": now})
            pipe.zcard(key)
            pipe.expire(key, window + 10)
            count = (await pipe.execute())[2]
        except Exception:
            # Redis lỗi thì không chặn request nghiệp vụ — ưu tiên phục vụ khách.
            return await call_next(request)

        if count > limit:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(window)},
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Quá nhiều request, thử lại sau",
                        "details": {"limit": limit, "window_seconds": window},
                    }
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(limit - count, 0))
        return response
