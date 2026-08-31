import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.core.constants import EscrowStatus, EscrowTransactionType


class EscrowTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trip_id: uuid.UUID | None
    type: EscrowTransactionType
    amount: Decimal
    balance_after: Decimal
    note: str | None
    scheduled_payout_date: datetime | None
    processed_at: datetime | None
    created_at: datetime


class EscrowSummary(BaseModel):
    escrow_balance: Decimal
    escrow_target: Decimal
    escrow_status: EscrowStatus
    refund_requested_at: datetime | None
    refund_scheduled_at: datetime | None
    transactions: list[EscrowTransactionOut]


class RefundRequestResponse(BaseModel):
    amount: Decimal
    scheduled_payout_date: datetime | None
