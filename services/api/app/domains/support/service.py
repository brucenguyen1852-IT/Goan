"""Nghiệp vụ ticket hỗ trợ: mở, phân công, SLA, leo thang, kết luận (P2-08…P2-10).

Bốn ràng buộc vận hành ở tài liệu phân định §7.5 quyết định toàn bộ file này:

  - **Phân phối tự động** theo `agent_presence`: còn slot, đúng đội, và ưu tiên người đã từng
    xử lý việc của chính khách này. Kể lại từ đầu cho một người mới là cách nhanh nhất làm
    khách tức giận thêm một lần nữa.
  - **SLA tính theo phản hồi ĐẦU TIÊN**, không phải theo lúc đóng ticket. Một vụ tai nạn được
    trả lời sau 90 giây rồi xử lý trong hai ngày vẫn là làm đúng; im lặng 30 phút thì không.
  - **Quá hạn tự leo thang** lên `cs_lead`. Không có bước tự động này thì ticket quá hạn chỉ
    được phát hiện lúc khách gọi lần thứ hai.
  - **Agent offline quá 10 phút thì ticket quay về hàng đợi.** Hết ca, tắt máy, mất mạng —
    ticket không được nằm chờ theo người.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import log_event
from app.domains.chat import service as chat_service
from app.domains.chat.constants import ConversationKind, MemberRole
from app.domains.chat.models import Conversation, ConversationMember
from app.domains.iam.models import StaffUser
from app.domains.support.constants import (
    CLOSED_TICKET_STATUSES,
    DEFAULT_TEAM,
    MIN_PRIORITY,
    OPEN_TICKET_STATUSES,
    PRIORITY_ORDER,
    AgentStatus,
    SubjectType,
    TicketCategory,
    TicketEventType,
    TicketPriority,
    TicketStatus,
    TicketTeam,
)
from app.domains.support.models import AgentPresence, CannedResponse, SupportTicket, TicketEvent
from app.domains.users.models import User

logger = logging.getLogger("goan.support")

ESCALATION_TEAM = TicketTeam.CS


# --- Mã ticket ------------------------------------------------------------------------


async def _next_code(db: AsyncSession, moment: datetime) -> str:
    """Sinh mã dạng `GA-260904-0042` — thứ khách đọc qua điện thoại cho tổng đài.

    Đếm theo ngày chứ không dùng một chuỗi tăng dần toàn cục: nhìn mã là biết ticket mở hôm
    nào, và số thứ tự trong ngày đủ ngắn để đọc không nhầm.
    """
    ngay = moment.astimezone(timezone.utc).strftime("%y%m%d")
    tien_to = f"GA-{ngay}-"
    dem = (
        await db.execute(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.code.like(f"{tien_to}%"))
        )
    ).scalar_one()
    return f"{tien_to}{dem + 1:04d}"


def sla_due_at(priority: TicketPriority, *, now: datetime | None = None) -> datetime:
    """Hạn phản hồi đầu tiên. Con số nằm ở config để sửa được mà không cần deploy."""
    phut = get_settings().SLA_FIRST_RESPONSE_MINUTES.get(priority.value, 60)
    return (now or datetime.now(timezone.utc)) + timedelta(minutes=phut)


def effective_priority(category: TicketCategory, requested: TicketPriority) -> TicketPriority:
    """Nâng mức ưu tiên theo loại vấn đề, không bao giờ hạ.

    Khách chọn "thấp" cho một vụ tai nạn thì đó là do họ không biết cách phân loại của mình
    ảnh hưởng tới hàng đợi CSKH — không phải vì việc đó thật sự nhẹ.
    """
    san = MIN_PRIORITY.get(category)
    if san is None:
        return requested
    return max(requested, san, key=PRIORITY_ORDER.index)


# --- Dấu vết --------------------------------------------------------------------------


def record_event(
    db: AsyncSession,
    ticket: SupportTicket,
    event_type: TicketEventType,
    *,
    actor: StaffUser | None = None,
    **payload: object,
) -> TicketEvent:
    """Ghi một bước xử lý. Gọi trong cùng transaction với thay đổi mà nó mô tả."""
    su_kien = TicketEvent(
        ticket_id=ticket.id,
        actor_staff_id=actor.id if actor else None,
        event_type=event_type,
        payload=dict(payload) or None,
    )
    db.add(su_kien)
    return su_kien


# --- Phân phối tự động (P2-09) --------------------------------------------------------


async def pick_agent(
    db: AsyncSession, *, team: TicketTeam, subject_id: uuid.UUID
) -> StaffUser | None:
    """Chọn agent cho một ticket mới: đúng đội, còn slot, ưu tiên người quen việc của khách.

    Trả về `None` khi cả đội đã kín hoặc không ai trực — lúc đó ticket nằm ở trạng thái `new`
    trong hàng đợi chung, không bị gán bừa cho một người đang bận hoặc đã tắt máy.
    """
    ung_vien = list(
        (
            await db.execute(
                select(AgentPresence).where(
                    AgentPresence.team == team,
                    AgentPresence.status == AgentStatus.AVAILABLE,
                    AgentPresence.active_chats < AgentPresence.max_chats,
                )
            )
        )
        .scalars()
        .all()
    )
    if not ung_vien:
        return None

    # Ai từng xử lý ticket của chính khách này thì được ưu tiên: khách không phải kể lại từ đầu.
    quen_viec = set(
        (
            await db.execute(
                select(SupportTicket.assigned_agent_id).where(
                    SupportTicket.subject_id == subject_id,
                    SupportTicket.assigned_agent_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    ung_vien.sort(key=lambda p: (p.agent_id not in quen_viec, p.active_chats))
    chon = ung_vien[0]
    return await db.get(StaffUser, chon.agent_id)


async def _presence_of(db: AsyncSession, agent_id: uuid.UUID) -> AgentPresence | None:
    return (
        await db.execute(select(AgentPresence).where(AgentPresence.agent_id == agent_id))
    ).scalar_one_or_none()


async def set_presence(
    db: AsyncSession,
    staff: StaffUser,
    *,
    status: AgentStatus,
    team: TicketTeam = TicketTeam.CS,
    max_chats: int | None = None,
) -> AgentPresence:
    """Agent bật/tắt trực. Mỗi lần gọi cũng là một nhịp "tôi còn sống" cho job bàn giao ca."""
    presence = await _presence_of(db, staff.id)
    if presence is None:
        presence = AgentPresence(
            agent_id=staff.id,
            team=team,
            max_chats=max_chats or get_settings().AGENT_DEFAULT_MAX_CHATS,
        )
        db.add(presence)
    presence.status = status
    presence.team = team
    if max_chats is not None:
        presence.max_chats = max_chats
    presence.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(presence)
    return presence


async def _assign(
    db: AsyncSession, ticket: SupportTicket, agent: StaffUser, *, actor: StaffUser | None = None
) -> None:
    """Gán ticket cho agent và cộng tải. Không commit — người gọi quyết định ranh giới."""
    truoc = ticket.assigned_agent_id
    if truoc and truoc != agent.id:
        cu = await _presence_of(db, truoc)
        if cu is not None and cu.active_chats > 0:
            cu.active_chats -= 1
    ticket.assigned_agent_id = agent.id
    ticket.status = TicketStatus.ASSIGNED
    moi = await _presence_of(db, agent.id)
    if moi is not None:
        moi.active_chats += 1
    record_event(
        db,
        ticket,
        TicketEventType.ASSIGNED,
        actor=actor,
        agent_id=str(agent.id),
        previous_agent_id=str(truoc) if truoc else None,
    )


# --- Mở ticket ------------------------------------------------------------------------


async def create_ticket(
    db: AsyncSession,
    *,
    user: User,
    subject: str,
    category: TicketCategory,
    priority: TicketPriority = TicketPriority.NORMAL,
    trip_id: uuid.UUID | None = None,
    body: str | None = None,
) -> SupportTicket:
    """Mở ticket kèm hội thoại `support` và phân công ngay nếu có người trực (P2-08, P2-09)."""
    from app.core.constants import UserRole

    now = datetime.now(timezone.utc)
    muc = effective_priority(category, priority)
    doi = DEFAULT_TEAM[category]

    ticket = SupportTicket(
        code=await _next_code(db, now),
        subject_type=SubjectType.DRIVER if user.role is UserRole.DRIVER else SubjectType.RIDER,
        subject_id=user.id,
        trip_id=trip_id,
        category=category,
        priority=muc,
        team=doi,
        subject=subject,
        sla_due_at=sla_due_at(muc, now=now),
    )
    db.add(ticket)
    await db.flush()

    # Hội thoại đi kèm ticket: khách nhắn tiếp vào đúng chỗ, không mở ticket thứ hai để hỏi
    # thêm một câu.
    conversation = Conversation(kind=ConversationKind.SUPPORT, subject=subject)
    db.add(conversation)
    await db.flush()
    db.add(
        ConversationMember(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MemberRole.DRIVER if user.role is UserRole.DRIVER else MemberRole.RIDER,
        )
    )
    ticket.conversation_id = conversation.id

    record_event(db, ticket, TicketEventType.CREATED, category=category.value, priority=muc.value)
    agent = await pick_agent(db, team=doi, subject_id=user.id)
    if agent is not None:
        await _assign(db, ticket, agent)

    await db.commit()
    await db.refresh(ticket)

    if body:
        # Nội dung khách mô tả đi vào hội thoại như một tin bình thường, để agent đọc liền
        # mạch thay vì phải nhảy giữa hai màn hình.
        await db.refresh(conversation)
        await chat_service.send_message(db, conversation, body=body, sender_user=user)

    log_event(
        logger,
        "support_ticket_created",
        ticket_id=str(ticket.id),
        code=ticket.code,
        priority=muc.value,
        team=doi.value,
        assigned=bool(agent),
    )
    return ticket


# --- Truy vấn -------------------------------------------------------------------------


async def get_ticket(db: AsyncSession, ticket_id: uuid.UUID) -> SupportTicket:
    ticket = await db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise NotFoundError("Không tìm thấy ticket")
    return ticket


async def queue(
    db: AsyncSession,
    *,
    team: TicketTeam | None = None,
    status: TicketStatus | None = None,
    agent_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[SupportTicket]:
    """Hàng đợi CSKH: việc gấp nhất và sắp quá hạn nhất lên trước."""
    stmt = select(SupportTicket)
    if team is not None:
        stmt = stmt.where(SupportTicket.team == team)
    if status is not None:
        stmt = stmt.where(SupportTicket.status == status)
    else:
        stmt = stmt.where(SupportTicket.status.in_(OPEN_TICKET_STATUSES))
    if agent_id is not None:
        stmt = stmt.where(SupportTicket.assigned_agent_id == agent_id)
    # Sắp theo hạn SLA chứ không theo thời điểm tạo: một ticket `urgent` mở sau vẫn phải đứng
    # trước một ticket `low` mở từ sáng.
    stmt = stmt.order_by(SupportTicket.sla_due_at.asc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


# --- Vòng đời -------------------------------------------------------------------------


async def claim(db: AsyncSession, ticket: SupportTicket, staff: StaffUser) -> SupportTicket:
    """Agent tự nhận một ticket trong hàng đợi."""
    if ticket.status in CLOSED_TICKET_STATUSES:
        raise ConflictError("Ticket đã kết luận, không nhận lại được")
    if ticket.assigned_agent_id == staff.id:
        return ticket
    if ticket.assigned_agent_id is not None:
        raise ConflictError("Ticket đã có người nhận")
    await _assign(db, ticket, staff, actor=staff)
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def transfer(
    db: AsyncSession,
    ticket: SupportTicket,
    *,
    actor: StaffUser,
    to_agent: StaffUser | None = None,
    to_team: TicketTeam | None = None,
    reason: str,
) -> SupportTicket:
    """Chuyển ticket sang agent hoặc đội khác, luôn kèm lý do.

    Chuyển tay không ghi lý do thì vài ngày sau không ai giải thích được vì sao một ticket
    đi qua bốn người — và đó chính là loại ticket khách khiếu nại lên trên.
    """
    if ticket.status in CLOSED_TICKET_STATUSES:
        raise ConflictError("Ticket đã kết luận, không chuyển được")
    if to_agent is None and to_team is None:
        raise ConflictError("Phải chỉ định agent hoặc đội nhận")

    doi_cu = ticket.team
    if to_team is not None and to_team != ticket.team:
        ticket.team = to_team
        # Đổi đội mà giữ nguyên người cũ là để ticket nằm ở đội mới nhưng không ai trong đội
        # đó thấy mình có trách nhiệm.
        if to_agent is None and ticket.assigned_agent_id is not None:
            cu = await _presence_of(db, ticket.assigned_agent_id)
            if cu is not None and cu.active_chats > 0:
                cu.active_chats -= 1
            ticket.assigned_agent_id = None
            ticket.status = TicketStatus.NEW

    if to_agent is not None:
        await _assign(db, ticket, to_agent, actor=actor)

    record_event(
        db,
        ticket,
        TicketEventType.TRANSFERRED,
        actor=actor,
        reason=reason,
        from_team=doi_cu.value,
        to_team=ticket.team.value,
        to_agent_id=str(to_agent.id) if to_agent else None,
    )
    await db.commit()
    await db.refresh(ticket)
    log_event(
        logger, "support_ticket_transferred", ticket_id=str(ticket.id), to_team=ticket.team.value
    )
    return ticket


async def record_first_response(
    db: AsyncSession, ticket: SupportTicket, staff: StaffUser
) -> SupportTicket:
    """Đóng đồng hồ SLA ở lần agent trả lời ĐẦU TIÊN, và chỉ lần đầu.

    Ghi đè ở mỗi lần trả lời sẽ biến chỉ số "phản hồi đầu" thành "phản hồi cuối" — một con số
    luôn đẹp và hoàn toàn vô nghĩa.
    """
    if ticket.first_response_at is not None:
        return ticket
    ticket.first_response_at = datetime.now(timezone.utc)
    record_event(db, ticket, TicketEventType.FIRST_RESPONSE, actor=staff)
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def resolve(
    db: AsyncSession, ticket: SupportTicket, *, actor: StaffUser, note: str
) -> SupportTicket:
    """Kết luận ticket kèm ghi chú, và trả slot lại cho agent."""
    if ticket.status in CLOSED_TICKET_STATUSES:
        raise ConflictError("Ticket đã kết luận")
    ticket.status = TicketStatus.RESOLVED
    ticket.resolved_at = datetime.now(timezone.utc)
    ticket.resolution_note = note
    if ticket.assigned_agent_id is not None:
        presence = await _presence_of(db, ticket.assigned_agent_id)
        if presence is not None and presence.active_chats > 0:
            presence.active_chats -= 1
    record_event(db, ticket, TicketEventType.RESOLVED, actor=actor, note=note)
    await db.commit()
    await db.refresh(ticket)
    log_event(logger, "support_ticket_resolved", ticket_id=str(ticket.id))
    return ticket


async def reopen(db: AsyncSession, ticket: SupportTicket, *, reason: str) -> SupportTicket:
    """Khách chưa hài lòng thì ticket mở lại, không mở ticket mới.

    Mở ticket mới sẽ làm tỷ lệ reopen bằng 0 vĩnh viễn — chỉ số đẹp nhất và vô dụng nhất mà
    một đội CSKH có thể tự tặng cho mình.
    """
    if ticket.status not in CLOSED_TICKET_STATUSES:
        raise ConflictError("Ticket chưa kết luận thì không mở lại")
    ticket.status = TicketStatus.ASSIGNED if ticket.assigned_agent_id else TicketStatus.NEW
    ticket.resolved_at = None
    ticket.reopened_count += 1
    # Đồng hồ SLA chạy lại từ đầu: lần trả lời trước không tính cho vòng khiếu nại này.
    ticket.first_response_at = None
    ticket.sla_due_at = sla_due_at(ticket.priority)
    if ticket.assigned_agent_id is not None:
        presence = await _presence_of(db, ticket.assigned_agent_id)
        if presence is not None:
            presence.active_chats += 1
    record_event(db, ticket, TicketEventType.REOPENED, reason=reason)
    await db.commit()
    await db.refresh(ticket)
    return ticket


# --- Job nền --------------------------------------------------------------------------


async def escalate_overdue(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Ticket quá hạn phản hồi đầu thì tự leo thang lên `cs_lead` (P2-08).

    Không có bước tự động này thì ticket quá hạn chỉ được phát hiện lúc khách gọi lần thứ hai
    — và lúc đó thì cam kết SLA đã hỏng rồi, chỉ còn xin lỗi.
    """
    moment = now or datetime.now(timezone.utc)
    stmt = select(SupportTicket).where(
        SupportTicket.status.in_((TicketStatus.NEW, TicketStatus.ASSIGNED)),
        SupportTicket.first_response_at.is_(None),
        SupportTicket.sla_due_at <= moment,
    )
    dem = 0
    for ticket in (await db.execute(stmt)).scalars().all():
        ticket.status = TicketStatus.ESCALATED
        record_event(
            db,
            ticket,
            TicketEventType.ESCALATED,
            reason="sla_first_response_overdue",
            sla_due_at=ticket.sla_due_at.isoformat(),
        )
        dem += 1
    if dem:
        await db.commit()
        log_event(logger, "support_tickets_escalated", count=dem)
    return dem


async def release_offline_agents(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Agent mất dấu quá lâu thì ticket của họ quay về hàng đợi (P2-08, bàn giao ca).

    Hết ca, tắt máy, mất mạng — ticket không được nằm chờ theo người. Ghi `released` để lúc
    đối chiếu chất lượng còn phân biệt được "agent bỏ việc" với "hệ thống thu lại".
    """
    settings = get_settings()
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(minutes=settings.AGENT_OFFLINE_RELEASE_MINUTES)

    stmt = select(AgentPresence).where(
        or_(
            AgentPresence.status == AgentStatus.OFFLINE,
            AgentPresence.last_seen_at.is_(None),
            AgentPresence.last_seen_at <= cutoff,
        )
    )
    dem = 0
    for presence in (await db.execute(stmt)).scalars().all():
        moc = presence.last_seen_at
        if moc is not None and moc.tzinfo is None:
            moc = moc.replace(tzinfo=timezone.utc)
        if presence.status is not AgentStatus.OFFLINE and (moc is None or moc > cutoff):
            continue
        tickets = (
            (
                await db.execute(
                    select(SupportTicket).where(
                        SupportTicket.assigned_agent_id == presence.agent_id,
                        SupportTicket.status.in_(OPEN_TICKET_STATUSES),
                    )
                )
            )
            .scalars()
            .all()
        )
        for ticket in tickets:
            ticket.assigned_agent_id = None
            ticket.status = TicketStatus.NEW
            record_event(
                db,
                ticket,
                TicketEventType.RELEASED,
                reason="agent_offline",
                agent_id=str(presence.agent_id),
            )
            dem += 1
        presence.active_chats = 0
    if dem:
        await db.commit()
        log_event(logger, "support_tickets_released", count=dem)
    return dem


# --- Mẫu trả lời (P2-10) --------------------------------------------------------------


async def list_canned(
    db: AsyncSession, *, team: TicketTeam | None = None, active_only: bool = True
) -> list[CannedResponse]:
    stmt = select(CannedResponse)
    if team is not None:
        stmt = stmt.where(CannedResponse.team == team)
    if active_only:
        stmt = stmt.where(CannedResponse.is_active.is_(True))
    return list((await db.execute(stmt.order_by(CannedResponse.shortcut))).scalars().all())


async def resolve_shortcut(
    db: AsyncSession, *, team: TicketTeam, shortcut: str
) -> CannedResponse | None:
    """Tra mẫu theo gõ tắt `/hoantien`. Dấu `/` đứng đầu là tuỳ chọn."""
    khoa = shortcut.lstrip("/").strip().lower()
    return (
        await db.execute(
            select(CannedResponse).where(
                CannedResponse.team == team,
                func.lower(CannedResponse.shortcut) == khoa,
                CannedResponse.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()


async def upsert_canned(
    db: AsyncSession,
    *,
    team: TicketTeam,
    title: str,
    body: str,
    shortcut: str,
    is_active: bool = True,
) -> CannedResponse:
    khoa = shortcut.lstrip("/").strip().lower()
    mau = (
        await db.execute(
            select(CannedResponse).where(
                CannedResponse.team == team, CannedResponse.shortcut == khoa
            )
        )
    ).scalar_one_or_none()
    if mau is None:
        mau = CannedResponse(team=team, shortcut=khoa, title=title, body=body)
        db.add(mau)
    mau.title = title
    mau.body = body
    mau.is_active = is_active
    await db.commit()
    await db.refresh(mau)
    return mau


# --- Quyền xem ------------------------------------------------------------------------


def assert_can_read(ticket: SupportTicket, staff: StaffUser, *, read_all: bool) -> None:
    """`support:conversation:read_own` chỉ mở đúng ticket của mình, không mở cả hàng đợi."""
    if read_all or ticket.assigned_agent_id == staff.id:
        return
    raise PermissionDeniedError("Bạn không được phân công ticket này")


# --- Bảng SLA và hiệu suất agent (P2-19) ----------------------------------------------


async def performance(
    db: AsyncSession, *, since: datetime | None = None, now: datetime | None = None
) -> dict:
    """Bốn chỉ số ở tài liệu phân định §7.5: phản hồi đầu, thời gian xử lý, reopen, đạt SLA.

    Tính trên ticket ĐÃ kết luận cho hai chỉ số thời gian, nhưng đếm quá hạn trên cả ticket
    còn mở: một ticket urgent nằm 3 tiếng chưa ai đụng vào là thứ bảng này phải nói ra ngay,
    chứ không phải im lặng cho tới lúc nó được đóng.
    """
    moment = now or datetime.now(timezone.utc)
    tu = since or (moment - timedelta(days=30))

    rows = list(
        (await db.execute(select(SupportTicket).where(SupportTicket.created_at >= tu)))
        .scalars()
        .all()
    )

    def _aware(moc: datetime | None) -> datetime | None:
        if moc is None:
            return None
        return moc if moc.tzinfo is not None else moc.replace(tzinfo=timezone.utc)

    theo_agent: dict[str, dict] = {}
    tong = {
        "tickets": len(rows),
        "dang_mo": 0,
        "qua_han_chua_phan_hoi": 0,
        "dat_sla": 0,
        "co_moc_phan_hoi": 0,
        "reopen": 0,
    }
    tong_phan_hoi: list[float] = []
    tong_xu_ly: list[float] = []

    for ticket in rows:
        tao = _aware(ticket.created_at)
        han = _aware(ticket.sla_due_at)
        dau = _aware(ticket.first_response_at)
        xong = _aware(ticket.resolved_at)

        if ticket.status in OPEN_TICKET_STATUSES:
            tong["dang_mo"] += 1
            if dau is None and han is not None and han <= moment:
                tong["qua_han_chua_phan_hoi"] += 1
        if ticket.reopened_count:
            tong["reopen"] += 1
        if dau is not None:
            tong["co_moc_phan_hoi"] += 1
            if han is not None and dau <= han:
                tong["dat_sla"] += 1
            if tao is not None:
                tong_phan_hoi.append((dau - tao).total_seconds() / 60)
        if xong is not None and tao is not None:
            tong_xu_ly.append((xong - tao).total_seconds() / 60)

        khoa = str(ticket.assigned_agent_id) if ticket.assigned_agent_id else "chua_phan_cong"
        muc = theo_agent.setdefault(
            khoa,
            {
                "agent_id": khoa,
                "tickets": 0,
                "dang_mo": 0,
                "da_ket_luan": 0,
                "reopen": 0,
                "dat_sla": 0,
                "co_moc_phan_hoi": 0,
                "_phan_hoi": [],
                "_xu_ly": [],
            },
        )
        muc["tickets"] += 1
        if ticket.status in OPEN_TICKET_STATUSES:
            muc["dang_mo"] += 1
        if ticket.status in CLOSED_TICKET_STATUSES:
            muc["da_ket_luan"] += 1
        if ticket.reopened_count:
            muc["reopen"] += 1
        if dau is not None:
            muc["co_moc_phan_hoi"] += 1
            if han is not None and dau <= han:
                muc["dat_sla"] += 1
            if tao is not None:
                muc["_phan_hoi"].append((dau - tao).total_seconds() / 60)
        if xong is not None and tao is not None:
            muc["_xu_ly"].append((xong - tao).total_seconds() / 60)

    def _tb(xs: list[float]) -> float | None:
        # Rỗng trả về None chứ KHÔNG phải 0: "chưa có số liệu" và "phản hồi tức thì" là hai
        # chuyện khác nhau, và hiển thị 0 phút cho cái đầu là nói dối bằng biểu đồ.
        return round(sum(xs) / len(xs), 1) if xs else None

    agents = []
    for muc in theo_agent.values():
        agents.append(
            {
                "agent_id": muc["agent_id"],
                "tickets": muc["tickets"],
                "dang_mo": muc["dang_mo"],
                "da_ket_luan": muc["da_ket_luan"],
                "phan_hoi_dau_phut": _tb(muc["_phan_hoi"]),
                "xu_ly_phut": _tb(muc["_xu_ly"]),
                "ty_le_reopen": (
                    round(muc["reopen"] / muc["tickets"], 3) if muc["tickets"] else 0.0
                ),
                "ty_le_dat_sla": (
                    round(muc["dat_sla"] / muc["co_moc_phan_hoi"], 3)
                    if muc["co_moc_phan_hoi"]
                    else None
                ),
            }
        )
    agents.sort(key=lambda a: (-a["tickets"], a["agent_id"]))

    return {
        "tu_ngay": tu,
        "tong_ticket": tong["tickets"],
        "dang_mo": tong["dang_mo"],
        "qua_han_chua_phan_hoi": tong["qua_han_chua_phan_hoi"],
        "phan_hoi_dau_phut": _tb(tong_phan_hoi),
        "xu_ly_phut": _tb(tong_xu_ly),
        "ty_le_reopen": (round(tong["reopen"] / tong["tickets"], 3) if tong["tickets"] else 0.0),
        "ty_le_dat_sla": (
            round(tong["dat_sla"] / tong["co_moc_phan_hoi"], 3) if tong["co_moc_phan_hoi"] else None
        ),
        "agents": agents,
    }
