"""Mở ticket hỗ trợ từ app khách và app tài xế (P2-08)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.domains.support import service
from app.domains.support.constants import OPEN_TICKET_STATUSES
from app.domains.support.models import SupportTicket
from app.domains.support.schemas import CreateTicketRequest, TicketOut
from app.domains.users.models import User

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: CreateTicketRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    """Mở ticket. Hội thoại `support` đi kèm được tạo luôn, không cần gọi thêm API nào."""
    ticket = await service.create_ticket(
        db,
        user=user,
        subject=body.subject,
        category=body.category,
        priority=body.priority,
        trip_id=body.trip_id,
        body=body.body,
    )
    return TicketOut.model_validate(ticket)


@router.get("/tickets", response_model=list[TicketOut])
async def my_tickets(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[TicketOut]:
    """Ticket của chính người đang đăng nhập — việc đang mở lên trước."""
    rows = (
        (
            await db.execute(
                select(SupportTicket)
                .where(SupportTicket.subject_id == user.id)
                .order_by(
                    SupportTicket.status.in_(OPEN_TICKET_STATUSES).desc(),
                    SupportTicket.created_at.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return [TicketOut.model_validate(t) for t in rows]
