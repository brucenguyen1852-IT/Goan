import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PricingRule(Base):
    """Cấu hình bảng giá — Ops chỉnh từ Admin dashboard, KHÔNG hard-code trong code."""

    __tablename__ = "pricing_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time_band: Mapped[str] = mapped_column(String(20), nullable=False)  # normal/night/peak
    base_fee: Mapped[int] = mapped_column(Integer, nullable=False)
    per_km: Mapped[int] = mapped_column(Integer, nullable=False)
    per_min: Mapped[int] = mapped_column(Integer, nullable=False)
    min_fare: Mapped[int] = mapped_column(Integer, nullable=False)
    far_pickup_fee: Mapped[int] = mapped_column(Integer, default=20_000)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
