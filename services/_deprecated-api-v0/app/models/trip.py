import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TripStatus(str, enum.Enum):
    REQUESTED = "requested"
    MATCHING = "matching"
    DRIVER_ASSIGNED = "driver_assigned"
    DRIVER_ARRIVING = "driver_arriving"
    QR_VERIFIED = "qr_verified"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    RATED = "rated"
    CANCELLED_BY_CUSTOMER = "cancelled_by_customer"
    CANCELLED_BY_DRIVER = "cancelled_by_driver"
    NO_DRIVER_FOUND = "no_driver_found"


class TimeBand(str, enum.Enum):
    NORMAL = "normal"  # 06h-21h
    NIGHT = "night"  # 21h-05h
    PEAK = "peak"  # cao điểm đặc biệt (lễ tết...)


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver_profiles.id"), nullable=True
    )
    partner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    status: Mapped[TripStatus] = mapped_column(Enum(TripStatus), default=TripStatus.REQUESTED)
    time_band: Mapped[TimeBand] = mapped_column(Enum(TimeBand), default=TimeBand.NORMAL)

    # Toạ độ dạng geography(Point) — dùng cho query khoảng cách/bán kính qua PostGIS
    pickup_geo = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    dropoff_geo = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    pickup_address: Mapped[str] = mapped_column(String(255))
    dropoff_address: Mapped[str] = mapped_column(String(255))

    distance_km: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)

    base_fare: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_fare: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_fare: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surcharge_far_pickup: Mapped[int] = mapped_column(Integer, default=0)
    total_fare: Mapped[int | None] = mapped_column(Integer, nullable=True)

    route_polyline_actual: Mapped[str | None] = mapped_column(String, nullable=True)
    route_polyline_optimal: Mapped[str | None] = mapped_column(String, nullable=True)
    route_deviation_ratio: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    qr_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
