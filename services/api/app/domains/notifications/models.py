"""Token thiết bị để gửi push (P2-13).

Một người dùng có nhiều thiết bị, và mỗi lần cài lại app là một token mới trong khi token cũ
chết vĩnh viễn. Vì thế bảng này lưu theo TOKEN chứ không theo người: gỡ một token hỏng không
được đụng tới các máy khác của cùng người đó.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model_base import TimestampMixin, pg_enum, uuid_pk
from app.database import Base
from app.domains.notifications.constants import DevicePlatform


class PushToken(Base, TimestampMixin):
    __tablename__ = "push_tokens"
    __table_args__ = (
        UniqueConstraint("token", name="uq_push_tokens_token"),
        Index("ix_push_tokens_user", "user_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[DevicePlatform] = mapped_column(
        pg_enum(DevicePlatform, "device_platform"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
