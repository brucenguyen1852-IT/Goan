"""Schema ticket hỗ trợ."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.support.constants import (
    AgentStatus,
    SubjectType,
    TicketCategory,
    TicketEventType,
    TicketPriority,
    TicketStatus,
    TicketTeam,
)


class CreateTicketRequest(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    category: TicketCategory = TicketCategory.OTHER
    # Mức khách tự chọn chỉ là đề nghị: an toàn và tiền luôn được nâng lên (xem
    # `service.effective_priority`), không bao giờ hạ xuống.
    priority: TicketPriority = TicketPriority.NORMAL
    trip_id: uuid.UUID | None = None
    body: str | None = Field(default=None, max_length=4000)


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    subject: str
    subject_type: SubjectType
    subject_id: uuid.UUID
    trip_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    team: TicketTeam
    assigned_agent_id: uuid.UUID | None = None
    first_response_at: datetime | None = None
    resolved_at: datetime | None = None
    sla_due_at: datetime
    reopened_count: int
    resolution_note: str | None = None
    created_at: datetime


class TicketEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: TicketEventType
    actor_staff_id: uuid.UUID | None = None
    payload: dict | None = None
    created_at: datetime


class TransferRequest(BaseModel):
    to_agent_id: uuid.UUID | None = None
    to_team: TicketTeam | None = None
    # Bắt buộc: chuyển tay không ghi lý do thì vài ngày sau không ai giải thích được vì sao
    # một ticket đi qua bốn người.
    reason: str = Field(min_length=3, max_length=500)


class ResolveRequest(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


class ReopenRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PresenceRequest(BaseModel):
    status: AgentStatus
    team: TicketTeam = TicketTeam.CS
    max_chats: int | None = Field(default=None, ge=1, le=50)


class PresenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: uuid.UUID
    team: TicketTeam
    status: AgentStatus
    active_chats: int
    max_chats: int
    last_seen_at: datetime | None = None


class CannedResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    team: TicketTeam
    title: str
    body: str
    shortcut: str
    is_active: bool


class CannedResponseRequest(BaseModel):
    team: TicketTeam = TicketTeam.CS
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=4000)
    shortcut: str = Field(min_length=1, max_length=32)
    is_active: bool = True
