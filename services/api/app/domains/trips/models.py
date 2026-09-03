"""Model trips + trip_gps_logs (SPEC 3.3, 3.4)."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import TimeBand, TripActorType, TripEventType, TripStatus
from app.core.model_base import Money, TimestampMixin, pg_enum, uuid_pk
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
    driver_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    status: Mapped[TripStatus] = mapped_column(
        pg_enum(TripStatus, "trip_status"), default=TripStatus.REQUESTED, nullable=False
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
        pg_enum(TimeBand, "time_band"), default=TimeBand.NORMAL, nullable=False
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
    # Tài xế bấm "đã tới điểm đón". Trước đây không có mốc này nên app khách hiển thị
    # "tài xế đã đến" ngay khi tài xế mới nhận chuyến và còn cách 3km.
    driver_arrived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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


class TripEvent(Base):
    """Dấu vết vòng đời của MỘT chuyến (SPEC 4).

    Vì sao tách khỏi `audit_logs`: audit_logs ghi theo request HTTP nên bỏ sót mọi thứ hệ
    thống tự làm — chuyến hết hạn matching do Celery beat, tài xế bị cờ gian lận, trạng thái
    đổi trong một transaction dài. Khi khách khiếu nại "sao chuyến của tôi bị huỷ", CSKH cần
    một dòng thời gian đầy đủ của chuyến đó, không phải log của các lời gọi API.

    Chỉ ghi thêm, không sửa, không xoá.
    """

    __tablename__ = "trip_events"
    __table_args__ = (Index("ix_trip_events_trip_created", "trip_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    trip_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[TripEventType] = mapped_column(
        pg_enum(TripEventType, "trip_event_type"), nullable=False
    )
    from_status: Mapped[TripStatus | None] = mapped_column(
        pg_enum(TripStatus, "trip_status"), nullable=True
    )
    to_status: Mapped[TripStatus | None] = mapped_column(
        pg_enum(TripStatus, "trip_status"), nullable=True
    )
    actor_type: Mapped[TripActorType] = mapped_column(
        pg_enum(TripActorType, "trip_actor_type"), default=TripActorType.SYSTEM, nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class TripRating(Base):
    """Khách đánh giá tài xế sau chuyến (SPEC 3.3 — trạng thái cuối `rated`).

    Một chuyến chỉ đánh giá được một lần: ràng buộc UNIQUE trên trip_id, không dựa vào tầng
    ứng dụng kiểm tra — hai request song song sẽ cùng vượt qua kiểm tra ở tầng ứng dụng.
    """

    __tablename__ = "trip_ratings"
    __table_args__ = (Index("ix_trip_ratings_driver", "driver_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    trip_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    rider_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
