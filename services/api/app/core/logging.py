"""Structured JSON logging (SPEC 12 — Phase 7 hardening)."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.config import settings

SENSITIVE_KEYS = {
    "national_id_number",
    "otp",
    "password",
    "qr_token",
    "access_token",
    "refresh_token",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id and request_id != "-":
            payload["request_id"] = request_id
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = "***" if key in SENSITIVE_KEYS else value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if settings.JSON_LOGS
        else logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    # Gắn request_id vào mọi log record (import muộn để tránh vòng lặp import).
    from app.core.observability import RequestIdLogFilter

    handler.addFilter(RequestIdLogFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)


def log_event(logger: logging.Logger, message: str, **fields: Any) -> None:
    logger.info(message, extra={"extra_fields": fields})
