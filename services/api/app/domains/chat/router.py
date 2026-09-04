"""Router hội thoại cho khách và tài xế."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.domains.chat import service
from app.domains.chat.schemas import (
    ConversationOut,
    MarkReadRequest,
    MessageOut,
    SendMessageRequest,
)
from app.domains.notifications import service as notifications
from app.domains.users.models import User
from app.websocket.events import ServerEvent

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
    conversation = await service.get_conversation(db, conversation_id)
    service.assert_member(conversation, user=user)
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
    conversation = await service.get_conversation(db, conversation_id)
    service.assert_member(conversation, user=user)
    message, created = await service.send_message(
        db, conversation, body=body.body, sender_user=user, client_msg_id=body.client_msg_id
    )
    if created:
        # Đẩy cho những người còn lại trong hội thoại; ai offline thì nhận push (P2-13).
        for member in conversation.members:
            if member.left_at is None and member.user_id and member.user_id != user.id:
                await notifications.notify_user(
                    member.user_id,
                    ServerEvent.CHAT_MESSAGE,
                    conversation_id=str(conversation.id),
                    message_id=str(message.id),
                    body=message.body,
                )
    return MessageOut.model_validate(message)


@router.post("/conversations/{conversation_id}/read", response_model=ConversationOut)
async def mark_read(
    conversation_id: uuid.UUID,
    body: MarkReadRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationOut:
    conversation = await service.get_conversation(db, conversation_id)
    member = service.assert_member(conversation, user=user)
    await service.mark_read(db, conversation, member, body.message_id)
    out = ConversationOut.model_validate(conversation)
    out.unread_count = await service.unread_count(db, conversation, member)
    return out
