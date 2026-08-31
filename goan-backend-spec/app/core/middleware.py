"""Rate limiting đơn giản qua Redis (SPEC 12 — Phase 7 hardening).

Cửa sổ 1 phút cố định theo IP + user (nếu có token), đủ để chặn spam OTP/tạo chuyến.
"""

import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings
from app.redis_client import RATE_LIMIT_KEY, get_redis

EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        if request.url.path in EXEMPT_PATHS or request.scope["type"] != "http":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        auth = request.headers.get("authorization", "")
        scope = f"{client_ip}:{auth[-16:]}" if auth else client_ip
        key = RATE_LIMIT_KEY.format(scope=scope, minute=int(time.time() // 60))

        try:
            redis = get_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 70)
        except Exception:
            # Redis lỗi thì không chặn request nghiệp vụ.
            return await call_next(request)

        if count > settings.RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Quá nhiều request, thử lại sau",
                        "details": {"limit_per_minute": settings.RATE_LIMIT_PER_MINUTE},
                    }
                },
            )
        return await call_next(request)
