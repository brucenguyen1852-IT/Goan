"""Model users + driver_profiles (SPEC 3.1, 3.2)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.core.constants import (
    DriverApprovalStatus,
    EscrowStatus,
    OnlineStatus,
    UserRole,
    UserStatus,
)
from app.core.model_base import Money, TimestampMixin, pg_enum, uuid_pk
from app.database import Base


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False)
    # Lưu dạng đã mã hoá at-rest, không bao giờ log plaintext (SPEC 13)
    national_id_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    national_id_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"), default=UserStatus.ACTIVE, nullable=False
    )

    driver_profile: Mapped["DriverProfile | None"] = relationship(
        back_populates="user", uselist=False, lazy="selectin"
    )


class DriverProfile(Base, TimestampMixin):
    __tablename__ = "driver_profiles"
    __table_args__ = (
        Index("ix_driver_profiles_location", "current_lat", "current_lng"),
        Index("ix_driver_profiles_online_status", "online_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    license_number: Mapped[str] = mapped_column(String(50), nullable=False)
    # Duyệt hồ sơ bởi Driver Ops (P1-10). Trước đây tài xế tạo hồ sơ là chạy được ngay —
    # không có bước người thật nhìn giấy tờ.
    approval_status: Mapped[DriverApprovalStatus] = mapped_column(
        pg_enum(DriverApprovalStatus, "driver_approval_status"),
        default=DriverApprovalStatus.PENDING,
        nullable=False,
    )
    approval_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    license_years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ekyc_selfie_reference_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    escrow_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    escrow_target: Mapped[Decimal] = mapped_column(
        Money, default=settings.ESCROW_DEFAULT_TARGET, nullable=False
    )
    escrow_status: Mapped[EscrowStatus] = mapped_column(
        pg_enum(EscrowStatus, "escrow_status"), default=EscrowStatus.ACCUMULATING, nullable=False
    )

    online_status: Mapped[OnlineStatus] = mapped_column(
        pg_enum(OnlineStatus, "online_status"), default=OnlineStatus.OFFLINE, nullable=False
    )
    current_lat: Mapped[float | None] = mapped_column(nullable=True)
    current_lng: Mapped[float | None] = mapped_column(nullable=True)

    rating_avg: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("5.00"), nullable=False
    )
    total_trips: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fraud_strikes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # QR động: regenerate mỗi lần offline -> online (SPEC 7.1). Không expose ra API công khai.
    active_qr_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_selfie_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_selfie_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escrow_refund_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escrow_refund_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="driver_profile", lazy="selectin")
