"""Tệp đính kèm: gắn vào hội thoại và người tải lên, chưa cần tin nhắn (P2-12)

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dòng tệp được tạo lúc XIN url tải lên, khi chưa có tin nhắn nào. Người dùng chọn ảnh
    # rồi đổi ý là chuyện thường, nên "chưa gắn tin" phải là trạng thái hợp lệ.
    op.alter_column("message_attachments", "message_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("message_attachments", sa.Column("conversation_id", sa.Uuid(), nullable=True))
    op.add_column("message_attachments", sa.Column("uploader_user_id", sa.Uuid(), nullable=True))
    op.add_column("message_attachments", sa.Column("uploader_staff_id", sa.Uuid(), nullable=True))
    op.add_column(
        "message_attachments",
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column(
        "message_attachments",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # Điền hội thoại cho các dòng đã có (nếu có) trước khi siết NOT NULL.
    op.execute(
        "UPDATE message_attachments a SET conversation_id = m.conversation_id "
        "FROM messages m WHERE m.id = a.message_id AND a.conversation_id IS NULL"
    )
    op.execute("DELETE FROM message_attachments WHERE conversation_id IS NULL")
    op.alter_column(
        "message_attachments", "conversation_id", existing_type=sa.Uuid(), nullable=False
    )

    op.create_foreign_key(
        "fk_message_attachments_conversation",
        "message_attachments",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_message_attachments_uploader_user",
        "message_attachments",
        "users",
        ["uploader_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_message_attachments_uploader_staff",
        "message_attachments",
        "staff_users",
        ["uploader_staff_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_message_attachments_conv", "message_attachments", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_message_attachments_conv", table_name="message_attachments")
    op.drop_constraint(
        "fk_message_attachments_uploader_staff", "message_attachments", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_message_attachments_uploader_user", "message_attachments", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_message_attachments_conversation", "message_attachments", type_="foreignkey"
    )
    # Quay lui: dòng chưa gắn tin nhắn không tồn tại được ở lược đồ cũ.
    op.execute("DELETE FROM message_attachments WHERE message_id IS NULL")
    op.drop_column("message_attachments", "updated_at")
    op.drop_column("message_attachments", "created_at")
    op.drop_column("message_attachments", "uploader_staff_id")
    op.drop_column("message_attachments", "uploader_user_id")
    op.drop_column("message_attachments", "conversation_id")
    op.alter_column("message_attachments", "message_id", existing_type=sa.Uuid(), nullable=False)
