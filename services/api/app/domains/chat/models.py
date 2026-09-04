"""Hội thoại, thành viên, tin nhắn, tệp đính kèm (tài liệu phân định §7) — P2-01.

Ba quyết định về cấu trúc, đều xuất phát từ chuyện đã xảy ra ở các hệ thống chat thật:

1. **`client_msg_id` là duy nhất trong một hội thoại.** Mạng di động Việt Nam chập chờn: app
   gửi tin, mất sóng trước khi nhận phản hồi, người dùng bấm gửi lại. Không có ràng buộc này
   thì khách thấy tin của mình hiện hai lần và nghĩ hệ thống hỏng.

2. **Người gửi tách làm hai cột** (`sender_user_id` cho khách/tài xế, `sender_staff_id` cho
   CSKH). Nhét chung một cột thì mất khoá ngoại, và mất khoá ngoại nghĩa là vài tháng sau
   không ai chắc dòng đó là khách hay nhân viên nữa.

3. **Rời hội thoại là ghi `left_at`, không xoá dòng.** Khiếu nại xảy ra sau vài tuần, và câu
   hỏi đầu tiên luôn là "lúc đó ai đang ở trong cuộc trò chuyện này".
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.model_base import TimestampMixin, pg_enum, uuid_pk
from app.database import Base
from app.domains.chat.constants import (
    ConversationKind,
    ConversationStatus,
    MemberRole,
    MessageKind,
)


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_trip", "trip_id"),
        Index("ix_conversations_status_kind", "status", "kind"),
        Index("ix_conversations_last_message", "last_message_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[ConversationKind] = mapped_column(
        pg_enum(ConversationKind, "conversation_kind"), nullable=False
    )
    status: Mapped[ConversationStatus] = mapped_column(
        pg_enum(ConversationStatus, "conversation_status"),
        default=ConversationStatus.OPEN,
        nullable=False,
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Sắp xếp hàng đợi CSKH theo tin mới nhất; cập nhật mỗi lần có tin để khỏi phải JOIN đếm.
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    members: Mapped[list["ConversationMember"]] = relationship(
        back_populates="conversation", lazy="selectin"
    )


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    __table_args__ = (
        Index("ix_conversation_members_user", "user_id"),
        Index("ix_conversation_members_staff", "staff_user_id"),
        Index("ix_conversation_members_conv", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    staff_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[MemberRole] = mapped_column(pg_enum(MemberRole, "member_role"), nullable=False)

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Rời đi thì ghi mốc, KHÔNG xoá dòng: khiếu nại đến sau vài tuần và câu hỏi đầu tiên luôn
    # là "lúc đó ai đang ở trong cuộc trò chuyện này".
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_read_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="members")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Khử trùng: gửi lại cùng client_msg_id không tạo tin thứ hai.
        UniqueConstraint("conversation_id", "client_msg_id", name="uq_message_client_id"),
        # Phân trang con trỏ đọc ngược theo thời gian.
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
        Index("ix_messages_flagged", "flagged_off_app"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[MessageKind] = mapped_column(
        pg_enum(MessageKind, "message_kind"), default=MessageKind.TEXT, nullable=False
    )

    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    sender_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)
    client_msg_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Nghi vấn thanh toán ngoài app: CHỈ gắn cờ, không chặn tin. Chặn nhầm một tin nhắn thật
    # còn tệ hơn bỏ lỡ một tin đáng ngờ — người dùng sẽ chuyển sang Zalo và mất luôn dấu vết.
    flagged_off_app: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flag_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Ẩn danh hoá sau hạn lưu trữ (P2-20) thay vì xoá: giữ được thống kê, mất nội dung.
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Mốc thời gian sinh ở PYTHON, không dùng func.now(): trên Postgres `now()` trả về thời
    # điểm bắt đầu transaction nên mọi tin trong cùng một transaction có CÙNG mốc, còn SQLite
    # chỉ có độ phân giải một giây. Cả hai đều làm hỏng thứ tự tin nhắn và làm đồng bộ bù
    # (`after=`) khi thì bỏ sót, khi thì trả trùng. Python cho micro giây và tăng đều.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    attachments: Mapped[list["MessageAttachment"]] = relationship(
        back_populates="message", lazy="selectin"
    )


class MessageAttachment(Base):
    __tablename__ = "message_attachments"
    __table_args__ = (Index("ix_message_attachments_message", "message_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    # Khoá đối tượng trong kho lưu trữ, KHÔNG phải URL công khai: URL đọc được ký hạn 15 phút
    # mỗi lần cần (P2-12), nên lưu URL cố định là tự mở kho ảnh giấy tờ cho cả internet.
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scan_result: Mapped[str | None] = mapped_column(String(50), nullable=True)

    message: Mapped[Message] = relationship(back_populates="attachments")
