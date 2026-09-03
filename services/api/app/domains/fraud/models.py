"""fraud_incidents + fraud_review_queue (SPEC 3.6, 7)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import FraudDetectedBy, FraudReviewStatus, FraudSeverity, FraudType
from app.core.model_base import Money, uuid_pk
from app.database import Base


class FraudIncident(Base):
    __tablename__ = "fraud_incidents"
    __table_args__ = (Index("ix_fraud_incidents_driver_created", "driver_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    trip_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("trips.id"), nullable=True)
    driver_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    fraud_type: Mapped[FraudType] = mapped_column(
        Enum(FraudType, name="fraud_type"), nullable=False
    )
    detected_by: Mapped[FraudDetectedBy] = mapped_column(
        Enum(FraudDetectedBy, name="fraud_detected_by"), nullable=False
    )
    severity: Mapped[FraudSeverity] = mapped_column(
        Enum(FraudSeverity, name="fraud_severity"), nullable=False
    )
    penalty_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FraudReviewQueue(Base):
    """Tín hiệu nghi ngờ (vd: tỷ lệ online/đơn bất thường) — admin review thủ công,
    KHÔNG tự động phạt (SPEC 7.3)."""

    __tablename__ = "fraud_review_queue"

    id: Mapped[uuid.UUID] = uuid_pk()
    driver_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    signal_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[FraudReviewStatus] = mapped_column(
        Enum(FraudReviewStatus, name="fraud_review_status"),
        default=FraudReviewStatus.PENDING,
        nullable=False,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DriverOnlineSession(Base):
    """Ghi nhận số giờ online để tính tỷ lệ online/đơn (SPEC 7.3)."""

    __tablename__ = "driver_online_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    driver_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
