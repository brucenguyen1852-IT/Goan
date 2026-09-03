"""payments, driver_wallets, wallet_transactions, reconciliation_reports (SPEC 3.8, 9)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import PaymentMethod, PaymentStatus, WalletTransactionType
from app.core.model_base import Money, TimestampMixin, pg_enum, uuid_pk
from app.database import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_trip", "trip_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    trip_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("trips.id"), nullable=False)
    rider_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        pg_enum(PaymentMethod, "payment_method"),
        default=PaymentMethod.IN_APP_CARD,
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, "payment_status"), default=PaymentStatus.PENDING, nullable=False
    )
    gateway_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DriverWallet(Base):
    __tablename__ = "driver_wallets"

    driver_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    available_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    pending_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    __table_args__ = (Index("ix_wallet_tx_driver_created", "driver_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    driver_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("trips.id"), nullable=True)
    type: Mapped[WalletTransactionType] = mapped_column(
        pg_enum(WalletTransactionType, "wallet_transaction_type"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # Mốc tiền pending được giải phóng sang available (chống hoàn/huỷ, SPEC 9)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReconciliationReport(Base, TimestampMixin):
    """Báo cáo đối soát hàng ngày (SPEC 9.1)."""

    __tablename__ = "reconciliation_reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    report_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    total_trips: Mapped[int] = mapped_column(default=0, nullable=False)
    total_final_fare: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_payments: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_driver_payout: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )
    total_wallet_credit: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )
    total_escrow_accrual: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )
    # Phí huỷ chuyến muộn: khách trả, tài xế nhận. Không nằm trong final_fare (chuyến bị
    # huỷ nên không có cước) nhưng vẫn là tiền chạy qua hệ thống, phải vào đối soát.
    total_cancellation_fee: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )
    fare_payment_diff: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    payout_wallet_diff: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    balanced: Mapped[bool] = mapped_column(default=True, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
