"""Ticket hỗ trợ, dấu vết xử lý, mẫu trả lời, trạng thái trực của agent — P2-08…P2-10.

Ba quyết định về cấu trúc, mỗi cái đều là câu trả lời cho một câu hỏi sẽ được hỏi thật:

1. **`code` hiển thị cho khách tách khỏi `id`.** Khách gọi điện đọc "GA-260904-0042", không
   đọc UUID. Không có mã ngắn thì tổng đài phải bắt khách đọc 36 ký tự hex qua điện thoại.

2. **`ticket_events` chỉ ghi thêm.** Câu hỏi "vì sao ticket này nằm 3 ngày mới xong" chỉ trả
   lời được nếu từng bước chuyển tay đều còn dấu vết, kể cả bước làm sai.

3. **`agent_presence` giữ `active_chats` dạng số đếm sẵn.** Hàng đợi CSKH phải chọn người
   trong vài mili-giây mỗi khi có ticket mới; JOIN đếm lại toàn bộ ticket đang mở cho từng
   agent ở mỗi lần phân là cách làm chậm đúng chỗ đông người nhất.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.model_base import TimestampMixin, pg_enum, uuid_pk
from app.database import Base
from app.domains.support.constants import (
    AgentStatus,
    SubjectType,
    TicketCategory,
    TicketEventType,
    TicketPriority,
    TicketStatus,
    TicketTeam,
)

# JSONB trên Postgres, JSON trên SQLite (dev/test) — cùng một khai báo, không rẽ nhánh ở
# chỗ dùng.
JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class SupportTicket(Base, TimestampMixin):
    __tablename__ = "support_tickets"
    __table_args__ = (
        UniqueConstraint("code", name="uq_support_tickets_code"),
        # Hàng đợi CSKH và job quét quá hạn đều lọc theo đúng cặp này.
        Index("ix_support_tickets_status_sla", "status", "sla_due_at"),
        Index("ix_support_tickets_team_status", "team", "status"),
        Index("ix_support_tickets_agent", "assigned_agent_id"),
        Index("ix_support_tickets_subject", "subject_id"),
        Index("ix_support_tickets_trip", "trip_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(24), nullable=False)

    subject_type: Mapped[SubjectType] = mapped_column(
        pg_enum(SubjectType, "ticket_subject_type"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )

    category: Mapped[TicketCategory] = mapped_column(
        pg_enum(TicketCategory, "ticket_category"), nullable=False
    )
    priority: Mapped[TicketPriority] = mapped_column(
        pg_enum(TicketPriority, "ticket_priority"), nullable=False
    )
    status: Mapped[TicketStatus] = mapped_column(
        pg_enum(TicketStatus, "ticket_status"), default=TicketStatus.NEW, nullable=False
    )
    team: Mapped[TicketTeam] = mapped_column(pg_enum(TicketTeam, "ticket_team"), nullable=False)

    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )

    # Ba mốc đo chất lượng CSKH (phân định §7.5). Để rỗng nghĩa là chưa xảy ra, không phải
    # là bằng 0 — nên không được gán mặc định.
    first_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    reopened_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TicketEvent(Base):
    """Dấu vết từng bước xử lý. Chỉ ghi thêm, không sửa không xoá."""

    __tablename__ = "ticket_events"
    __table_args__ = (Index("ix_ticket_events_ticket", "ticket_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False
    )
    # Rỗng = hệ thống tự làm (job quét quá hạn, job trả ticket của agent đã offline).
    actor_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[TicketEventType] = mapped_column(
        pg_enum(TicketEventType, "ticket_event_type"), nullable=False
    )
    payload: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    # Mốc sinh ở Python chứ không dùng func.now(): trên Postgres now() trả về thời điểm bắt
    # đầu transaction, nên nhiều sự kiện ghi trong cùng một transaction sẽ trùng mốc và không
    # còn xếp được thứ tự — đúng thứ mà bảng dấu vết này tồn tại để làm.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class CannedResponse(Base, TimestampMixin):
    """Mẫu trả lời theo đội, gọi bằng gõ tắt `/hoantien` (P2-10)."""

    __tablename__ = "canned_responses"
    __table_args__ = (
        UniqueConstraint("team", "shortcut", name="uq_canned_team_shortcut"),
        Index("ix_canned_responses_team", "team", "is_active"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    team: Mapped[TicketTeam] = mapped_column(pg_enum(TicketTeam, "ticket_team"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    shortcut: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AgentPresence(Base, TimestampMixin):
    """Trạng thái trực của một agent. Một dòng cho mỗi nhân sự CSKH."""

    __tablename__ = "agent_presence"
    __table_args__ = (
        UniqueConstraint("agent_id", name="uq_agent_presence_agent"),
        Index("ix_agent_presence_pick", "team", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False
    )
    team: Mapped[TicketTeam] = mapped_column(pg_enum(TicketTeam, "ticket_team"), nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        pg_enum(AgentStatus, "agent_status"), default=AgentStatus.OFFLINE, nullable=False
    )
    active_chats: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_chats: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Mốc cuối cùng agent còn dấu hiệu sống. Job bàn giao ca dựa vào đây.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
