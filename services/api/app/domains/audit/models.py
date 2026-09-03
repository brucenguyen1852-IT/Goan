"""Bảng audit_logs — dấu vết mọi thao tác ghi (SPEC 13, mục 2.3 tài liệu phân định).

Nguyên tắc: chỉ ghi thêm, không sửa, không xoá. Đây là bằng chứng khi có tranh chấp tiền
với tài xế và là yêu cầu bắt buộc để kiểm toán vòng gọi vốn sau.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base

# JSONB trên Postgres (index được), JSON thường trên SQLite khi chạy test.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
        Index("ix_audit_logs_staff_created", "actor_staff_id", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Ai — NULL khi request chưa đăng nhập (vd gửi OTP).
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Nhân sự nội bộ nằm ở bảng khác (staff_users), không dùng chung khoá ngoại với users.
    actor_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Làm gì
    action: Mapped[str] = mapped_column(String(128))  # vd "POST /api/v1/trips"
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(512))
    status_code: Mapped[int] = mapped_column(Integer)

    # Trên đối tượng nào — suy ra từ đường dẫn, để tra cứu "chuyến X ai đã đụng vào"
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Từ đâu
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Nội dung — đã che các trường nhạy cảm, xem audit/service.py
    payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    # Lý do — bắt buộc với thao tác nhạy cảm của nhân sự nội bộ (che PII, hoàn tiền, khoá tài khoản)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
