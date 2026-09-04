"""Hội thoại, thành viên, tin nhắn, tệp đính kèm (P2-01)

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

conversation_kind = sa.Enum("trip", "support", "internal", name="conversation_kind")
conversation_status = sa.Enum("open", "closed", name="conversation_status")
member_role = sa.Enum("rider", "driver", "agent", name="member_role")
message_kind = sa.Enum("text", "image", "system", name="message_kind")

# Tham chiếu kiểu đã tạo — xem ghi chú ở 0003 về việc sa.Enum lặng lẽ tạo lại kiểu.
conversation_kind_ref = postgresql.ENUM(name="conversation_kind", create_type=False)
conversation_status_ref = postgresql.ENUM(name="conversation_status", create_type=False)
member_role_ref = postgresql.ENUM(name="member_role", create_type=False)
message_kind_ref = postgresql.ENUM(name="message_kind", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (conversation_kind, conversation_status, member_role, message_kind):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", conversation_kind_ref, nullable=False),
        sa.Column("status", conversation_status_ref, nullable=False, server_default="open"),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id", ondelete="SET NULL")),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_conversations_trip", "conversations", ["trip_id"])
    op.create_index("ix_conversations_status_kind", "conversations", ["status", "kind"])
    op.create_index("ix_conversations_last_message", "conversations", ["last_message_at"])

    op.create_table(
        "conversation_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("staff_user_id", sa.Uuid(), sa.ForeignKey("staff_users.id", ondelete="CASCADE")),
        sa.Column("role", member_role_ref, nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_read_message_id", sa.Uuid(), nullable=True),
    )
    op.create_index("ix_conversation_members_conv", "conversation_members", ["conversation_id"])
    op.create_index("ix_conversation_members_user", "conversation_members", ["user_id"])
    op.create_index("ix_conversation_members_staff", "conversation_members", ["staff_user_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", message_kind_ref, nullable=False, server_default="text"),
        sa.Column("sender_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "sender_staff_id", sa.Uuid(), sa.ForeignKey("staff_users.id", ondelete="SET NULL")
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("client_msg_id", sa.String(length=64), nullable=True),
        sa.Column("flagged_off_app", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("flag_reason", sa.String(length=200), nullable=True),
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Khử trùng ở tầng DB: kiểm tra ở tầng ứng dụng chỉ giảm số lần chạm tới đây, không
        # thay thế được nó khi hai request chạy song song.
        sa.UniqueConstraint("conversation_id", "client_msg_id", name="uq_message_client_id"),
    )
    op.create_index("ix_messages_conv_created", "messages", ["conversation_id", "created_at"])
    op.create_index("ix_messages_flagged", "messages", ["flagged_off_app"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])

    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_result", sa.String(length=50), nullable=True),
    )
    op.create_index("ix_message_attachments_message", "message_attachments", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_message_attachments_message", table_name="message_attachments")
    op.drop_table("message_attachments")

    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_messages_flagged", table_name="messages")
    op.drop_index("ix_messages_conv_created", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conversation_members_staff", table_name="conversation_members")
    op.drop_index("ix_conversation_members_user", table_name="conversation_members")
    op.drop_index("ix_conversation_members_conv", table_name="conversation_members")
    op.drop_table("conversation_members")

    op.drop_index("ix_conversations_last_message", table_name="conversations")
    op.drop_index("ix_conversations_status_kind", table_name="conversations")
    op.drop_index("ix_conversations_trip", table_name="conversations")
    op.drop_table("conversations")

    bind = op.get_bind()
    for enum in (message_kind, member_role, conversation_status, conversation_kind):
        enum.drop(bind, checkfirst=True)
