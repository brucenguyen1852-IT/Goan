"""Request ID xuyên suốt + hook Sentry tuỳ chọn (SPEC 12 — Phase 7).

Mỗi request có một `request_id`. Nó đi vào mọi dòng log của request đó, vào bảng audit_logs,
và trả về cho client qua header `X-Request-ID`. Khi khách báo lỗi, chỉ cần một mã này là tra
được toàn bộ dấu vết — không phải mò theo thời gian.
"""

from __future__ import annotations

import contextvars
import logging
import uuid

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings

logger = logging.getLogger("goan.observability")

REQUEST_ID_HEADER = "X-Request-ID"
request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def current_request_id() -> str | None:
    return request_id_ctx.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Nhận X-Request-ID từ client (nếu có) hoặc sinh mới. Phải là middleware ngoài cùng."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        # Không tin tưởng giá trị client gửi lên quá 64 ký tự.
        request_id = incoming[:64] if incoming else uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class RequestIdLogFilter(logging.Filter):
    """Gắn request_id vào mọi log record để formatter JSON in ra được."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id() or "-"
        return True


def setup_sentry() -> bool:
    """Bật Sentry khi có SENTRY_DSN. Không có DSN thì im lặng bỏ qua — dev không cần cài gói.

    Trả về True nếu đã bật, để `/health` và log khởi động phản ánh đúng thực tế.
    """
    dsn = getattr(settings, "SENTRY_DSN", "") or ""
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        logger.warning("SENTRY_DSN đã đặt nhưng chưa cài sentry-sdk — bỏ qua")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.ENV,
        release=getattr(settings, "RELEASE", None) or None,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        # Không gửi kèm body request: có thể chứa OTP, số CCCD, toạ độ.
        send_default_pii=False,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    )
    logger.info("Sentry đã bật (env=%s)", settings.ENV)
    return True


def install(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
