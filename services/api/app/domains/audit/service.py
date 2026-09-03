"""Ghi audit log. Tách khỏi middleware để service khác cũng gọi trực tiếp được."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit.models import AuditLog

logger = logging.getLogger("goan.audit")

# Không bao giờ ghi nguyên văn các trường này vào audit log.
SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "otp",
        "access_token",
        "refresh_token",
        "token",
        "qr_token",
        "national_id",
        "cccd",
        "license_number",
        "authorization",
        "secret",
        "card_number",
        "cvv",
        "pin",
        "idempotency_key",
    }
)
REDACTED = "***"
MAX_PAYLOAD_BYTES = 8_000

# Suy ra loại/định danh tài nguyên từ đường dẫn: /api/v1/trips/{uuid}/complete -> (trip, uuid)
_RESOURCE_RE = re.compile(r"/api/v1/(?P<type>[a-z-]+)/(?P<id>[0-9a-fA-F-]{8,36})(?:/|$)")
_SINGULAR = {
    "trips": "trip",
    "drivers": "driver",
    "users": "user",
    "partners": "partner",
    "payments": "payment",
}


def redact(value: Any, _depth: int = 0) -> Any:
    """Che đệ quy các trường nhạy cảm. Giới hạn độ sâu để payload lồng nhau không làm treo."""
    if _depth > 6:
        return REDACTED
    if isinstance(value, dict):
        return {
            k: (REDACTED if k.lower() in SENSITIVE_FIELDS else redact(v, _depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v, _depth + 1) for v in value[:50]]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "…"
    return value


def resolve_resource(path: str) -> tuple[str | None, str | None]:
    m = _RESOURCE_RE.search(path)
    if not m:
        return None, None
    raw = m.group("type")
    return _SINGULAR.get(raw, raw.rstrip("s")), m.group("id")


async def record(
    db: AsyncSession,
    *,
    action: str,
    method: str,
    path: str,
    status_code: int,
    actor_id: uuid.UUID | None = None,
    actor_staff_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    payload: dict | None = None,
    reason: str | None = None,
    duration_ms: int | None = None,
) -> AuditLog:
    resource_type, resource_id = resolve_resource(path)
    safe_payload = redact(payload) if payload is not None else None
    if safe_payload is not None and len(str(safe_payload)) > MAX_PAYLOAD_BYTES:
        safe_payload = {"_truncated": True, "_size": len(str(safe_payload))}

    entry = AuditLog(
        actor_id=actor_id,
        actor_staff_id=actor_staff_id,
        actor_role=actor_role,
        action=action,
        method=method,
        path=path[:512],
        status_code=status_code,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:512] or None,
        request_id=request_id,
        payload=safe_payload,
        reason=reason,
        duration_ms=duration_ms,
    )
    db.add(entry)
    await db.flush()
    return entry
