"""Hoàn thiện vòng đời chuyến: trip_events, trip_ratings, mốc tài xế đã tới, trạng thái rated

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

trip_event_type = sa.Enum(
    "created",
    "matching_started",
    "offer_sent",
    "driver_accepted",
    "driver_assigned_manually",
    "driver_arrived",
    "qr_verified",
    "gps_recorded",
    "completed",
    "rated",
    "cancelled",
    "no_driver_found",
    "matching_retried",
    "fraud_flagged",
    name="trip_event_type",
)
trip_actor_type = sa.Enum("rider", "driver", "admin", "system", name="trip_actor_type")

# Tham chiếu tới kiểu ĐÃ được tạo ở trên. Bắt buộc dùng postgresql.ENUM(create_type=False):
# sa.Enum(create_type=False) im lặng bỏ qua cờ này — dialect_impl vẫn create_type=True — nên
# CREATE TABLE sẽ phát lại CREATE TYPE và ngã với "type ... already exists".
trip_event_type_ref = postgresql.ENUM(name="trip_event_type", create_type=False)
trip_actor_type_ref = postgresql.ENUM(name="trip_actor_type", create_type=False)
trip_status_ref = postgresql.ENUM(name="trip_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    # Postgres dùng enum gốc nên phải ALTER TYPE để thêm giá trị; SQLite lưu enum bằng
    # VARCHAR + CHECK nên không cần bước này.
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE trip_status ADD VALUE IF NOT EXISTS 'rated'")

    trip_event_type.create(bind, checkfirst=True)
    trip_actor_type.create(bind, checkfirst=True)

    op.add_column(
        "trips", sa.Column("driver_arrived_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("trips", sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "reconciliation_reports",
        sa.Column(
            "total_cancellation_fee",
            sa.Numeric(12, 0),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "trip_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "trip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", trip_event_type_ref, nullable=False),
        sa.Column("from_status", trip_status_ref, nullable=True),
        sa.Column(
            "to_status",
            trip_status_ref,
            nullable=True,
        ),
        sa.Column("actor_type", trip_actor_type_ref, nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trip_events_trip_created", "trip_events", ["trip_id", "created_at"])

    op.create_table(
        "trip_ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "trip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trips.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "rider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "driver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name="ck_trip_ratings_stars"),
    )
    op.create_index("ix_trip_ratings_driver", "trip_ratings", ["driver_id"])


def downgrade() -> None:
    op.drop_index("ix_trip_ratings_driver", table_name="trip_ratings")
    op.drop_table("trip_ratings")
    op.drop_index("ix_trip_events_trip_created", table_name="trip_events")
    op.drop_table("trip_events")
    op.drop_column("reconciliation_reports", "total_cancellation_fee")
    op.drop_column("trips", "rated_at")
    op.drop_column("trips", "driver_arrived_at")

    bind = op.get_bind()
    trip_actor_type.drop(bind, checkfirst=True)
    trip_event_type.drop(bind, checkfirst=True)
    # Giá trị 'rated' của trip_status không gỡ được bằng ALTER TYPE trên Postgres.
    # Muốn gỡ hẳn phải tạo lại type — cố ý không làm ở đây vì rủi ro cao hơn lợi ích.
