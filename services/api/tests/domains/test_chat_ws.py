"""Chat qua WebSocket: "đang gõ" và token hết hạn giữa chừng (P2-05, P2-14).

Hai thứ ở đây không đi qua REST nên không có test HTTP nào chạm tới được:

  1. "Đang gõ" cố tình KHÔNG lưu DB, nên bằng chứng duy nhất nó chạy đúng là ai nhận được gì.
  2. Token hết hạn giữa lúc đang kết nối. Không báo thì client giữ một kết nối đã vô hiệu và
     tưởng mình vẫn online — người dùng gõ tin, thấy nó "đã gửi", mà không ai nhận được.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.constants import TripStatus, UserRole
from app.core.security import create_access_token
from app.domains.chat import service as chat_service
from app.websocket import router as ws_router
from app.websocket.events import ClientEvent, ServerEvent
from tests.conftest import create_driver, create_rider, create_trip


class FakeSocket:
    """Ghi lại tin đã gửi và mã đóng kết nối."""

    def __init__(self, inbox: list[dict] | None = None) -> None:
        self.inbox = list(inbox or [])
        self.messages: list[dict] = []
        self.closed_code: int | None = None
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)

    async def receive_json(self) -> dict:
        from fastapi import WebSocketDisconnect

        if not self.inbox:
            raise WebSocketDisconnect(1000)
        return self.inbox.pop(0)

    async def close(self, code: int = 1000) -> None:
        self.closed_code = code


@pytest.fixture
def duong_day(db, monkeypatch):
    """Đấu WS router vào phiên DB của test và thu lại mọi tin gửi cho từng người."""

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(ws_router, "SessionFactory", lambda: _Ctx())

    hop_thu: dict[uuid.UUID, list[dict]] = {}

    async def _send_to_user(user_id, message):
        hop_thu.setdefault(user_id, []).append(message)

    monkeypatch.setattr(ws_router.manager, "send_to_user", _send_to_user)
    return hop_thu


@pytest.fixture
def ket_noi_tran(monkeypatch):
    """Bỏ qua phần đăng ký Redis pub/sub của connection manager.

    Test ở đây hỏi về vòng lặp nhận tin của endpoint, không phải về fan-out giữa các worker —
    thứ đã có test riêng. Để nguyên thì mỗi test lại dựng một listener task sống lâu hơn nó.
    """

    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr(ws_router.manager, "connect", _noop)
    monkeypatch.setattr(ws_router.manager, "disconnect", _noop)


async def _hoi_thoai(db, *, rider_phone="0901000041", driver_phone="0902000041"):
    rider = await create_rider(db, phone=rider_phone)
    driver_user, _ = await create_driver(db, phone=driver_phone)
    trip = await create_trip(db, rider, driver_user, status=TripStatus.DRIVER_ARRIVING)
    conversation = await chat_service.get_or_create_trip_conversation(
        db, trip_id=trip.id, rider_id=rider.id, driver_id=driver_user.id
    )
    return rider, driver_user, conversation


@pytest.mark.integration
async def test_dang_go_toi_dung_nguoi_con_lai_va_khong_doi_ve_nguoi_gui(db, duong_day):
    """QA-CHAT-08. Dội tín hiệu về chính người gõ thì màn hình của họ hiện "bạn đang gõ…" —
    vô nghĩa, và tốn đúng một lượt gửi cho mỗi phím bấm."""
    rider, driver_user, conversation = await _hoi_thoai(db)

    await ws_router._handle_message(
        rider.id,
        UserRole.RIDER,
        {"type": ClientEvent.CHAT_TYPING.value, "conversation_id": str(conversation.id)},
        FakeSocket(),
    )

    assert [m["type"] for m in duong_day[driver_user.id]] == [ServerEvent.CHAT_TYPING.value]
    assert duong_day[driver_user.id][0]["conversation_id"] == str(conversation.id)
    assert rider.id not in duong_day


@pytest.mark.security
@pytest.mark.integration
async def test_nguoi_ngoai_hoi_thoai_khong_phat_duoc_tin_hieu_dang_go(db, duong_day):
    """QA-CHAT-09. Biết id hội thoại không cho ai quyền làm phiền hai người trong đó — kênh WS
    phải kiểm tư cách thành viên y như REST."""
    _, driver_user, conversation = await _hoi_thoai(db)
    nguoi_la = await create_rider(db, phone="0901000042")

    await ws_router._handle_message(
        nguoi_la.id,
        UserRole.RIDER,
        {"type": ClientEvent.CHAT_TYPING.value, "conversation_id": str(conversation.id)},
        FakeSocket(),
    )

    assert duong_day == {}


@pytest.mark.integration
async def test_hoi_thoai_khong_ton_tai_thi_bo_qua_chu_khong_no(db, duong_day):
    """Client cũ giữ id của hội thoại đã bị dọn: bỏ qua, không được làm sập cả kết nối WS."""
    rider = await create_rider(db, phone="0901000043")

    await ws_router._handle_message(
        rider.id,
        UserRole.RIDER,
        {"type": ClientEvent.CHAT_TYPING.value, "conversation_id": str(uuid.uuid4())},
        FakeSocket(),
    )

    assert duong_day == {}


@pytest.mark.security
@pytest.mark.integration
async def test_token_het_han_giua_chung_thi_bao_roi_dong_ket_noi(db, monkeypatch, ket_noi_tran):
    """QA-CHAT-10. Kết nối mở từ trước vẫn sống sau khi token hết hạn: client tưởng mình
    online, gõ tin thấy "đã gửi", mà không ai nhận được."""
    rider = await create_rider(db, phone="0901000044")
    token = create_access_token(str(rider.id), UserRole.RIDER.value)

    het_han = datetime.now(timezone.utc) - timedelta(minutes=1)
    monkeypatch.setattr(
        ws_router,
        "decode_token",
        lambda _t: {"sub": str(rider.id), "role": UserRole.RIDER.value, "exp": het_han.timestamp()},
    )
    socket = FakeSocket(inbox=[{"type": ClientEvent.PING.value}])
    await ws_router.websocket_endpoint(socket, token=token)  # type: ignore[arg-type]

    assert [m["type"] for m in socket.messages] == [ServerEvent.AUTH_EXPIRED.value]
    assert socket.closed_code == 4401


@pytest.mark.integration
async def test_token_con_han_thi_phuc_vu_binh_thuong(db, ket_noi_tran):
    """Cặp của test trên: nếu chỉ có test hết hạn thì một lỗi so sánh ngược dấu vẫn xanh."""
    rider = await create_rider(db, phone="0901000045")
    token = create_access_token(str(rider.id), UserRole.RIDER.value)

    socket = FakeSocket(inbox=[{"type": ClientEvent.PING.value}])
    await ws_router.websocket_endpoint(socket, token=token)  # type: ignore[arg-type]

    assert [m["type"] for m in socket.messages] == [ServerEvent.PONG.value]
    assert socket.closed_code is None
