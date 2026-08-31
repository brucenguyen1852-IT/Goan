"""Model trips + trip_gps_logs (SPEC 3.3, 3.4)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import TimeBand, TripStatus
from app.core.model_base import Money, TimestampMixin, uuid_pk
from app.database import Base


class Trip(Base, TimestampMixin):
    __tablename__ = "trips"
    __table_args__ = (
        Index("ix_trips_status_requested_at", "status", "requested_at"),
        Index("ix_trips_driver_id", "driver_id"),
        Index("ix_trips_rider_id", "rider_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    rider_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    status: Mapped[TripStatus] = mapped_column(
        Enum(TripStatus, name="trip_status"), default=TripStatus.REQUESTED, nullable=False
    )

    pickup_lat: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_lng: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dropoff_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropoff_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropoff_address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    driver_to_pickup_distance_km: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True
    )
    route_polyline: Mapped[str | None] = mapped_column(Text, nullable=True)
    optimal_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    time_band: Mapped[TimeBand] = mapped_column(
        Enum(TimeBand, name="time_band"), default=TimeBand.NORMAL, nullable=False
    )

    estimated_fare: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    final_fare: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pickup_surcharge: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    platform_commission: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    driver_payout: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    insurance_fee: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    cancellation_fee: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    # Trợ cấp vùng mới lấy từ ngân sách marketing, KHÔNG trừ vào payout/commission (SPEC 6.4)
    pickup_surcharge_subsidized: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )

    qr_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    restaurant_partner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("partners.id"), nullable=True
    )
    insurance_voided: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Idempotency cho POST /trips và /complete (SPEC 13)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)


class TripGpsLog(Base):
    __tablename__ = "trip_gps_logs"
    __table_args__ = (Index("ix_trip_gps_logs_trip_recorded", "trip_id", "recorded_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    trip_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
