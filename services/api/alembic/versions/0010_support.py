"""Ticket hỗ trợ, dấu vết xử lý, mẫu trả lời, trực ca (P2-08…P2-10)

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

ticket_subject_type = sa.Enum("rider", "driver", name="ticket_subject_type")
ticket_category = sa.Enum(
    "payment",
    "fraud",
    "safety",
    "app_issue",
    "driver_conduct",
    "rider_conduct",
    "other",
    name="ticket_category",
)
ticket_priority = sa.Enum("low", "normal", "high", "urgent", name="ticket_priority")
ticket_status = sa.Enum(
    "new", "assigned", "waiting_customer", "escalated", "resolved", "closed", name="ticket_status"
)
ticket_team = sa.Enum("cs", "risk", "finance", "driver_ops", name="ticket_team")
agent_status = sa.Enum("available", "busy", "away", "offline", name="agent_status")
ticket_event_type = sa.Enum(
    "created",
    "assigned",
    "first_response",
    "transferred",
    "escalated",
    "resolved",
    "reopened",
    "released",
    name="ticket_event_type",
)

# Tham chiếu kiểu đã tạo — xem ghi chú ở 0003. `ticket_team` xuất hiện ở ba bảng, nên nếu để
# sa.Enum thì lệnh CREATE TYPE chạy ba lần và migration ngã ngay ở bảng thứ hai.
subject_type_ref = postgresql.ENUM(name="ticket_subject_type", create_type=False)
category_ref = postgresql.ENUM(name="ticket_category", create_type=False)
priority_ref = postgresql.ENUM(name="ticket_priority", create_type=False)
status_ref = postgresql.ENUM(name="ticket_status", create_type=False)
team_ref = postgresql.ENUM(name="ticket_team", create_type=False)
agent_status_ref = postgresql.ENUM(name="agent_status", create_type=False)
event_type_ref = postgresql.ENUM(name="ticket_event_type", create_type=False)

# JSONB trên Postgres, JSON trên SQLite — cùng khai báo với model.
json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

ALL_ENUMS = (
    ticket_subject_type,
    ticket_category,
    ticket_priority,
    ticket_status,
    ticket_team,
    agent_status,
    ticket_event_type,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ALL_ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("subject_type", subject_type_ref, nullable=False),
        sa.Column(
            "subject_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id", ondelete="SET NULL")),
        sa.Column(
            "conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="SET NULL")
        ),
        sa.Column("category", category_ref, nullable=False),
        sa.Column("priority", priority_ref, nullable=False),
        sa.Column("status", status_ref, nullable=False, server_default="new"),
        sa.Column("team", team_ref, nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column(
            "assigned_agent_id", sa.Uuid(), sa.ForeignKey("staff_users.id", ondelete="SET NULL")
        ),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reopened_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code", name="uq_support_tickets_code"),
    )
    op.create_index("ix_support_tickets_status_sla", "support_tickets", ["status", "sla_due_at"])
    op.create_index("ix_support_tickets_team_status", "support_tickets", ["team", "status"])
    op.create_index("ix_support_tickets_agent", "support_tickets", ["assigned_agent_id"])
    op.create_index("ix_support_tickets_subject", "support_tickets", ["subject_id"])
    op.create_index("ix_support_tickets_trip", "support_tickets", ["trip_id"])

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Uuid(),
            sa.ForeignKey("support_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_staff_id", sa.Uuid(), sa.ForeignKey("staff_users.id", ondelete="SET NULL")
        ),
        sa.Column("event_type", event_type_ref, nullable=False),
        sa.Column("payload", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_events_ticket", "ticket_events", ["ticket_id", "created_at"])

    op.create_table(
        "canned_responses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("team", team_ref, nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("shortcut", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("team", "shortcut", name="uq_canned_team_shortcut"),
    )
    op.create_index("ix_canned_responses_team", "canned_responses", ["team", "is_active"])

    op.create_table(
        "agent_presence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("staff_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team", team_ref, nullable=False),
        sa.Column("status", agent_status_ref, nullable=False, server_default="offline"),
        sa.Column("active_chats", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_chats", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("agent_id", name="uq_agent_presence_agent"),
    )
    op.create_index("ix_agent_presence_pick", "agent_presence", ["team", "status"])


def downgrade() -> None:
    op.drop_index("ix_agent_presence_pick", table_name="agent_presence")
    op.drop_table("agent_presence")

    op.drop_index("ix_canned_responses_team", table_name="canned_responses")
    op.drop_table("canned_responses")

    op.drop_index("ix_ticket_events_ticket", table_name="ticket_events")
    op.drop_table("ticket_events")

    op.drop_index("ix_support_tickets_trip", table_name="support_tickets")
    op.drop_index("ix_support_tickets_subject", table_name="support_tickets")
    op.drop_index("ix_support_tickets_agent", table_name="support_tickets")
    op.drop_index("ix_support_tickets_team_status", table_name="support_tickets")
    op.drop_index("ix_support_tickets_status_sla", table_name="support_tickets")
    op.drop_table("support_tickets")

    bind = op.get_bind()
    for enum in reversed(ALL_ENUMS):
        enum.drop(bind, checkfirst=True)
