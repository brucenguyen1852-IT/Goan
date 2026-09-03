"""Idempotency-Key dùng chung cho mọi POST chạm tiền (SPEC 13).

Mạng di động ở VN chập chờn: app tài xế bấm "Hoàn thành chuyến", mất sóng, người dùng bấm lại.
Nếu không khử trùng thì khách bị trừ tiền hai lần. Trước đây mỗi endpoint tự lo (tạo chuyến,
kết thúc chuyến); giờ gom về một chỗ để endpoint mới không thể quên.

Cơ chế:
  1. SETNX khoá theo (user, method, path, key). Giành được khoá thì xử lý thật.
  2. Xử lý xong, lưu (status, body) vào Redis 24h.
  3. Request trùng sau đó phát lại đúng response cũ, kèm header Idempotent-Replay: true.
  4. Request trùng khi bản gốc CÒN ĐANG CHẠY thì trả 409 — không xử lý song song.

Chỉ khoá theo user để hai người dùng khác nhau vô tình trùng key không ảnh hưởng nhau.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
from typing import cast

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import StreamingResponse

from app.config import settings
from app.core.security import decode_token
from app.redis_client import get_redis

logger = logging.getLogger("goan.idempotency")

IDEMPOTENCY_HEADER = "Idempotency-Key"
REPLAY_HEADER = "Idempotent-Replay"

# Các endpoint bắt buộc khử trùng: tạo ra tiền hoặc bản ghi không thể hoàn tác.
PROTECTED_SUFFIXES: tuple[str, ...] = (
    "/complete",
    "/cancel",
    "/withdraw",
    "/request-refund",
    "/accept",
)
PROTECTED_EXACT: tuple[str, ...] = ("/api/v1/trips",)
MAX_CACHED_BODY = 64_000


def is_protected(method: str, path: str) -> bool:
    if method != "POST":
        return False
    if path.rstrip("/") in PROTECTED_EXACT:
        return True
    return path.endswith(PROTECTED_SUFFIXES)


def _actor_from_request(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            return str(decode_token(auth[7:])["sub"])
        except Exception:
            return "anon"
    return "anon"


def build_key(actor: str, method: str, path: str, raw_key: str) -> str:
    digest = hashlib.sha256(f"{actor}|{method}|{path}|{raw_key}".encode()).hexdigest()[:40]
    return f"idem:{digest}"


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if request.scope["type"] != "http" or not is_protected(request.method, path):
            return await call_next(request)

        raw_key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
        if not raw_key:
            if settings.IDEMPOTENCY_REQUIRED:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "idempotency_key_required",
                            "message": f"Thiếu header {IDEMPOTENCY_HEADER} cho thao tác này",
                        }
                    },
                )
            return await call_next(request)

        key = build_key(_actor_from_request(request), request.method, path, raw_key[:128])
        lock_key = key + ":lock"

        try:
            redis = get_redis()
            cached = await redis.get(key)
        except Exception:
            # Redis hỏng thì không chặn nghiệp vụ — mất khử trùng còn hơn mất dịch vụ.
            logger.warning("Redis không sẵn sàng, bỏ qua idempotency", exc_info=True)
            return await call_next(request)

        if cached is not None:
            stored = json.loads(cached)
            return JSONResponse(
                status_code=stored["status"],
                content=stored["body"],
                headers={REPLAY_HEADER: "true"},
            )

        acquired = await redis.set(lock_key, "1", nx=True, ex=60)
        if not acquired:
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "idempotency_in_progress",
                        "message": "Yêu cầu tương tự đang được xử lý, vui lòng chờ",
                    }
                },
            )

        try:
            response = await call_next(request)
            # call_next luôn trả StreamingResponse; cần gom body để vừa cache vừa trả lại.
            chunks: list[bytes] = []
            async for chunk in cast(StreamingResponse, response).body_iterator:
                chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode())
            body = b"".join(chunks)
            # Chỉ ghi nhớ kết quả thành công. Lỗi 4xx/5xx phải cho phép thử lại.
            if 200 <= response.status_code < 300 and len(body) <= MAX_CACHED_BODY:
                # response không phải JSON thì không cache, vẫn trả về bình thường
                with contextlib.suppress(ValueError, TypeError):
                    await redis.set(
                        key,
                        json.dumps({"status": response.status_code, "body": json.loads(body)}),
                        ex=settings.IDEMPOTENCY_TTL_SECONDS,
                    )
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        finally:
            await redis.delete(lock_key)
