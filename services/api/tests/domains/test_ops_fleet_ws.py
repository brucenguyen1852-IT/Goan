"""Đẩy trạng thái đội xe qua WebSocket cho Console (PRD-OPS-14) — P1-09.

Ba thứ được chốt ở đây, và cả ba đều là lỗi đã từng gặp ở hệ thống thật:

  1. Kênh này phải kiểm quyền y như REST. Một WebSocket quên kiểm quyền là cửa sau mở toang:
     ai có token hợp lệ cũng xem được vị trí toàn bộ tài xế.
  2. Không có ai xem thì phải NGỪNG truy vấn DB. Vòng lặp nền chạy suốt đêm cho không ai đọc
     là cách đốt tiền hạ tầng êm ái nhất.
  3. Một tab chết không được làm hỏng lượt gửi của những người còn lại.
"""

import asyncio

import pytest

from app.core.constants import OnlineStatus, TripStatus
from app.websocket import ops_fleet
from app.websocket.events import ServerEvent
from tests.conftest import create_driver, create_rider, create_trip


class FakeSocket:
    """Ghi lại message nhận được. `alive=False` mô phỏng tab đã đóng mà chưa kịp báo."""

    def __init__(self, alive: bool = True) -> None:
        self.alive = alive
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        if not self.alive:
            raise RuntimeError("kết nối đã đóng")
        self.messages.append(message)


@pytest.fixture
def broadcaster(monkeypatch, db):
    """Broadcaster mới cho từng test, dùng chung phiên DB in-memory của test."""

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(ops_fleet, "SessionFactory", lambda: _Ctx())
    return ops_fleet.OpsFleetBroadcaster()


@pytest.mark.integration
async def test_anh_chup_dem_dung_tai_xe_online_va_chuyen_dang_chay(db, broadcaster):
    rider = await create_rider(db, phone="0901000021")
    driver_user, profile = await create_driver(db, phone="0902000021")
    profile.online_status = OnlineStatus.ON_TRIP
    await db.commit()
    await create_trip(db, rider, driver_user, status=TripStatus.IN_PROGRESS)

    snapshot = await ops_fleet.build_snapshot()

    assert snapshot["drivers_on_trip"] == 1
    assert snapshot["trips_active"] == 1
    assert snapshot["drivers"][0]["current_trip_id"] is not None


@pytest.mark.security
@pytest.mark.integration
async def test_anh_chup_khong_kem_so_dien_thoai(db, broadcaster):
    await create_driver(db, phone="0902000022")

    snapshot = await ops_fleet.build_snapshot()

    assert "0902000022" not in str(snapshot)


@pytest.mark.integration
async def test_gui_cho_moi_console_dang_mo(db, broadcaster):
    await create_driver(db, phone="0902000023")
    a, b = FakeSocket(), FakeSocket()
    await broadcaster.subscribe(a, "staff-1")
    await broadcaster.subscribe(b, "staff-2")

    sent = await broadcaster.broadcast_once()

    assert sent == 2
    assert a.messages[-1]["type"] == ServerEvent.OPS_FLEET_UPDATE.value
    assert b.messages[-1]["data"]["drivers_online"] == 1
    await broadcaster.shutdown()


@pytest.mark.integration
async def test_mot_tab_chet_khong_lam_hong_luot_gui_cua_nguoi_khac(db, broadcaster):
    await create_driver(db, phone="0902000024")
    song, chet = FakeSocket(), FakeSocket(alive=False)
    await broadcaster.subscribe(song, "staff-1")
    await broadcaster.subscribe(chet, "staff-2")

    sent = await broadcaster.broadcast_once()

    assert sent == 1
    assert len(song.messages) == 1
    assert broadcaster.viewer_count == 1, "Tab chết phải bị loại khỏi danh sách"
    await broadcaster.shutdown()


@pytest.mark.integration
async def test_khong_ai_xem_thi_khong_truy_van_gi_ca(db, broadcaster):
    """Vòng lặp nền chạy suốt đêm cho không ai đọc là cách đốt tiền hạ tầng êm nhất."""
    await create_driver(db, phone="0902000025")

    assert await broadcaster.broadcast_once() == 0


@pytest.mark.integration
async def test_nguoi_cuoi_cung_dong_tab_thi_vong_lap_dung_han(db, broadcaster):
    socket = FakeSocket()
    await broadcaster.subscribe(socket, "staff-1")
    dang_chay = broadcaster._task
    assert dang_chay is not None and not dang_chay.done()

    await broadcaster.unsubscribe(socket)
    await asyncio.sleep(0)

    assert broadcaster.viewer_count == 0
    assert broadcaster._task is None


class FakeWebSocket(FakeSocket):
    """Đủ bề mặt để gọi thẳng handler: mở, đóng, và một lần nhận rồi ngắt."""

    def __init__(self) -> None:
        super().__init__()
        self.closed_code: int | None = None
        self.accepted = False

    async def close(self, code: int = 1000) -> None:
        self.closed_code = code

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect(1000)


async def _open(db, monkeypatch, token: str) -> FakeWebSocket:
    from app.websocket import router as ws_router

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(ws_router, "SessionFactory", lambda: _Ctx())
    # Ảnh chụp gửi ngay lúc mở kết nối cũng phải đọc từ DB của test, không phải DB thật.
    monkeypatch.setattr(ops_fleet, "SessionFactory", lambda: _Ctx())
    socket = FakeWebSocket()
    await ws_router.ops_fleet_socket(socket, token=token)  # type: ignore[arg-type]
    # Vòng lặp nền dùng chung broadcaster toàn cục; chờ nó dừng hẳn trước khi test đóng DB,
    # nếu không nó sẽ truy vấn vào một phiên đã đóng ở bước dọn dẹp.
    await ops_fleet.broadcaster.shutdown()
    return socket


@pytest.mark.security
@pytest.mark.integration
async def test_token_cua_khach_khong_mo_duoc_kenh_doi_xe(db, monkeypatch):
    """Kênh này lộ vị trí toàn đội — WebSocket quên kiểm quyền là cửa sau mở toang."""
    from app.core.constants import UserRole
    from app.core.security import create_access_token

    rider = await create_rider(db, phone="0901000026")
    socket = await _open(db, monkeypatch, create_access_token(str(rider.id), UserRole.RIDER.value))

    assert socket.closed_code == 4403
    assert socket.accepted is False


@pytest.mark.security
@pytest.mark.integration
async def test_nhan_su_thieu_quyen_fleet_cung_bi_tu_choi(db, monkeypatch):
    """Kế toán có token nội bộ hợp lệ, nhưng không có việc gì với bản đồ đội xe."""
    from app.core.security import create_access_token
    from app.deps import STAFF_ROLE
    from tests.domains.test_iam import make_staff

    staff = await make_staff(db, email="ketoan-ws@goan.vn", roles=["finance_accountant"])
    socket = await _open(db, monkeypatch, create_access_token(str(staff.id), STAFF_ROLE))

    assert socket.closed_code == 4403


@pytest.mark.security
@pytest.mark.integration
async def test_dieu_phoi_mo_duoc_va_nhan_ngay_anh_chup_dau_tien(db, monkeypatch):
    """Không gửi ngay thì Console nhìn màn hình trống suốt 3 giây đầu."""
    from app.core.security import create_access_token
    from app.deps import STAFF_ROLE
    from tests.domains.test_iam import make_staff

    await create_driver(db, phone="0902000027")
    staff = await make_staff(db, email="dieuphoi-ws@goan.vn", roles=["dispatcher"])
    socket = await _open(db, monkeypatch, create_access_token(str(staff.id), STAFF_ROLE))

    assert socket.accepted is True
    assert socket.closed_code is None
    assert socket.messages[0]["type"] == ServerEvent.OPS_FLEET_UPDATE.value
    assert ops_fleet.broadcaster.viewer_count == 0, "Ngắt kết nối rồi thì phải rời danh sách"


@pytest.mark.security
@pytest.mark.integration
async def test_token_hong_bi_dong_voi_ma_4401(db, monkeypatch):
    socket = await _open(db, monkeypatch, "token-bia-dat")

    assert socket.closed_code == 4401
