"""Schema cho maker–checker."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domains.approvals.constants import ApprovalKind, ApprovalStatus


class ApprovalCreateRequest(BaseModel):
    kind: ApprovalKind
    reason: str = Field(min_length=10, max_length=1000, description="Vì sao cần thao tác này")
    amount: Decimal | None = Field(default=None, ge=0, description="Số tiền, nếu có")
    resource_type: str | None = Field(default=None, max_length=64)
    resource_id: str | None = Field(default=None, max_length=64)
    payload: dict | None = None


class ApprovalDecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ApprovalKind
    status: ApprovalStatus
    amount: Decimal | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    reason: str
    requested_by: uuid.UUID
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    expires_at: datetime
    created_at: datetime
