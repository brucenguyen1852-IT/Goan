"""partners, partner_commissions, satellite_zones, marketing_subsidies (SPEC 3.7, 6.4, 10)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import PartnerType
from app.core.model_base import Money, TimestampMixin, uuid_pk
from app.database import Base


class Partner(Base, TimestampMixin):
    __tablename__ = "partners"

    id: Mapped[uuid.UUID] = uuid_pk()
    type: Mapped[PartnerType] = mapped_column(Enum(PartnerType, name="partner_type"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"), nullable=False
    )  # % hoa hồng nhà hàng (3-7%) hoặc % phí bảo hiểm (5-8%)
    qr_code_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    contact_info: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requires_vat_invoice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PartnerCommission(Base):
    __tablename__ = "partner_commissions"

    id: Mapped[uuid.UUID] = uuid_pk()
    partner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("partners.id"), nullable=False)
    trip_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("trips.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SatelliteZone(Base, TimestampMixin):
    """Khu vực khuyến khích tài xế túc trực giờ cao điểm (SPEC 6.4)."""

    __tablename__ = "satellite_zones"

    id: Mapped[uuid.UUID] = uuid_pk()
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("partners.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    radius_m: Mapped[int] = mapped_column(Integer, default=1500, nullable=False)
    active_hours: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_new_zone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MarketingSubsidy(Base):
    """Trợ cấp vùng mới — hạch toán riêng, không trừ driver_payout/platform_commission (SPEC 6.4)."""

    __tablename__ = "marketing_subsidies"

    id: Mapped[uuid.UUID] = uuid_pk()
    trip_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("trips.id"), nullable=False)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("satellite_zones.id"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
