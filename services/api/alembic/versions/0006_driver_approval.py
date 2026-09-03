"""Duyệt hồ sơ tài xế: approval_status + người duyệt

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

approval_status = sa.Enum("pending", "approved", "rejected", name="driver_approval_status")
# Tham chiếu kiểu đã tạo, xem ghi chú ở 0003.
approval_status_ref = postgresql.ENUM(name="driver_approval_status", create_type=False)


def upgrade() -> None:
    approval_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "driver_profiles",
        sa.Column("approval_status", approval_status_ref, nullable=False, server_default="pending"),
    )
    op.add_column(
        "driver_profiles", sa.Column("approval_note", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "driver_profiles", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("driver_profiles", sa.Column("approved_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_driver_profiles_approved_by",
        "driver_profiles",
        "staff_users",
        ["approved_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # Tài xế đang chạy thật trước khi có bước duyệt thì coi như đã được duyệt — nếu để
    # "pending" thì họ bị chặn ngay sau khi deploy.
    op.execute("UPDATE driver_profiles SET approval_status = 'approved'")


def downgrade() -> None:
    op.drop_constraint("fk_driver_profiles_approved_by", "driver_profiles", type_="foreignkey")
    op.drop_column("driver_profiles", "approved_by")
    op.drop_column("driver_profiles", "approved_at")
    op.drop_column("driver_profiles", "approval_note")
    op.drop_column("driver_profiles", "approval_status")
    approval_status.drop(op.get_bind(), checkfirst=True)
