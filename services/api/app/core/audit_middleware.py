"""Middleware ghi audit log cho mọi thao tác ghi.

Đặt ở lớp trong cùng (thêm vào app sớm nhất) để nhìn thấy status code cuối cùng.

Ghi log KHÔNG được làm hỏng request: mọi lỗi khi ghi đều nuốt và log warning. Mất một dòng
audit là chuyện phải sửa, nhưng làm khách không đặt được xe vì lỗi ghi log thì tệ hơn.
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings
from app.core.security import decode_token
from app.database import SessionFactory
from app.domains.audit import service as audit_service

STAFF_ROLE = "staff"

logger = logging.getLogger("goan.audit")

AUDITED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Đường dẫn không cần audit: gửi OTP quá ồn và không thay đổi dữ liệu nghiệp vụ.
SKIP_PATHS = frozenset({"/api/v1/auth/request-otp"})
MAX_BODY_BYTES = 32_000


def _reason_from_body(body: dict | None) -> str | None:
    reason = (body or {}).get("reason")
    return reason[:2000] if isinstance(reason, str) and reason.strip() else None


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            not settings.AUDIT_ENABLED
            or request.scope["type"] != "http"
            or request.method not in AUDITED_METHODS
            or request.url.path in SKIP_PATHS
        ):
            return await call_next(request)

        # Đọc body rồi phát lại cho handler phía sau (BaseHTTPMiddleware không tự làm việc này).
        raw_body = await request.body()

        async def replay_receive() -> dict:
            return {"type": "http.request", "body": raw_body, "more_body": False}

        request._receive = replay_receive

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - started) * 1000)

        try:
            await self._write(request, response, raw_body, duration_ms)
        except Exception:
            logger.warning("Không ghi được audit log", exc_info=True)
        return response

    async def _write(
        self, request: Request, response: Response, raw_body: bytes, duration_ms: int
    ) -> None:
        actor_id: uuid.UUID | None = None
        actor_staff_id: uuid.UUID | None = None
        actor_role: str | None = None
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                payload = decode_token(auth[7:])
                actor_role = payload.get("role")
                # Nhân sự nội bộ ở bảng staff_users; nhét id đó vào actor_id sẽ vi phạm khoá
                # ngoại trỏ sang users và làm mất luôn dòng audit.
                if actor_role == STAFF_ROLE:
                    actor_staff_id = uuid.UUID(payload["sub"])
                else:
                    actor_id = uuid.UUID(payload["sub"])
            except Exception:
                pass  # token hỏng/hết hạn: vẫn ghi log nhưng không gán người thực hiện

        body: dict | None = None
        if raw_body and len(raw_body) <= MAX_BODY_BYTES:
            try:
                parsed = json.loads(raw_body)
                body = parsed if isinstance(parsed, dict) else {"_value": parsed}
            except ValueError:
                body = {"_non_json": True, "_bytes": len(raw_body)}

        async with SessionFactory() as session:
            await audit_service.record(
                session,
                action=f"{request.method} {request.url.path}",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                actor_id=actor_id,
                actor_staff_id=actor_staff_id,
                actor_role=actor_role,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                request_id=getattr(request.state, "request_id", None),
                payload=body,
                # Thao tác nhạy cảm gửi lý do trong body (xem PII, khoá tài khoản, hoàn tiền).
                # Không có thì mới lấy từ header.
                reason=request.headers.get("X-Audit-Reason") or _reason_from_body(body),
                duration_ms=duration_ms,
            )
            await session.commit()
