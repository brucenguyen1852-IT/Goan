"""Thiết bị tin cậy của nhân sự nội bộ (nhớ 2FA 30 ngày)

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_trusted_devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "staff_user_id",
            sa.Uuid(),
            sa.ForeignKey("staff_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Chỉ lưu hash: đọc trộm được DB cũng không dựng lại được token để dùng.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("device_label", sa.String(length=200), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_staff_trusted_devices_staff_user_id", "staff_trusted_devices", ["staff_user_id"]
    )
    op.create_index(
        "ix_staff_trusted_devices_token_hash",
        "staff_trusted_devices",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_staff_trusted_devices_token_hash", table_name="staff_trusted_devices")
    op.drop_index("ix_staff_trusted_devices_staff_user_id", table_name="staff_trusted_devices")
    op.drop_table("staff_trusted_devices")
