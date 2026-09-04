"""Support Desk cho Console: hàng đợi, nhận việc, chuyển tay, kết luận, chat 3 bên (P2-08…P2-10).

Ranh giới quyền ở đây không phải chi tiết kỹ thuật mà là quy định vận hành:
`support:conversation:read_own` cho agent thấy đúng việc của mình,
`support:conversation:read_all` mới mở cả hàng đợi và lịch sử chat của người khác.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.deps import require_permission
from app.domains.chat import service as chat_service
from app.domains.chat.models import Conversation, ConversationMember, Message
from app.domains.chat.schemas import ConversationOut, MessageOut
from app.domains.iam import service as iam_service
from app.domains.iam.models import StaffUser
from app.domains.support import service
from app.domains.support.constants import TicketStatus, TicketTeam
from app.domains.support.models import TicketEvent
from app.domains.support.schemas import (
    CannedResponseOut,
    CannedResponseRequest,
    PresenceOut,
    PresenceRequest,
    ReopenRequest,
    ReplyRequest,
    ResolveRequest,
    SupportStatsOut,
    TicketEventOut,
    TicketOut,
    TransferRequest,
)

router = APIRouter(prefix="/ops/support", tags=["ops-support"])
chat_router = APIRouter(prefix="/ops/chat", tags=["ops-support"])

READ_ALL = "support:conversation:read_all"


def _read_all(staff: StaffUser) -> bool:
    return iam_service.has_permission(staff, READ_ALL)


# --- Hàng đợi -------------------------------------------------------------------------


@router.get("/queue", response_model=list[TicketOut])
async def support_queue(
    team: TicketTeam | None = Query(default=None),
    status: TicketStatus | None = Query(default=None),
    mine: bool = Query(default=False, description="Chỉ ticket được phân công cho tôi"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> list[TicketOut]:
    """Hàng đợi CSKH, sắp theo hạn SLA gấp nhất.

    Agent chỉ có quyền `read_own` thì luôn nhận về đúng việc của mình, kể cả khi họ tự gọi API
    với `mine=false` — ẩn nút trên giao diện không phải là phân quyền.
    """
    agent_id = staff.id if (mine or not _read_all(staff)) else None
    rows = await service.queue(db, team=team, status=status, agent_id=agent_id, limit=limit)
    return [TicketOut.model_validate(t) for t in rows]


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> TicketOut:
    ticket = await service.get_ticket(db, ticket_id)
    service.assert_can_read(ticket, staff, read_all=_read_all(staff))
    return TicketOut.model_validate(ticket)


@router.get("/tickets/{ticket_id}/events", response_model=list[TicketEventOut])
async def ticket_events(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> list[TicketEventOut]:
    """Dấu vết từng bước xử lý — câu trả lời cho "vì sao ticket này nằm ba ngày"."""
    ticket = await service.get_ticket(db, ticket_id)
    service.assert_can_read(ticket, staff, read_all=_read_all(staff))
    rows = (
        (
            await db.execute(
                select(TicketEvent)
                .where(TicketEvent.ticket_id == ticket.id)
                .order_by(TicketEvent.created_at.asc(), TicketEvent.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return [TicketEventOut.model_validate(e) for e in rows]


# --- Vòng đời -------------------------------------------------------------------------


@router.post("/tickets/{ticket_id}/claim", response_model=TicketOut)
async def claim_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> TicketOut:
    ticket = await service.get_ticket(db, ticket_id)
    return TicketOut.model_validate(await service.claim(db, ticket, staff))


@router.post("/tickets/{ticket_id}/transfer", response_model=TicketOut)
async def transfer_ticket(
    ticket_id: uuid.UUID,
    body: TransferRequest,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> TicketOut:
    ticket = await service.get_ticket(db, ticket_id)
    service.assert_can_read(ticket, staff, read_all=_read_all(staff))
    to_agent = None
    if body.to_agent_id is not None:
        to_agent = await db.get(StaffUser, body.to_agent_id)
        if to_agent is None or not to_agent.is_active:
            raise NotFoundError("Không tìm thấy nhân sự nhận việc")
    ticket = await service.transfer(
        db, ticket, actor=staff, to_agent=to_agent, to_team=body.to_team, reason=body.reason
    )
    return TicketOut.model_validate(ticket)


@router.post("/tickets/{ticket_id}/reply", response_model=MessageOut)
async def reply_ticket(
    ticket_id: uuid.UUID,
    body: ReplyRequest,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> MessageOut:
    """Trả lời khách ngay trong màn hình ticket, và ĐÓNG ĐỒNG HỒ SLA bằng chính lần đó.

    Tách hai việc này ra hai thao tác là mời người ta quên thao tác thứ hai — rồi báo cáo SLA
    hiển thị "chưa phản hồi" cho những ticket đã được trả lời từ lâu.
    """
    ticket = await service.get_ticket(db, ticket_id)
    service.assert_can_read(ticket, staff, read_all=_read_all(staff))
    if ticket.conversation_id is None:
        raise NotFoundError("Ticket này không có hội thoại đi kèm")

    conversation = await chat_service.get_conversation(db, ticket.conversation_id)
    # Agent chưa ở trong hội thoại thì vào trước, để khách thấy tin hệ thống báo có người
    # nhận việc chứ không phải bỗng dưng có người lạ nhắn tin.
    await chat_service.agent_join(db, conversation, staff)
    message, _ = await chat_service.send_message(
        db, conversation, body=body.body, sender_staff=staff, client_msg_id=body.client_msg_id
    )
    if ticket.assigned_agent_id is None:
        await service.claim(db, ticket, staff)
    await service.record_first_response(db, ticket, staff)
    return MessageOut.model_validate(message)


@router.post("/tickets/{ticket_id}/resolve", response_model=TicketOut)
async def resolve_ticket(
    ticket_id: uuid.UUID,
    body: ResolveRequest,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> TicketOut:
    ticket = await service.get_ticket(db, ticket_id)
    service.assert_can_read(ticket, staff, read_all=_read_all(staff))
    return TicketOut.model_validate(await service.resolve(db, ticket, actor=staff, note=body.note))


@router.post("/tickets/{ticket_id}/reopen", response_model=TicketOut)
async def reopen_ticket(
    ticket_id: uuid.UUID,
    body: ReopenRequest,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> TicketOut:
    ticket = await service.get_ticket(db, ticket_id)
    service.assert_can_read(ticket, staff, read_all=_read_all(staff))
    return TicketOut.model_validate(await service.reopen(db, ticket, reason=body.reason))


# --- Trực ca --------------------------------------------------------------------------


@router.post("/presence", response_model=PresenceOut)
async def set_presence(
    body: PresenceRequest,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> PresenceOut:
    """Agent bật/tắt trực. Cũng là nhịp "tôi còn sống" cho job bàn giao ca."""
    presence = await service.set_presence(
        db, staff, status=body.status, team=body.team, max_chats=body.max_chats
    )
    return PresenceOut.model_validate(presence)


# --- Bảng SLA và hiệu suất (P2-19) ----------------------------------------------------


@router.get("/stats", response_model=SupportStatsOut)
async def support_stats(
    days: int = Query(default=30, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission(READ_ALL)),
) -> SupportStatsOut:
    """Bảng chất lượng CSKH: phản hồi đầu, thời gian xử lý, tỷ lệ reopen, tỷ lệ đạt SLA.

    Đòi `read_all` vì đây là số liệu về hiệu suất của người khác — trưởng nhóm xem, không
    phải mọi agent.
    """
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(days=days)
    return SupportStatsOut.model_validate(await service.performance(db, since=since))


# --- Mẫu trả lời (P2-10) --------------------------------------------------------------


@router.get("/canned-responses", response_model=list[CannedResponseOut])
async def list_canned(
    team: TicketTeam | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("support:ticket:write")),
) -> list[CannedResponseOut]:
    rows = await service.list_canned(db, team=team)
    return [CannedResponseOut.model_validate(c) for c in rows]


@router.put("/canned-responses", response_model=CannedResponseOut)
async def upsert_canned(
    body: CannedResponseRequest,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission(READ_ALL)),
) -> CannedResponseOut:
    """Sửa mẫu là việc của trưởng nhóm: một câu trả lời sai gửi cho hàng nghìn khách."""
    mau = await service.upsert_canned(
        db,
        team=body.team,
        title=body.title,
        body=body.body,
        shortcut=body.shortcut,
        is_active=body.is_active,
    )
    return CannedResponseOut.model_validate(mau)


# --- Chat 3 bên và tra cứu (P2-06, P2-18) ---------------------------------------------


@chat_router.post("/conversations/{conversation_id}/join", response_model=ConversationOut)
async def join_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> ConversationOut:
    """Tham gia hội thoại 3 bên. Cả khách và tài xế đều thấy tin hệ thống báo có CSKH vào."""
    conversation = await chat_service.get_conversation(db, conversation_id)
    await chat_service.agent_join(db, conversation, staff)
    return ConversationOut.model_validate(conversation)


@chat_router.post("/conversations/{conversation_id}/leave", response_model=ConversationOut)
async def leave_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> ConversationOut:
    conversation = await chat_service.get_conversation(db, conversation_id)
    await chat_service.agent_leave(db, conversation, staff)
    return ConversationOut.model_validate(conversation)


@chat_router.get("/search", response_model=list[ConversationOut])
async def search_conversations(
    user_id: uuid.UUID | None = Query(default=None),
    trip_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission(READ_ALL)),
) -> list[ConversationOut]:
    """Tra lịch sử chat phục vụ khiếu nại (P2-18).

    Đòi `read_all` chứ không phải `read_own`: đây là đọc hội thoại của người khác, và mỗi lần
    gọi đều nằm trong audit log qua middleware.
    """
    stmt = select(Conversation)
    if trip_id is not None:
        stmt = stmt.where(Conversation.trip_id == trip_id)
    if user_id is not None:
        stmt = stmt.where(
            Conversation.id.in_(
                select(ConversationMember.conversation_id).where(
                    ConversationMember.user_id == user_id
                )
            )
        )
    stmt = stmt.order_by(Conversation.last_message_at.desc().nullslast()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [ConversationOut.model_validate(c) for c in rows]


@chat_router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def read_conversation(
    conversation_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("support:ticket:write")),
) -> list[MessageOut]:
    """Đọc nội dung một hội thoại từ Console.

    Agent chỉ có `read_own` vẫn đọc được hội thoại mình đang tham gia — nhưng không đọc được
    hội thoại của người khác, đó là ranh giới giữa "làm việc" và "tò mò".
    """
    conversation = await chat_service.get_conversation(db, conversation_id)
    if not _read_all(staff):
        chat_service.assert_member(conversation, staff=staff)
    rows = (
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [MessageOut.model_validate(m) for m in reversed(rows)]
