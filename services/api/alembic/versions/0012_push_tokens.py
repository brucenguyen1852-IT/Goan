"""Token thiết bị nhận push (P2-13)

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

device_platform = sa.Enum("android", "ios", "web", name="device_platform")
platform_ref = postgresql.ENUM(name="device_platform", create_type=False)


def upgrade() -> None:
    device_platform.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "push_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("platform", platform_ref, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Một token chỉ thuộc về đúng một dòng: cùng máy đăng nhập tài khoản khác thì dòng cũ
        # đổi chủ, chứ không sinh dòng thứ hai rồi gửi tin của cả hai người vào một màn hình.
        sa.UniqueConstraint("token", name="uq_push_tokens_token"),
    )
    op.create_index("ix_push_tokens_user", "push_tokens", ["user_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_push_tokens_user", table_name="push_tokens")
    op.drop_table("push_tokens")
    device_platform.drop(op.get_bind(), checkfirst=True)
