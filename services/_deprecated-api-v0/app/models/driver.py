import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DriverOnlineStatus(str, enum.Enum):
    OFFLINE = "offline"
    ONLINE_IDLE = "online_idle"
    ON_TRIP = "on_trip"
    SUSPENDED = "suspended"


class EscrowStatus(str, enum.Enum):
    ACCUMULATING = "accumulating"  # đang trích 15%/chuyến
    FULL = "full"  # đã đủ định mức, không trích nữa
    REFUNDING = "refunding"  # đang trong quy trình hoàn trả 45-60 ngày
    REFUNDED = "refunded"


class DriverProfile(Base):
    __tablename__ = "driver_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)

    license_number: Mapped[str] = mapped_column(String(30), nullable=False)
    license_class: Mapped[str] = mapped_column(String(10), nullable=False)  # B1, B2, C...
    years_experience: Mapped[int] = mapped_column(Integer, default=0)

    ekyc_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/verified/rejected
    online_status: Mapped[DriverOnlineStatus] = mapped_column(
        Enum(DriverOnlineStatus), default=DriverOnlineStatus.OFFLINE
    )

    rating_avg: Mapped[float] = mapped_column(Numeric(3, 2), default=5.00)
    total_trips: Mapped[int] = mapped_column(Integer, default=0)

    escrow_balance: Mapped[int] = mapped_column(Integer, default=0)  # VND
    escrow_target: Mapped[int] = mapped_column(Integer, default=4_000_000)  # VND
    escrow_status: Mapped[EscrowStatus] = mapped_column(
        Enum(EscrowStatus), default=EscrowStatus.ACCUMULATING
    )

    # Vị trí cuối cùng biết được — đồng bộ định kỳ từ Redis GEO (nguồn realtime thật)
    # sang đây để phục vụ query báo cáo/fallback matching qua PostGIS.
    last_known_location = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="driver_profile")  # noqa: F821
