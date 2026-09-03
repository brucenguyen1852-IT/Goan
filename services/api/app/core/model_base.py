"""Mixin dùng chung cho ORM model: UUID PK (SPEC 3 — tránh lộ số lượng đơn qua ID tuần tự)."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Numeric, Uuid, func
from sqlalchemy import Enum as SAEnum
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


def pg_enum(enum_cls: type[Enum], name: str) -> SAEnum:
    """Cột enum lưu **giá trị** ("rider"), không phải tên thành viên ("RIDER").

    Mặc định SQLAlchemy lưu TÊN thành viên. Trên SQLite không ai thấy vì cả ghi lẫn đọc đều
    dùng tên. Trên Postgres thì kiểu enum được migration tạo ra bằng giá trị viết thường, nên
    mọi lần ghi đều ngã: `invalid input value for enum user_role: "RIDER"`.

    Nói cách khác: dùng thẳng `Enum(UserRole, ...)` thì test SQLite xanh còn production
    Postgres không tạo nổi một người dùng. Mọi cột enum phải đi qua hàm này.
    """
    return SAEnum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])
