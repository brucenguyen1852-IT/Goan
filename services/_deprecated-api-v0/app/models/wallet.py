import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WalletType(str, enum.Enum):
    DRIVER_EARNING = "driver_earning"
    DRIVER_ESCROW = "driver_escrow"
    PLATFORM_REVENUE = "platform_revenue"
    PARTNER_COMMISSION = "partner_commission"
    INSURANCE_FEE = "insurance_fee"


class TxDirection(str, enum.Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class WalletTransaction(Base):
    """Bút toán ledger — KHÔNG BAO GIỜ update/xóa, chỉ insert thêm.
    Số dư ví luôn được TÍNH TOÁN từ tổng các bút toán, không lưu trực tiếp,
    để đảm bảo có thể audit đầy đủ (yêu cầu bắt buộc cho gọi vốn Series A)."""

    __tablename__ = "wallet_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_type: Mapped[WalletType] = mapped_column(Enum(WalletType), nullable=False)
    # owner_id: driver_profile.id nếu wallet_type liên quan tài xế, partner.id nếu partner, None nếu platform
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    trip_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # VND, luôn dương
    direction: Mapped[TxDirection] = mapped_column(Enum(TxDirection), nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DriverDebt(Base):
    """Công nợ hoa hồng khi tài xế thu tiền mặt trực tiếp từ khách."""

    __tablename__ = "driver_debts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("driver_profiles.id"))
    trip_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="cash_commission")
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/cleared
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Payout(Base):
    __tablename__ = "payouts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("driver_profiles.id"))
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    bank_txn_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
