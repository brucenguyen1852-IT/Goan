"""pricing_rules + peak_periods (SPEC 4.1) — cho phép admin chỉnh biểu giá mà không deploy lại."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import TimeBand
from app.core.model_base import Money, TimestampMixin, uuid_pk
from app.database import Base


class PricingRule(Base, TimestampMixin):
    __tablename__ = "pricing_rules"

    id: Mapped[uuid.UUID] = uuid_pk()
    time_band: Mapped[TimeBand] = mapped_column(Enum(TimeBand, name="time_band"), nullable=False)
    base_fee: Mapped[Decimal] = mapped_column(Money, nullable=False)
    per_km: Mapped[Decimal] = mapped_column(Money, nullable=False)
    per_minute: Mapped[Decimal] = mapped_column(Money, nullable=False)
    min_fare: Mapped[Decimal] = mapped_column(Money, nullable=False)
    take_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    driver_share_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PeakPeriod(Base, TimestampMixin):
    """Khung giờ cao điểm đặc biệt (giao thừa, lễ Tết...) — service kiểm tra overlap."""

    __tablename__ = "peak_periods"
    __table_args__ = (Index("ix_peak_periods_range", "start_at", "end_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
