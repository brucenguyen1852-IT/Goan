"""Nghiệp vụ hội thoại: gửi, đọc, đồng bộ bù, tham gia 3 bên (P2-02…P2-07, P2-11).

Bài toán thật của chat trong ứng dụng gọi xe không phải là "hiển thị tin nhắn". Nó là:

  - Mạng rớt giữa chừng, người dùng bấm gửi lại → **không được** thành hai tin.
  - Mất sóng 5 phút rồi nối lại → phải thấy **đủ** tin đã lỡ, không thiếu không trùng.
  - CSKH nhảy vào giữa cuộc trò chuyện của khách và tài xế → cả hai bên phải **biết**.
  - Có người rủ nhau chuyển khoản ngoài app → phải **thấy được**, nhưng không được chặn.

Bốn thứ đó là toàn bộ nội dung file này.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import log_event
from app.domains.chat.constants import (
    ConversationKind,
    ConversationStatus,
    MemberRole,
    MessageKind,
)
from app.domains.chat.models import Conversation, ConversationMember, Message
from app.domains.iam.models import StaffUser
from app.domains.users.models import User

logger = logging.getLogger("goan.chat")

# Dấu hiệu rủ nhau thanh toán ngoài app (P2-11). Cố tình rộng và cố tình CHỈ gắn cờ:
# chặn nhầm một tin thật thì hai bên chuyển sang Zalo và mất luôn dấu vết — tệ hơn nhiều
# so với việc để một tin đáng ngờ đi qua nhưng có người xem lại.
OFF_APP_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Số tài khoản ngân hàng", re.compile(r"\b\d{9,16}\b")),
    (
        "Nhắc tên ngân hàng",
        re.compile(
            r"\b(vietcombank|vcb|techcombank|tcb|mbbank|mb bank|acb|bidv|vietinbank|momo|zalopay|viettel ?money)\b",
            re.I,
        ),
    ),
    (
        "Rủ chuyển khoản / trả ngoài",
        re.compile(
            r"(chuyển khoản|ck cho|trả ngoài|tiền mặt luôn|khỏi qua app|huỷ app|hủy app|hủy chuyến rồi)",
            re.I,
        ),
    ),
    ("Chia sẻ mã QR ví", re.compile(r"(qr|mã)\s*(momo|zalopay|vietqr)", re.I)),
]


def detect_off_app_payment(body: str) -> str | None:
    """Trả về lý do nghi vấn, hoặc None. Không bao giờ chặn tin."""
    for label, pattern in OFF_APP_PATTERNS:
        if pattern.search(body):
            return label
    return None


# --- Hội thoại ------------------------------------------------------------------------


async def get_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Không tìm thấy hội thoại")
    return conversation


def active_member(
    conversation: Conversation,
    *,
    user: User | None = None,
    staff: StaffUser | None = None,
) -> ConversationMember | None:
    for member in conversation.members:
        if member.left_at is not None:
            continue
        if user is not None and member.user_id == user.id:
            return member
        if staff is not None and member.staff_user_id == staff.id:
            return member
    return None


def assert_member(
    conversation: Conversation,
    *,
    user: User | None = None,
    staff: StaffUser | None = None,
) -> ConversationMember:
    member = active_member(conversation, user=user, staff=staff)
    if member is None:
        # Cùng một thông điệp với hội thoại không tồn tại: dò id để biết ai đang nói chuyện
        # với ai cũng là rò rỉ.
        raise PermissionDeniedError("Không tìm thấy hội thoại")
    return member


async def get_member_conversation(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    *,
    user: User | None = None,
    staff: StaffUser | None = None,
) -> tuple[Conversation, ConversationMember]:
    """Lấy hội thoại mà người gọi thật sự là thành viên — dùng cho bề mặt khách/tài xế.

    Hội thoại KHÔNG tồn tại và hội thoại của người khác trả về **cùng một** lỗi 403 với cùng
    một thông điệp. Trả 404 cho cái không tồn tại và 403 cho cái có thật là tự khai: người dò
    chỉ cần quét id rồi lọc theo mã trạng thái là biết chính xác hội thoại nào đang sống, dù
    không đọc được nội dung. Bài rà soát API bắt được đúng chỗ này.
    """
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise PermissionDeniedError("Không tìm thấy hội thoại")
    return conversation, assert_member(conversation, user=user, staff=staff)


async def get_or_create_trip_conversation(
    db: AsyncSession, *, trip_id: uuid.UUID, rider_id: uuid.UUID, driver_id: uuid.UUID
) -> Conversation:
    """Mở hội thoại cho chuyến ngay khi ghép được tài xế (P2-07).

    Tự mở chứ không đợi ai bấm: khách vừa được ghép là lúc họ cần hỏi "anh đang ở đâu",
    và bắt họ tìm nút mở chat trước khi hỏi được là hỏng đúng khoảnh khắc quan trọng nhất.
    """
    existing = (
        await db.execute(select(Conversation).where(Conversation.trip_id == trip_id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    conversation = Conversation(kind=ConversationKind.TRIP, trip_id=trip_id)
    db.add(conversation)
    await db.flush()
    db.add_all(
        [
            ConversationMember(
                conversation_id=conversation.id, user_id=rider_id, role=MemberRole.RIDER
            ),
            ConversationMember(
                conversation_id=conversation.id, user_id=driver_id, role=MemberRole.DRIVER
            ),
        ]
    )
    await db.commit()
    await db.refresh(conversation)
    log_event(logger, "chat_trip_conversation_opened", trip_id=str(trip_id))
    return conversation


async def close_stale_trip_conversations(
    db: AsyncSession, *, older_than_hours: int = 24, now: datetime | None = None
) -> int:
    """Đóng hội thoại của chuyến đã kết thúc quá lâu (P2-07).

    Không xoá, chỉ đóng: nội dung vẫn tra cứu được khi có khiếu nại, nhưng không ai gửi thêm
    được vào một chuyến của tuần trước.
    """
    from app.core.constants import TERMINAL_TRIP_STATUSES
    from app.domains.trips.models import Trip

    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(hours=older_than_hours)

    stmt = (
        select(Conversation)
        .join(Trip, Trip.id == Conversation.trip_id)
        .where(
            Conversation.status == ConversationStatus.OPEN,
            Conversation.kind == ConversationKind.TRIP,
            Trip.status.in_(TERMINAL_TRIP_STATUSES),
        )
    )
    closed = 0
    for conversation in (await db.execute(stmt)).scalars().all():
        moc = conversation.last_message_at or conversation.created_at
        if moc.tzinfo is None:
            moc = moc.replace(tzinfo=timezone.utc)
        if moc <= cutoff:
            conversation.status = ConversationStatus.CLOSED
            conversation.closed_at = moment
            closed += 1
    if closed:
        await db.commit()
        log_event(logger, "chat_conversations_closed", count=closed)
    return closed


# --- Tin nhắn -------------------------------------------------------------------------


async def send_message(
    db: AsyncSession,
    conversation: Conversation,
    *,
    body: str,
    sender_user: User | None = None,
    sender_staff: StaffUser | None = None,
    client_msg_id: str | None = None,
    kind: MessageKind = MessageKind.TEXT,
) -> tuple[Message, bool]:
    """Gửi tin. Trả về (tin nhắn, có phải tin mới không).

    Gửi lại cùng `client_msg_id` trả về ĐÚNG tin cũ thay vì tạo tin thứ hai — app mất sóng
    rồi bấm gửi lại là chuyện xảy ra hằng ngày, không phải trường hợp hiếm.
    """
    if conversation.status is ConversationStatus.CLOSED:
        raise ConflictError("Hội thoại đã đóng")

    if client_msg_id:
        existing = (
            await db.execute(
                select(Message).where(
                    Message.conversation_id == conversation.id,
                    Message.client_msg_id == client_msg_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False

    reason = detect_off_app_payment(body) if kind is MessageKind.TEXT else None
    message = Message(
        conversation_id=conversation.id,
        kind=kind,
        body=body,
        client_msg_id=client_msg_id,
        sender_user_id=sender_user.id if sender_user else None,
        sender_staff_id=sender_staff.id if sender_staff else None,
        flagged_off_app=reason is not None,
        flag_reason=reason,
    )
    db.add(message)
    conversation.last_message_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError:
        # Hai request cùng client_msg_id chạy song song: ràng buộc duy nhất ở DB chặn lại,
        # và ở đây trả về tin đã có. Kiểm tra ở tầng ứng dụng phía trên chỉ giảm số lần
        # chạm tới nhánh này, không thay thế được nó.
        await db.rollback()
        existing = (
            await db.execute(
                select(Message).where(
                    Message.conversation_id == conversation.id,
                    Message.client_msg_id == client_msg_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing, False

    await db.refresh(message)
    if reason:
        log_event(
            logger,
            "chat_off_app_payment_flagged",
            conversation_id=str(conversation.id),
            message_id=str(message.id),
            reason=reason,
        )
    return message, True


async def list_messages(
    db: AsyncSession,
    conversation: Conversation,
    *,
    before: datetime | None = None,
    after: datetime | None = None,
    limit: int = 50,
) -> list[Message]:
    """Lịch sử hội thoại.

    `before` để cuộn ngược xem tin cũ. `after` là **đồng bộ bù** sau khi mất kết nối: app gửi
    mốc tin cuối nó có, nhận về đúng phần đã lỡ theo thứ tự thời gian (P2-03).
    """
    stmt = select(Message).where(Message.conversation_id == conversation.id)
    if before:
        stmt = stmt.where(Message.created_at < before).order_by(
            Message.created_at.desc(), Message.id.desc()
        )
    else:
        if after:
            stmt = stmt.where(Message.created_at > after)
        stmt = stmt.order_by(Message.created_at.asc(), Message.id.asc())

    rows = list((await db.execute(stmt.limit(limit))).scalars().all())
    # Luôn trả về theo chiều thời gian tăng dần để client chỉ có một cách ghép vào danh sách.
    return sorted(rows, key=lambda m: (m.created_at, str(m.id)))


async def mark_read(
    db: AsyncSession, conversation: Conversation, member: ConversationMember, message_id: uuid.UUID
) -> ConversationMember:
    """Đánh dấu đã đọc tới một tin (P2-04).

    Chỉ tiến, không lùi: hai thiết bị của cùng một người đọc lệch nhau thì mốc đã đọc phải là
    mốc xa nhất, nếu không số chưa đọc sẽ nhảy lung tung giữa điện thoại và máy tính.
    """
    message = await db.get(Message, message_id)
    if message is None or message.conversation_id != conversation.id:
        raise NotFoundError("Tin nhắn không thuộc hội thoại này")

    current = member.last_read_at
    if current is not None and current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    created = message.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    if current is None or created > current:
        member.last_read_at = created
        member.last_read_message_id = message.id
        await db.commit()
        await db.refresh(member)
    return member


async def unread_count(
    db: AsyncSession, conversation: Conversation, member: ConversationMember
) -> int:
    """Số tin chưa đọc. Không đếm tin của chính mình — không ai có tin chưa đọc của bản thân."""
    stmt = (
        select(func.count()).select_from(Message).where(Message.conversation_id == conversation.id)
    )
    if member.user_id:
        stmt = stmt.where(
            or_(Message.sender_user_id != member.user_id, Message.sender_user_id.is_(None))
        )
    elif member.staff_user_id:
        stmt = stmt.where(
            or_(Message.sender_staff_id != member.staff_user_id, Message.sender_staff_id.is_(None))
        )
    if member.last_read_at:
        stmt = stmt.where(Message.created_at > member.last_read_at)
    return int(await db.scalar(stmt) or 0)


async def list_conversations_for_user(
    db: AsyncSession, user: User, *, limit: int = 50
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
        .where(ConversationMember.user_id == user.id, ConversationMember.left_at.is_(None))
        .order_by(Conversation.last_message_at.desc().nullslast())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


# --- Hội thoại 3 bên ------------------------------------------------------------------


async def agent_join(
    db: AsyncSession, conversation: Conversation, staff: StaffUser
) -> ConversationMember:
    """CSKH tham gia hội thoại của khách và tài xế (P2-06).

    Sinh một tin hệ thống để CẢ HAI bên nhìn thấy. Người thứ ba đọc được cuộc trò chuyện mà
    hai người kia không biết là chuyện không được phép xảy ra — vừa sai về quyền riêng tư,
    vừa làm khách mất lòng tin khi phát hiện ra sau.
    """
    # Hỏi thẳng DB: quan hệ `conversation.members` được nạp lúc truy vấn, nên sau khi vừa
    # thêm một thành viên nó vẫn là ảnh cũ và ta sẽ thêm trùng.
    existing = (
        await db.execute(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation.id,
                ConversationMember.staff_user_id == staff.id,
                ConversationMember.left_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    member = ConversationMember(
        conversation_id=conversation.id, staff_user_id=staff.id, role=MemberRole.AGENT
    )
    db.add(member)
    await db.flush()
    await send_message(
        db,
        conversation,
        body=f"{staff.full_name} (CSKH GoAn) đã tham gia hội thoại",
        sender_staff=staff,
        kind=MessageKind.SYSTEM,
    )
    await db.refresh(member)
    # Nạp lại danh sách thành viên: người gọi đang giữ đối tượng Conversation cũ, và nếu
    # không làm mới thì họ vừa thêm CSKH xong mà hỏi lại vẫn thấy chưa có ai.
    await db.refresh(conversation, ["members"])
    log_event(
        logger,
        "chat_agent_joined",
        conversation_id=str(conversation.id),
        staff_id=str(staff.id),
    )
    return member


async def agent_leave(db: AsyncSession, conversation: Conversation, staff: StaffUser) -> None:
    member = (
        await db.execute(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation.id,
                ConversationMember.staff_user_id == staff.id,
                ConversationMember.left_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if member is None:
        return
    member.left_at = datetime.now(timezone.utc)
    await db.flush()
    await send_message(
        db,
        conversation,
        body=f"{staff.full_name} (CSKH GoAn) đã rời hội thoại",
        sender_staff=staff,
        kind=MessageKind.SYSTEM,
    )
    await db.refresh(conversation, ["members"])
    log_event(
        logger, "chat_agent_left", conversation_id=str(conversation.id), staff_id=str(staff.id)
    )
