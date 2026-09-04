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
    # Mã tệp đã xin URL tải lên trước đó (P2-12). Server chỉ nhận mã của chính nó cấp ra.
    attachment_id: uuid.UUID | None = None


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
    attachment_id: uuid.UUID | None = None


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


class UploadRequest(BaseModel):
    conversation_id: uuid.UUID
    content_type: str = Field(max_length=100)
    # Client khai trước kích thước để bị từ chối NGAY, thay vì sau khi ngồi chờ tải xong 20MB
    # qua 4G rồi mới biết là quá hạn mức.
    size_bytes: int = Field(gt=0)


class UploadOut(BaseModel):
    attachment_id: uuid.UUID
    storage_key: str
    upload_url: str
    expires_at: datetime
    max_bytes: int


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID | None = None
    content_type: str
    size_bytes: int
    scan_result: str | None = None
    # URL đọc ký hạn ngắn, sinh mới mỗi lần hỏi. Không lưu vào DB.
    download_url: str | None = None
