"""Router hội thoại cho khách và tài xế."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.domains.chat import service
from app.domains.chat.constants import MessageKind
from app.domains.chat.schemas import (
    AttachmentOut,
    ConversationOut,
    MarkReadRequest,
    MessageOut,
    SendMessageRequest,
    UploadOut,
    UploadRequest,
)
from app.domains.notifications import service as notifications
from app.domains.users.models import User
from app.websocket.events import ServerEvent
from app.workers.queue import enqueue

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_PAGE = 100


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ConversationOut]:
    result = []
    for conversation in await service.list_conversations_for_user(db, user):
        member = service.active_member(conversation, user=user)
        out = ConversationOut.model_validate(conversation)
        out.unread_count = await service.unread_count(db, conversation, member) if member else 0
        result.append(out)
    return result


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID,
    before: datetime | None = Query(default=None, description="Cuộn ngược xem tin cũ"),
    after: datetime | None = Query(
        default=None, description="Đồng bộ bù sau khi mất kết nối: mốc tin cuối app đang có"
    ),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MessageOut]:
    conversation, _ = await service.get_member_conversation(db, conversation_id, user=user)
    rows = await service.list_messages(db, conversation, before=before, after=after, limit=limit)
    return [MessageOut.model_validate(m) for m in rows]


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessageOut:
    conversation, _ = await service.get_member_conversation(db, conversation_id, user=user)
    attachment = None
    if body.attachment_id is not None:
        attachment = await service.claim_attachment(
            db,
            conversation,
            body.attachment_id,
            uploader_user=user,
            client_msg_id=body.client_msg_id,
        )
    message, created = await service.send_message(
        db,
        conversation,
        body=body.body,
        sender_user=user,
        client_msg_id=body.client_msg_id,
        kind=MessageKind.IMAGE if attachment is not None else MessageKind.TEXT,
        attachment=attachment,
    )
    if created:
        settings = get_settings()
        for member in conversation.members:
            if member.left_at is None and member.user_id and member.user_id != user.id:
                await notifications.notify_user(
                    member.user_id,
                    ServerEvent.CHAT_MESSAGE,
                    conversation_id=str(conversation.id),
                    message_id=str(message.id),
                    body=message.body,
                )
                # Push đi sau vài giây và chỉ khi tới lúc đó họ vẫn chưa đọc (P2-13). Bắn
                # ngay lập tức là gửi thông báo cho tin người ta vừa đọc xong trên màn hình.
                if settings.PUSH_ON_MESSAGE_ENABLED:
                    enqueue(
                        "app.workers.tasks.deliver_chat_push",
                        str(message.id),
                        str(member.user_id),
                        countdown=settings.PUSH_ON_MESSAGE_DELAY_SECONDS,
                    )
    return MessageOut.model_validate(message)


@router.post("/conversations/{conversation_id}/read", response_model=ConversationOut)
async def mark_read(
    conversation_id: uuid.UUID,
    body: MarkReadRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationOut:
    conversation, member = await service.get_member_conversation(db, conversation_id, user=user)
    await service.mark_read(db, conversation, member, body.message_id)
    out = ConversationOut.model_validate(conversation)
    out.unread_count = await service.unread_count(db, conversation, member)
    return out


# --- Tệp đính kèm (P2-12) -------------------------------------------------------------


@router.post("/attachments", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def create_attachment_upload(
    body: UploadRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UploadOut:
    """Xin URL tải ảnh lên, có hạn 15 phút.

    Ảnh đi THẲNG lên kho, không qua backend: một ảnh 5MB đi qua tiến trình API là chiếm một
    worker suốt thời gian truyền, đúng lúc mạng của người gửi đang chậm nhất.
    """
    conversation, _ = await service.get_member_conversation(db, body.conversation_id, user=user)
    attachment, presigned = await service.create_upload(
        db,
        conversation,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        uploader_user=user,
    )
    return UploadOut(
        attachment_id=attachment.id,
        storage_key=presigned.storage_key,
        upload_url=presigned.upload_url,
        expires_at=presigned.expires_at,
        max_bytes=presigned.max_bytes,
    )


@router.get("/attachments/{attachment_id}", response_model=AttachmentOut)
async def get_attachment(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AttachmentOut:
    """URL đọc ký hạn ngắn, sinh mới mỗi lần xem chứ không lưu lại."""
    attachment = await service.get_attachment_for_member(db, attachment_id, user=user)
    out = AttachmentOut.model_validate(attachment)
    out.download_url = await service.attachment_download_url(db, attachment)
    return out
