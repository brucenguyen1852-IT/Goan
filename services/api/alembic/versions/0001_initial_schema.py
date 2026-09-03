"""Initial schema (SPEC 3)

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

MONEY = sa.Numeric(12, 0)

user_role = sa.Enum("rider", "driver", "admin", name="user_role")
user_status = sa.Enum("active", "suspended", "banned", name="user_status")
online_status = sa.Enum("offline", "online", "on_trip", name="online_status")
escrow_status = sa.Enum("accumulating", "fulfilled", name="escrow_status")
escrow_tx_type = sa.Enum("accrual", "penalty_deduction", "refund", name="escrow_transaction_type")
trip_status = sa.Enum(
    "requested",
    "matching",
    "matched",
    "driver_arriving",
    "qr_verified",
    "in_progress",
    "completed",
    "cancelled_by_rider",
    "cancelled_by_driver",
    "no_driver_found",
    name="trip_status",
)
time_band = sa.Enum("normal", "night", "peak", name="time_band")
fraud_type = sa.Enum(
    "ghost_trip", "route_deviation", "off_app_payment", "driver_swap", name="fraud_type"
)
fraud_detected_by = sa.Enum("system", "report", name="fraud_detected_by")
fraud_severity = sa.Enum("warning", "account_locked", name="fraud_severity")
fraud_review_status = sa.Enum("pending", "cleared", "confirmed", name="fraud_review_status")
partner_type = sa.Enum("restaurant", "hotel", "insurance", name="partner_type")
payment_method = sa.Enum("in_app_card", "in_app_wallet", "cash_disabled", name="payment_method")
payment_status = sa.Enum("pending", "completed", "failed", "refunded", name="payment_status")
wallet_tx_type = sa.Enum(
    "trip_payout", "escrow_hold", "payout_withdrawal", name="wallet_transaction_type"
)


def upgrade() -> None:
    # PostGIS dùng cho truy vấn khoảng cách/bán kính (SPEC 3 note về index GIST).
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("national_id_number", sa.String(255)),
        sa.Column("national_id_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("status", user_status, nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_users_phone", "users", ["phone"])

    op.create_table(
        "driver_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("license_number", sa.String(50), nullable=False),
        sa.Column("license_years_experience", sa.Integer()),
        sa.Column("ekyc_selfie_reference_url", sa.String(500)),
        sa.Column("escrow_balance", MONEY, nullable=False, server_default="0"),
        sa.Column("escrow_target", MONEY, nullable=False, server_default="3000000"),
        sa.Column("escrow_status", escrow_status, nullable=False, server_default="accumulating"),
        sa.Column("online_status", online_status, nullable=False, server_default="offline"),
        sa.Column("current_lat", sa.Float()),
        sa.Column("current_lng", sa.Float()),
        sa.Column("rating_avg", sa.Numeric(3, 2), nullable=False, server_default="5.00"),
        sa.Column("total_trips", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fraud_strikes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_qr_token", sa.String(64)),
        sa.Column("last_selfie_check_at", sa.DateTime(timezone=True)),
        sa.Column("next_selfie_check_at", sa.DateTime(timezone=True)),
        sa.Column("escrow_refund_requested_at", sa.DateTime(timezone=True)),
        sa.Column("escrow_refund_scheduled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_driver_profiles_location", "driver_profiles", ["current_lat", "current_lng"]
    )
    op.create_index("ix_driver_profiles_online_status", "driver_profiles", ["online_status"])
    # Index GIST theo geography(Point) cho truy vấn tài xế gần nhất bằng PostGIS.
    op.execute(
        "CREATE INDEX ix_driver_profiles_geo ON driver_profiles "
        "USING GIST (geography(ST_MakePoint(current_lng, current_lat))) "
        "WHERE current_lat IS NOT NULL AND current_lng IS NOT NULL"
    )

    op.create_table(
        "partners",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("type", partner_type, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("commission_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("qr_code_token", sa.String(64), unique=True),
        sa.Column("contact_info", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("lat", sa.Float()),
        sa.Column("lng", sa.Float()),
        sa.Column("address", sa.String(255)),
        sa.Column("requires_vat_invoice", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "trips",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rider_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("driver_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("status", trip_status, nullable=False, server_default="requested"),
        sa.Column("pickup_lat", sa.Float(), nullable=False),
        sa.Column("pickup_lng", sa.Float(), nullable=False),
        sa.Column("pickup_address", sa.String(255)),
        sa.Column("dropoff_lat", sa.Float()),
        sa.Column("dropoff_lng", sa.Float()),
        sa.Column("dropoff_address", sa.String(255)),
        sa.Column("driver_to_pickup_distance_km", sa.Numeric(6, 2)),
        sa.Column("route_polyline", sa.Text()),
        sa.Column("optimal_distance_km", sa.Numeric(6, 2)),
        sa.Column("time_band", time_band, nullable=False, server_default="normal"),
        sa.Column("estimated_fare", MONEY),
        sa.Column("final_fare", MONEY),
        sa.Column("distance_km", sa.Numeric(6, 2)),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("pickup_surcharge", MONEY, nullable=False, server_default="0"),
        sa.Column("platform_commission", MONEY),
        sa.Column("driver_payout", MONEY),
        sa.Column("insurance_fee", MONEY),
        sa.Column("cancellation_fee", MONEY, nullable=False, server_default="0"),
        sa.Column("pickup_surcharge_subsidized", MONEY, nullable=False, server_default="0"),
        sa.Column("qr_verified_at", sa.DateTime(timezone=True)),
        sa.Column("requested_at", sa.DateTime(timezone=True)),
        sa.Column("matched_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancellation_reason", sa.String(255)),
        sa.Column("restaurant_partner_id", sa.Uuid(), sa.ForeignKey("partners.id")),
        sa.Column("insurance_voided", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("idempotency_key", sa.String(64), unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_trips_status_requested_at", "trips", ["status", "requested_at"])
    op.create_index("ix_trips_driver_id", "trips", ["driver_id"])
    op.create_index("ix_trips_rider_id", "trips", ["rider_id"])

    op.create_table(
        "trip_gps_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "trip_id", sa.Uuid(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trip_gps_logs_trip_recorded", "trip_gps_logs", ["trip_id", "recorded_at"])

    op.create_table(
        "pricing_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("time_band", time_band, nullable=False),
        sa.Column("base_fee", MONEY, nullable=False),
        sa.Column("per_km", MONEY, nullable=False),
        sa.Column("per_minute", MONEY, nullable=False),
        sa.Column("min_fare", MONEY, nullable=False),
        sa.Column("take_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("driver_share_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "peak_periods",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_peak_periods_range", "peak_periods", ["start_at", "end_at"])

    op.create_table(
        "escrow_transactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("driver_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id")),
        sa.Column("type", escrow_tx_type, nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("balance_after", MONEY, nullable=False),
        sa.Column("note", sa.String(255)),
        sa.Column("scheduled_payout_date", sa.DateTime(timezone=True)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_escrow_tx_driver_created", "escrow_transactions", ["driver_id", "created_at"]
    )

    op.create_table(
        "fraud_incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id")),
        sa.Column("driver_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("fraud_type", fraud_type, nullable=False),
        sa.Column("detected_by", fraud_detected_by, nullable=False),
        sa.Column("severity", fraud_severity, nullable=False),
        sa.Column("penalty_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_fraud_incidents_driver_created", "fraud_incidents", ["driver_id", "created_at"]
    )

    op.create_table(
        "fraud_review_queue",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("driver_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("signal_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", fraud_review_status, nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "driver_online_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("driver_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "partner_commissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("partner_id", sa.Uuid(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "satellite_zones",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("partner_id", sa.Uuid(), sa.ForeignKey("partners.id")),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("radius_m", sa.Integer(), nullable=False, server_default="1500"),
        sa.Column("active_hours", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_new_zone", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "marketing_subsidies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("zone_id", sa.Uuid(), sa.ForeignKey("satellite_zones.id")),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("note", sa.String(255)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("rider_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("method", payment_method, nullable=False, server_default="in_app_card"),
        sa.Column("status", payment_status, nullable=False, server_default="pending"),
        sa.Column("gateway_reference", sa.String(120)),
        sa.Column("idempotency_key", sa.String(64), unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_payments_trip", "payments", ["trip_id"])

    op.create_table(
        "driver_wallets",
        sa.Column("driver_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("available_balance", MONEY, nullable=False, server_default="0"),
        sa.Column("pending_balance", MONEY, nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("driver_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id")),
        sa.Column("type", wallet_tx_type, nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True)),
        sa.Column("released", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_wallet_tx_driver_created", "wallet_transactions", ["driver_id", "created_at"]
    )

    op.create_table(
        "reconciliation_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False, unique=True),
        sa.Column("total_trips", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_final_fare", MONEY, nullable=False, server_default="0"),
        sa.Column("total_payments", MONEY, nullable=False, server_default="0"),
        sa.Column("total_driver_payout", MONEY, nullable=False, server_default="0"),
        sa.Column("total_wallet_credit", MONEY, nullable=False, server_default="0"),
        sa.Column("total_escrow_accrual", MONEY, nullable=False, server_default="0"),
        sa.Column("fare_payment_diff", MONEY, nullable=False, server_default="0"),
        sa.Column("payout_wallet_diff", MONEY, nullable=False, server_default="0"),
        sa.Column("balanced", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    for table in (
        "reconciliation_reports",
        "wallet_transactions",
        "driver_wallets",
        "payments",
        "marketing_subsidies",
        "satellite_zones",
        "partner_commissions",
        "driver_online_sessions",
        "fraud_review_queue",
        "fraud_incidents",
        "escrow_transactions",
        "peak_periods",
        "pricing_rules",
        "trip_gps_logs",
        "trips",
        "partners",
        "driver_profiles",
        "users",
    ):
        op.drop_table(table)

    for enum_type in (
        wallet_tx_type,
        payment_status,
        payment_method,
        partner_type,
        fraud_review_status,
        fraud_severity,
        fraud_detected_by,
        fraud_type,
        time_band,
        trip_status,
        escrow_tx_type,
        escrow_status,
        online_status,
        user_status,
        user_role,
    ):
        enum_type.drop(op.get_bind(), checkfirst=True)
