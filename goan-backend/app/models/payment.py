import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaymentMethod(str, enum.Enum):
    ONLINE = "online"
    CASH = "cash"


class PaymentGateway(str, enum.Enum):
    VNPAY = "vnpay"
    MOMO = "momo"
    ZALOPAY = "zalopay"
    NONE = "none"


class PaymentStatus(str, enum.Enum):
    PENDING_AUTH = "pending_auth"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    CAPTURE_FAILED = "capture_failed"
    DEBT_PENDING = "debt_pending"
    CASH_DECLARED = "cash_declared"
    SETTLED = "settled"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"), unique=True)

    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod), nullable=False)
    gateway: Mapped[PaymentGateway] = mapped_column(Enum(PaymentGateway), default=PaymentGateway.NONE)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING_AUTH)

    estimated_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gateway_txn_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
