"""Hội thoại: khử trùng, đồng bộ bù, đã đọc, 3 bên, cờ thanh toán ngoài app (PRD-CHAT-01…06).

Bốn tình huống dưới đây là toàn bộ lý do chat khó, và cả bốn đều là chuyện xảy ra hằng ngày
trên mạng di động Việt Nam chứ không phải trường hợp hiếm:

  1. Mất sóng giữa lúc gửi, người dùng bấm gửi lại → không được thành hai tin.
  2. Mất mạng 5 phút rồi nối lại → phải thấy đủ tin đã lỡ, không thiếu không trùng.
  3. CSKH nhảy vào giữa cuộc trò chuyện → cả hai bên phải biết.
  4. Rủ nhau chuyển khoản ngoài app → phải thấy được, nhưng KHÔNG chặn.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.constants import TripStatus
from app.core.exceptions import ConflictError, PermissionDeniedError
from app.domains.chat import service
from app.domains.chat.constants import ConversationStatus, MessageKind
from app.domains.chat.models import Conversation, Message
from tests.conftest import create_driver, create_rider, create_trip
from tests.domains.test_iam import make_staff


async def _trip_chat(db, *, rider_phone="0901000031", driver_phone="0902000031"):
    rider = await create_rider(db, phone=rider_phone)
    driver_user, _ = await create_driver(db, phone=driver_phone)
    trip = await create_trip(db, rider, driver_user, status=TripStatus.DRIVER_ARRIVING)
    conversation = await service.get_or_create_trip_conversation(
        db, trip_id=trip.id, rider_id=rider.id, driver_id=driver_user.id
    )
    return rider, driver_user, trip, conversation


# --- Khử trùng (P2-02) ----------------------------------------------------------------


@pytest.mark.integration
async def test_gui_lai_cung_client_msg_id_khong_tao_tin_thu_hai(db):
    """QA-CHAT-02. Mất sóng rồi bấm gửi lại là chuyện hằng ngày. Thấy tin của mình hiện
    hai lần thì người dùng nghĩ hệ thống hỏng — và họ đúng."""
    rider, _, _, conversation = await _trip_chat(db)

    lan_1, moi_1 = await service.send_message(
        db, conversation, body="Anh ơi em ở cổng sau nhé", sender_user=rider, client_msg_id="m-1"
    )
    lan_2, moi_2 = await service.send_message(
        db, conversation, body="Anh ơi em ở cổng sau nhé", sender_user=rider, client_msg_id="m-1"
    )

    assert moi_1 is True and moi_2 is False
    assert lan_1.id == lan_2.id
    assert len((await db.execute(select(Message))).scalars().all()) == 1


@pytest.mark.integration
async def test_khong_co_client_msg_id_thi_van_gui_duoc_binh_thuong(db):
    rider, _, _, conversation = await _trip_chat(db)

    await service.send_message(db, conversation, body="Tin 1", sender_user=rider)
    await service.send_message(db, conversation, body="Tin 2", sender_user=rider)

    assert len(await service.list_messages(db, conversation)) == 2


# --- Đồng bộ bù (P2-03) ---------------------------------------------------------------


@pytest.mark.integration
async def test_mat_mang_roi_noi_lai_thay_du_tin_da_lo(db):
    """QA-CHAT-03, DoD của P2-03: mất mạng 5 phút, nối lại thấy đủ tin đã lỡ."""
    rider, driver_user, _, conversation = await _trip_chat(db)
    truoc_khi_mat_mang, _ = await service.send_message(
        db, conversation, body="Em ra ngay", sender_user=rider
    )
    for i in range(3):
        await service.send_message(db, conversation, body=f"Tin lỡ {i}", sender_user=driver_user)

    da_lo = await service.list_messages(db, conversation, after=truoc_khi_mat_mang.created_at)

    assert [m.body for m in da_lo] == ["Tin lỡ 0", "Tin lỡ 1", "Tin lỡ 2"]


@pytest.mark.integration
async def test_cuon_nguoc_xem_tin_cu_va_luon_tra_theo_thu_tu_thoi_gian(db):
    rider, _, _, conversation = await _trip_chat(db)
    for i in range(5):
        await service.send_message(db, conversation, body=f"Tin {i}", sender_user=rider)
    tat_ca = await service.list_messages(db, conversation)

    cu_hon = await service.list_messages(db, conversation, before=tat_ca[3].created_at, limit=2)

    assert [m.body for m in cu_hon] == ["Tin 1", "Tin 2"]
    assert cu_hon[0].created_at <= cu_hon[1].created_at, "Client chỉ nên có một cách ghép danh sách"


# --- Đã đọc và chưa đọc (P2-04) -------------------------------------------------------


@pytest.mark.integration
async def test_dem_chua_doc_khong_tinh_tin_cua_chinh_minh(db):
    rider, driver_user, _, conversation = await _trip_chat(db)
    rider_member = service.active_member(conversation, user=rider)
    assert rider_member is not None

    await service.send_message(db, conversation, body="Của tôi", sender_user=rider)
    await service.send_message(db, conversation, body="Của tài xế 1", sender_user=driver_user)
    await service.send_message(db, conversation, body="Của tài xế 2", sender_user=driver_user)

    assert await service.unread_count(db, conversation, rider_member) == 2


@pytest.mark.integration
async def test_moc_da_doc_chi_tien_khong_lui(db):
    """Hai thiết bị của cùng một người đọc lệch nhau thì số chưa đọc không được nhảy lung tung."""
    rider, driver_user, _, conversation = await _trip_chat(db)
    rider_member = service.active_member(conversation, user=rider)
    assert rider_member is not None
    tin_1, _ = await service.send_message(db, conversation, body="Tin 1", sender_user=driver_user)
    tin_2, _ = await service.send_message(db, conversation, body="Tin 2", sender_user=driver_user)

    await service.mark_read(db, conversation, rider_member, tin_2.id)
    await service.mark_read(db, conversation, rider_member, tin_1.id)  # máy thứ hai đọc chậm hơn

    assert rider_member.last_read_message_id == tin_2.id
    assert await service.unread_count(db, conversation, rider_member) == 0


# --- Quyền (PRD-CHAT-05) --------------------------------------------------------------


@pytest.mark.security
@pytest.mark.integration
async def test_nguoi_ngoai_khong_doc_duoc_hoi_thoai(db):
    """Biết id hội thoại không đủ để đọc nó. Đây là tin nhắn riêng của hai người."""
    _, _, _, conversation = await _trip_chat(db)
    nguoi_la = await create_rider(db, phone="0901000099")

    with pytest.raises(PermissionDeniedError):
        service.assert_member(conversation, user=nguoi_la)


@pytest.mark.security
@pytest.mark.api
async def test_nguoi_ngoai_goi_api_thi_nhan_403_va_khong_biet_hoi_thoai_co_that_hay_khong(
    db, api_client
):
    from app.core.constants import UserRole
    from app.core.security import create_access_token

    _, _, _, conversation = await _trip_chat(db)
    nguoi_la = await create_rider(db, phone="0901000098")
    headers = {
        "Authorization": f"Bearer {create_access_token(str(nguoi_la.id), UserRole.RIDER.value)}"
    }

    co_that = await api_client.get(
        f"/api/v1/chat/conversations/{conversation.id}/messages", headers=headers
    )
    khong_co = await api_client.get(
        f"/api/v1/chat/conversations/{uuid.uuid4()}/messages", headers=headers
    )

    assert co_that.status_code == 403
    # Hội thoại có thật trả 403, không có thật trả 404 — nhưng thông điệp giống nhau nên
    # người dò không suy ra được gì từ nội dung.
    assert co_that.json()["error"]["message"] == khong_co.json()["error"]["message"]


# --- Hội thoại 3 bên (P2-06) ----------------------------------------------------------


@pytest.mark.integration
async def test_cskh_tham_gia_thi_ca_hai_ben_deu_thay_thong_bao(db):
    """QA-CHAT-05, DoD của P2-06. Người thứ ba đọc được cuộc trò chuyện mà hai người kia không biết là
    chuyện không được phép xảy ra."""
    rider, _, _, conversation = await _trip_chat(db)
    agent = await make_staff(db, email="cskh@goan.vn", roles=["cs_agent"])

    await service.agent_join(db, conversation, agent)

    messages = await service.list_messages(db, conversation)
    assert len(messages) == 1
    assert messages[0].kind is MessageKind.SYSTEM
    assert "đã tham gia hội thoại" in messages[0].body
    assert service.active_member(conversation, staff=agent) is not None
    assert service.active_member(conversation, user=rider) is not None


@pytest.mark.integration
async def test_cskh_roi_di_thi_ghi_moc_chu_khong_xoa_dong(db):
    """QA-CHAT-06. Khiếu nại đến sau vài tuần, và câu hỏi đầu tiên luôn là lúc đó ai đang ở trong cuộc
    trò chuyện này."""
    _, _, _, conversation = await _trip_chat(db)
    agent = await make_staff(db, email="cskh2@goan.vn", roles=["cs_agent"])
    await service.agent_join(db, conversation, agent)

    await service.agent_leave(db, conversation, agent)
    await db.refresh(conversation)

    assert service.active_member(conversation, staff=agent) is None
    van_con_dong = [m for m in conversation.members if m.staff_user_id == agent.id]
    assert len(van_con_dong) == 1 and van_con_dong[0].left_at is not None
    assert "đã rời hội thoại" in (await service.list_messages(db, conversation))[-1].body


@pytest.mark.integration
async def test_tham_gia_hai_lan_khong_tao_thanh_vien_trung(db):
    _, _, _, conversation = await _trip_chat(db)
    agent = await make_staff(db, email="cskh3@goan.vn", roles=["cs_agent"])

    a = await service.agent_join(db, conversation, agent)
    b = await service.agent_join(db, conversation, agent)

    assert a.id == b.id
    assert len(await service.list_messages(db, conversation)) == 1


# --- Cờ thanh toán ngoài app (P2-11) --------------------------------------------------


@pytest.mark.security
@pytest.mark.unit
@pytest.mark.parametrize(
    "noi_dung",
    [
        "Anh chuyển khoản cho em qua 0123456789 nhé",
        "Huỷ app đi rồi trả tiền mặt luôn cho nhanh",
        "Số tk Vietcombank của em đây",
        "Quét mã momo này giúp em",
    ],
)
def test_phat_hien_ru_thanh_toan_ngoai_app(noi_dung):
    assert service.detect_off_app_payment(noi_dung) is not None


@pytest.mark.unit
@pytest.mark.parametrize(
    "noi_dung",
    ["Anh ơi em ra ngay", "Xe em màu trắng biển 51G", "5 phút nữa em tới cổng"],
)
def test_khong_gan_co_nham_tin_nhan_binh_thuong(noi_dung):
    assert service.detect_off_app_payment(noi_dung) is None


@pytest.mark.security
@pytest.mark.integration
async def test_tin_bi_nghi_van_van_duoc_gui_di_chu_khong_bi_chan(db):
    """QA-CHAT-07. Chặn nhầm một tin thật thì hai bên chuyển sang Zalo và mất luôn dấu vết — tệ hơn
    nhiều so với để tin đi qua nhưng có người xem lại."""
    rider, _, _, conversation = await _trip_chat(db)

    message, moi = await service.send_message(
        db, conversation, body="Chuyển khoản cho em 0123456789 nhé", sender_user=rider
    )

    assert moi is True
    assert message.flagged_off_app is True
    assert message.flag_reason
    assert message.body == "Chuyển khoản cho em 0123456789 nhé", "Nội dung không bị sửa"


@pytest.mark.unit
def test_tin_he_thong_khong_bi_quet_co(db=None):
    """Tin hệ thống do chính backend sinh ra, quét nó chỉ tạo báo động giả."""
    assert service.detect_off_app_payment("CSKH Minh đã tham gia hội thoại") is None


# --- Vòng đời hội thoại chuyến (P2-07) ------------------------------------------------


@pytest.mark.integration
async def test_mo_hoi_thoai_chuyen_hai_lan_van_la_mot(db):
    """QA-CHAT-01. Hai thiết bị cùng mở màn hình chat một lúc: nếu mỗi lần mở tạo một
    hội thoại thì hai bên nhắn vào hai phòng khác nhau và không ai thấy ai."""
    rider, driver_user, trip, conversation = await _trip_chat(db)

    lai = await service.get_or_create_trip_conversation(
        db, trip_id=trip.id, rider_id=rider.id, driver_id=driver_user.id
    )

    assert lai.id == conversation.id
    assert len((await db.execute(select(Conversation))).scalars().all()) == 1


@pytest.mark.integration
async def test_chuyen_da_ket_thuc_qua_24h_thi_dong_hoi_thoai(db):
    """QA-CHAT-04. Hội thoại không tự đóng thì khách nhắn tiếp vào chuyến của tuần trước
    và tài xế không bao giờ đọc — im lặng, chứ không báo lỗi."""
    _, _, trip, conversation = await _trip_chat(db)
    trip.status = TripStatus.COMPLETED
    conversation.last_message_at = datetime.now(timezone.utc) - timedelta(hours=30)
    await db.commit()

    assert await service.close_stale_trip_conversations(db) == 1

    await db.refresh(conversation)
    assert conversation.status is ConversationStatus.CLOSED
    assert conversation.closed_at is not None


@pytest.mark.integration
async def test_chuyen_dang_chay_thi_khong_dong_hoi_thoai(db):
    _, _, trip, conversation = await _trip_chat(db)
    trip.status = TripStatus.IN_PROGRESS
    conversation.last_message_at = datetime.now(timezone.utc) - timedelta(days=3)
    await db.commit()

    assert await service.close_stale_trip_conversations(db) == 0


@pytest.mark.integration
async def test_hoi_thoai_da_dong_thi_khong_gui_them_duoc(db):
    rider, _, _, conversation = await _trip_chat(db)
    conversation.status = ConversationStatus.CLOSED
    await db.commit()

    with pytest.raises(ConflictError):
        await service.send_message(db, conversation, body="Cho em hỏi thêm", sender_user=rider)


# --- Qua HTTP -------------------------------------------------------------------------


@pytest.mark.api
async def test_luong_chat_qua_http(db, api_client):
    from app.core.constants import UserRole
    from app.core.security import create_access_token

    rider, driver_user, _, conversation = await _trip_chat(
        db, rider_phone="0901000041", driver_phone="0902000041"
    )
    rider_headers = {
        "Authorization": f"Bearer {create_access_token(str(rider.id), UserRole.RIDER.value)}"
    }
    driver_headers = {
        "Authorization": f"Bearer {create_access_token(str(driver_user.id), UserRole.DRIVER.value)}"
    }

    gui = await api_client.post(
        f"/api/v1/chat/conversations/{conversation.id}/messages",
        headers=rider_headers,
        json={"body": "Em ở cổng sau nhé", "client_msg_id": "http-1"},
    )
    gui_lai = await api_client.post(
        f"/api/v1/chat/conversations/{conversation.id}/messages",
        headers=rider_headers,
        json={"body": "Em ở cổng sau nhé", "client_msg_id": "http-1"},
    )
    danh_sach = await api_client.get("/api/v1/chat/conversations", headers=driver_headers)

    assert gui.status_code == 201
    assert gui_lai.json()["id"] == gui.json()["id"], "Gửi lại không tạo tin thứ hai"
    assert danh_sach.status_code == 200
    assert danh_sach.json()[0]["unread_count"] == 1


@pytest.mark.api
async def test_danh_dau_da_doc_qua_http_lam_so_chua_doc_ve_khong(db, api_client):
    from app.core.constants import UserRole
    from app.core.security import create_access_token

    rider, driver_user, _, conversation = await _trip_chat(
        db, rider_phone="0901000042", driver_phone="0902000042"
    )
    tin, _ = await service.send_message(
        db, conversation, body="Anh tới rồi", sender_user=driver_user
    )
    headers = {
        "Authorization": f"Bearer {create_access_token(str(rider.id), UserRole.RIDER.value)}"
    }

    response = await api_client.post(
        f"/api/v1/chat/conversations/{conversation.id}/read",
        headers=headers,
        json={"message_id": str(tin.id)},
    )

    assert response.status_code == 200
    assert response.json()["unread_count"] == 0
