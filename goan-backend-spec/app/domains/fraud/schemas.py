import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.core.constants import (
    FraudDetectedBy,
    FraudReviewStatus,
    FraudSeverity,
    FraudType,
)


class FraudIncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trip_id: uuid.UUID | None
    driver_id: uuid.UUID
    fraud_type: FraudType
    detected_by: FraudDetectedBy
    severity: FraudSeverity
    penalty_amount: Decimal
    details: dict
    created_at: datetime


class FraudReviewItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    driver_id: uuid.UUID
    reason: str
    signal_score: float
    details: dict
    status: FraudReviewStatus
    created_at: datetime


class ReviewDecision(BaseModel):
    confirmed: bool  # True = xác nhận gian lận -> cảnh cáo/khoá; False = bỏ qua
    trip_id: uuid.UUID | None = None  # chuyến liên quan sẽ bị void bảo hiểm
