import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FraudFlag(Base):
    """Ghi nhận nghi vấn gian lận — quét bởi Anti-Fraud Engine sau mỗi chuyến,
    Ops review thủ công qua Admin dashboard."""

    __tablename__ = "fraud_flags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"))
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("driver_profiles.id"))
    rule_code: Mapped[str] = mapped_column(String(50))  # e.g. ROUTE_DEVIATION, GHOST_TRIP, OFF_APP_PAYMENT
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # low/medium/high
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/reviewed/confirmed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
