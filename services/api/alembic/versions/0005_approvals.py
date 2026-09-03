"""Maker-checker: bảng approval_requests

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

approval_kind = sa.Enum(
    "payout",
    "escrow_refund",
    "fare_adjustment",
    "fraud_penalty",
    "refund",
    name="approval_kind",
)
approval_status = sa.Enum(
    "pending", "approved", "rejected", "expired", "cancelled", name="approval_status"
)


def upgrade() -> None:
    bind = op.get_bind()
    approval_kind.create(bind, checkfirst=True)
    approval_status.create(bind, checkfirst=True)

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", approval_kind, nullable=False),
        sa.Column("status", approval_status, nullable=False, server_default="pending"),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(12, 0), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "requested_by",
            sa.Uuid(),
            sa.ForeignKey("staff_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "decided_by",
            sa.Uuid(),
            sa.ForeignKey("staff_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_approval_requests_requested_by", "approval_requests", ["requested_by"])
    op.create_index("ix_approval_requests_decided_by", "approval_requests", ["decided_by"])
    op.create_index("ix_approval_requests_status_kind", "approval_requests", ["status", "kind"])
    op.create_index("ix_approval_requests_expires", "approval_requests", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_approval_requests_expires", table_name="approval_requests")
    op.drop_index("ix_approval_requests_status_kind", table_name="approval_requests")
    op.drop_index("ix_approval_requests_decided_by", table_name="approval_requests")
    op.drop_index("ix_approval_requests_requested_by", table_name="approval_requests")
    op.drop_table("approval_requests")

    bind = op.get_bind()
    approval_status.drop(bind, checkfirst=True)
    approval_kind.drop(bind, checkfirst=True)
