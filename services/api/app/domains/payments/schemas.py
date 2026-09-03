import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import WalletTransactionType


class WalletOut(BaseModel):
    driver_id: uuid.UUID
    available_balance: Decimal
    pending_balance: Decimal
    updated_at: datetime


class WalletTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trip_id: uuid.UUID | None
    type: WalletTransactionType
    amount: Decimal
    available_at: datetime | None
    released: bool
    created_at: datetime


class WithdrawRequest(BaseModel):
    amount: Decimal = Field(gt=0)


class WithdrawResponse(BaseModel):
    amount: Decimal
    available_balance: Decimal


class ReconciliationReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_date: date
    total_trips: int
    total_final_fare: Decimal
    total_payments: Decimal
    total_driver_payout: Decimal
    total_wallet_credit: Decimal
    total_escrow_accrual: Decimal
    total_cancellation_fee: Decimal
    fare_payment_diff: Decimal
    payout_wallet_diff: Decimal
    balanced: bool
