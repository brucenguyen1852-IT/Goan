"""Số liệu Prometheus cho tầng HTTP (SPEC 12 — Phase 7 hardening).

Vì sao tự viết middleware thay vì lắp một thư viện có sẵn:

1. **Nhãn `path` phải là template của route**, không phải đường dẫn thật. `/api/v1/trips/{trip_id}`
   là một chuỗi thời gian; `/api/v1/trips/<uuid>` là hàng triệu chuỗi thời gian và đủ để giết
   Prometheus. Đường dẫn không khớp route nào (bot quét, gõ nhầm) gom hết vào `unmatched` —
   nếu để nguyên thì chỉ cần một con bot quét là nổ cardinality.
2. Đo **toàn bộ** thời gian request, gồm cả rate limit và phát lại idempotency, nên middleware
   này phải nằm ngoài cùng (xem thứ tự trong `app/main.py`).

Nhãn cố ý KHÔNG có user_id, số điện thoại hay bất cứ thứ gì định danh được người dùng: số liệu
được scrape và lưu ở hệ thống ngoài, không phải nơi để PII đi ra.
"""

from __future__ import annotations

import time

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings

UNMATCHED = "unmatched"

# Đường dẫn không tự đếm mình: scrape mỗi 15 giây sẽ làm nhiễu chính số liệu đang đo.
EXCLUDED_PATHS = frozenset({"/metrics"})

REQUESTS = Counter(
    "goan_http_requests_total",
    "Tổng số request HTTP đã xử lý",
    labelnames=("method", "path", "status"),
)

LATENCY = Histogram(
    "goan_http_request_duration_seconds",
    "Thời gian xử lý request HTTP",
    labelnames=("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

IN_PROGRESS = Gauge(
    "goan_http_requests_in_progress",
    "Số request đang xử lý dở",
    labelnames=("method",),
)

APP_INFO = Gauge(
    "goan_app_info",
    "Thông tin bản dựng đang chạy (giá trị luôn bằng 1, thông tin nằm ở nhãn)",
    labelnames=("app", "env", "release"),
)


def route_label(request: Request) -> str:
    """Lấy template của route đã khớp. Gọi SAU khi router chạy xong thì scope mới có `route`."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else UNMATCHED


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        method = request.method
        started = time.perf_counter()
        IN_PROGRESS.labels(method=method).inc()
        status = "500"  # nếu handler ném ra ngoài thì vẫn phải được đếm
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            IN_PROGRESS.labels(method=method).dec()
            path = route_label(request)
            REQUESTS.labels(method=method, path=path, status=status).inc()
            LATENCY.labels(method=method, path=path).observe(time.perf_counter() - started)


def render() -> tuple[bytes, str]:
    """Trả về (nội dung, content-type) theo đúng định dạng phơi bày của Prometheus."""
    APP_INFO.labels(app=settings.APP_NAME, env=settings.ENV, release=settings.RELEASE or "dev").set(
        1
    )
    return generate_latest(), CONTENT_TYPE_LATEST
