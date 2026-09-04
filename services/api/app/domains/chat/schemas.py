"""Schema hội thoại."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.chat.constants import ConversationKind, ConversationStatus, MessageKind


class SendMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    # App tự sinh và gửi kèm. Gửi lại cùng mã này không tạo tin thứ hai — mất sóng rồi bấm
    # gửi lại là chuyện hằng ngày trên mạng di động.
    client_msg_id: str | None = Field(default=None, max_length=64)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    kind: MessageKind
    body: str
    sender_user_id: uuid.UUID | None = None
    sender_staff_id: uuid.UUID | None = None
    client_msg_id: str | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ConversationKind
    status: ConversationStatus
    trip_id: uuid.UUID | None = None
    subject: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0


class MarkReadRequest(BaseModel):
    message_id: uuid.UUID
