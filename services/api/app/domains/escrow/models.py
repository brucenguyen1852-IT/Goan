"""escrow_transactions (SPEC 3.5, 8) — audit trail đủ để đối soát với tài khoản ngân hàng tách bạch."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import EscrowTransactionType
from app.core.model_base import Money, pg_enum, uuid_pk
from app.database import Base


class EscrowTransaction(Base):
    __tablename__ = "escrow_transactions"
    __table_args__ = (Index("ix_escrow_tx_driver_created", "driver_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    driver_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("trips.id"), nullable=True)
    type: Mapped[EscrowTransactionType] = mapped_column(
        pg_enum(EscrowTransactionType, "escrow_transaction_type"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Money, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_payout_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
