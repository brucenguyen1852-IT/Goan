import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PartnerType(str, enum.Enum):
    RESTAURANT = "restaurant"
    HOTEL = "hotel"
    INSURANCE = "insurance"


class Partner(Base):
    __tablename__ = "partners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[PartnerType] = mapped_column(Enum(PartnerType), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    commission_rate: Mapped[float] = mapped_column(Numeric(4, 3), default=0.05)  # 0.03 - 0.07
    qr_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
