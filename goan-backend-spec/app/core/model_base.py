"""Mixin dùng chung cho ORM model: UUID PK (SPEC 3 — tránh lộ số lượng đơn qua ID tuần tự)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

# Kiểu tiền tệ chuẩn: NUMERIC(12,0) -> Decimal nguyên đồng VNĐ (SPEC 13)
Money = Numeric(12, 0)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
