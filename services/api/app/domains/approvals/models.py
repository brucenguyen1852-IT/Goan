"""Maker–checker: đề nghị và phê duyệt cho thao tác chạm tiền (phân định §2.3).

Vì sao cần bảng riêng thay vì gọi thẳng: những thao tác này (chi tiền, hoàn ký quỹ, điều chỉnh
cước, phạt gian lận, hoàn tiền) không có nút hoàn tác. Tách làm hai bước và bắt hai người khác
nhau ký là cách rẻ nhất để một tài khoản bị chiếm hoặc một phút bốc đồng không đủ để chuyển
tiền ra ngoài.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.model_base import Money, TimestampMixin, uuid_pk
from app.database import Base
from app.domains.approvals.constants import ApprovalKind, ApprovalStatus

JSONType = JSON().with_variant(JSONB(), "postgresql")


class ApprovalRequest(Base, TimestampMixin):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_status_kind", "status", "kind"),
        Index("ix_approval_requests_expires", "expires_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[ApprovalKind] = mapped_column(
        Enum(ApprovalKind, name="approval_kind"), nullable=False
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status"),
        default=ApprovalStatus.PENDING,
        nullable=False,
    )

    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    # Người tạo và người duyệt PHẢI khác nhau — ràng buộc ở service, có test chốt.
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Quá hạn tự huỷ: một đề nghị chi tiền nằm chờ vài tuần rồi được duyệt trong bối cảnh đã
    # khác hẳn là cách tạo ra sai sót đắt tiền.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
