"""Kịch bản chat từ đầu đến cuối: 3 bên, mất mạng, gửi trùng, ảnh, push (P2-21).

Khác với các file test kia — mỗi bài ở đó hỏi MỘT câu về MỘT hàm — mỗi bài ở đây kể trọn một
câu chuyện đi qua đúng chuỗi middleware thật, vì lỗi tệ nhất của hệ thống chat không nằm
trong một hàm nào cả. Nó nằm ở chỗ nối:

  - Khử trùng đúng, đồng bộ bù đúng, nhưng gộp lại thì tin đã lỡ hiện SAU tin mới.
  - CSKH vào hội thoại đúng, gửi tin đúng, nhưng số chưa đọc của khách không nhúc nhích.
  - Ảnh gắn đúng, push đúng, nhưng người đã rời hội thoại vẫn nhận được thông báo.

DoD của P2-21 chỉ có một câu: **không mất tin, không trùng tin trong mọi kịch bản.** Mỗi bài
dưới đây kết thúc bằng đúng phép đếm đó.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.constants import TripStatus, UserRole
from app.core.security import create_access_token
from app.domains.chat import service as chat
from app.domains.chat.constants import MessageKind
from app.domains.chat.models import Message
from app.domains.notifications import service as notifications
from app.domains.notifications.constants import DevicePlatform
from app.integrations.push import MockPushProvider, set_push
from tests.conftest import create_driver, create_rider, create_trip
from tests.domains.test_iam import make_staff, staff_headers


def _headers(user, role: UserRole) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), role.value)}"}


async def _chuyen_da_ghep(db, *, rider_phone, driver_phone):
    rider = await create_rider(db, phone=rider_phone)
    driver_user, _ = await create_driver(db, phone=driver_phone)
    trip = await create_trip(db, rider, driver_user, status=TripStatus.DRIVER_ARRIVING)
    conversation = await chat.get_or_create_trip_conversation(
        db, trip_id=trip.id, rider_id=rider.id, driver_id=driver_user.id
    )
    return rider, driver_user, trip, conversation


@pytest.fixture
def push_gia():
    from app.integrations import push as push_module

    cu = push_module.get_push()
    gia = MockPushProvider()
    set_push(gia)
    yield gia
    set_push(cu)


@pytest.mark.api
async def test_kich_ban_mat_mang_giua_chung_va_gui_trung(db, api_client):
    """QA-E2E-01. Khách đi thang máy: mất sóng giữa lúc gửi, bấm gửi lại, rồi lên mặt đất và
    đồng bộ bù.

    Đây là kịch bản gây ra nhiều báo lỗi nhất ở mọi ứng dụng chat trên mạng di động, và nó
    kết hợp hai cơ chế riêng biệt (khử trùng + phân trang con trỏ) mà mỗi cái đúng chưa đủ.
    """
    rider, driver_user, _, conv = await _chuyen_da_ghep(
        db, rider_phone="0901000111", driver_phone="0902000111"
    )
    kh = _headers(rider, UserRole.RIDER)
    tx = _headers(driver_user, UserRole.DRIVER)

    # 1. Khách gửi được một tin, app ghi lại mốc.
    dau = await api_client.post(
        f"/api/v1/chat/conversations/{conv.id}/messages",
        headers=kh,
        json={"body": "Anh ơi em ở cổng sau", "client_msg_id": "kh-1"},
    )
    assert dau.status_code == 201
    moc_cuoi = dau.json()["created_at"]

    # 2. Mất sóng ngay lúc gửi tin thứ hai — app không biết server đã nhận hay chưa, nên
    #    bấm gửi lại ba lần với cùng client_msg_id.
    for _ in range(3):
        lai = await api_client.post(
            f"/api/v1/chat/conversations/{conv.id}/messages",
            headers=kh,
            json={"body": "Anh tới chưa ạ", "client_msg_id": "kh-2"},
        )
        assert lai.status_code == 201
    id_lan_gui_lai = {lai.json()["id"]}

    # 3. Trong lúc khách mất mạng, tài xế trả lời hai tin.
    for i, noi_dung in enumerate(["Anh đang tới", "5 phút nữa nhé"], start=1):
        assert (
            await api_client.post(
                f"/api/v1/chat/conversations/{conv.id}/messages",
                headers=tx,
                json={"body": noi_dung, "client_msg_id": f"tx-{i}"},
            )
        ).status_code == 201

    # 4. Có mạng lại: đồng bộ bù từ mốc tin cuối app đang giữ.
    bu = await api_client.get(
        f"/api/v1/chat/conversations/{conv.id}/messages?after={moc_cuoi}",
        headers=kh,
    )
    assert bu.status_code == 200
    da_lo = bu.json()

    # KHÔNG MẤT TIN: đủ ba tin phát sinh sau mốc (một của mình, hai của tài xế).
    assert [m["body"] for m in da_lo] == ["Anh tới chưa ạ", "Anh đang tới", "5 phút nữa nhé"]
    # KHÔNG TRÙNG TIN: ba lần bấm gửi lại chỉ sinh đúng một dòng.
    assert len({m["id"] for m in da_lo} & id_lan_gui_lai) == 1
    tat_ca = (await db.execute(select(Message))).scalars().all()
    assert len(tat_ca) == 4
    assert len({m.id for m in tat_ca}) == 4


@pytest.mark.api
async def test_kich_ban_cskh_vao_giua_cuoc_tro_chuyen_ba_ben(db, api_client):
    """QA-E2E-02. Khách khiếu nại giữa chuyến, CSKH vào hội thoại, xử lý xong rồi rời đi.

    Điều kiện của kịch bản này: cả hai bên đều PHẢI biết có người thứ ba, ở đúng thời điểm
    người đó vào và ra. Đọc được cuộc trò chuyện mà hai người kia không biết là chuyện không
    được phép xảy ra.
    """
    rider, driver_user, _, conv = await _chuyen_da_ghep(
        db, rider_phone="0901000112", driver_phone="0902000112"
    )
    kh = _headers(rider, UserRole.RIDER)
    tx = _headers(driver_user, UserRole.DRIVER)
    cskh = await staff_headers(db, api_client, roles=["cs_lead"], email="lead-e2e@goan.vn")

    await api_client.post(
        f"/api/v1/chat/conversations/{conv.id}/messages",
        headers=kh,
        json={"body": "Anh tài xế đi sai đường"},
    )

    vao = await api_client.post(f"/api/v1/ops/chat/conversations/{conv.id}/join", headers=cskh)
    assert vao.status_code == 200

    await api_client.post(
        f"/api/v1/ops/support/tickets/{uuid.uuid4()}/reply", headers=cskh, json={"body": "x"}
    )  # ticket không tồn tại: không được ảnh hưởng gì tới hội thoại đang mở

    ra = await api_client.post(f"/api/v1/ops/chat/conversations/{conv.id}/leave", headers=cskh)
    assert ra.status_code == 200

    # Cả hai bên nhìn thấy CÙNG một dòng thời gian, kể cả hai tin hệ thống.
    nhin_tu_khach = (
        await api_client.get(f"/api/v1/chat/conversations/{conv.id}/messages", headers=kh)
    ).json()
    nhin_tu_tai_xe = (
        await api_client.get(f"/api/v1/chat/conversations/{conv.id}/messages", headers=tx)
    ).json()

    assert [m["id"] for m in nhin_tu_khach] == [m["id"] for m in nhin_tu_tai_xe]
    he_thong = [m["body"] for m in nhin_tu_khach if m["kind"] == "system"]
    assert len(he_thong) == 2
    assert "tham gia hội thoại" in he_thong[0] and "rời hội thoại" in he_thong[1]


@pytest.mark.api
async def test_kich_ban_gui_anh_hien_truong_roi_tra_cuu_lai_sau_khieu_nai(db, api_client):
    """QA-E2E-03. Tai nạn: khách gửi ảnh hiện trường, CSKH tra lại hội thoại sau đó.

    Ảnh phải đi qua đúng ba bước (xin URL → gửi tin → đọc bằng URL ký hạn) và bước cuối phải
    còn dùng được khi khiếu nại quay lại vài ngày sau — nhưng chỉ với người có quyền.
    """
    rider, _, _, conv = await _chuyen_da_ghep(
        db, rider_phone="0901000113", driver_phone="0902000113"
    )
    kh = _headers(rider, UserRole.RIDER)
    cskh = await staff_headers(db, api_client, roles=["cs_lead"], email="lead-anh@goan.vn")

    xin = await api_client.post(
        "/api/v1/chat/attachments",
        headers=kh,
        json={
            "conversation_id": str(conv.id),
            "content_type": "image/jpeg",
            "size_bytes": 320_000,
        },
    )
    assert xin.status_code == 201
    attachment_id = xin.json()["attachment_id"]

    gui = await api_client.post(
        f"/api/v1/chat/conversations/{conv.id}/messages",
        headers=kh,
        json={"body": "Ảnh hiện trường ạ", "attachment_id": attachment_id, "client_msg_id": "a-1"},
    )
    assert gui.status_code == 201 and gui.json()["kind"] == "image"

    # Gửi lại đúng client_msg_id (mất sóng lúc gửi ảnh) không tạo tin thứ hai, và cũng không
    # thất bại vì ảnh "đã dùng rồi".
    lai = await api_client.post(
        f"/api/v1/chat/conversations/{conv.id}/messages",
        headers=kh,
        json={"body": "Ảnh hiện trường ạ", "attachment_id": attachment_id, "client_msg_id": "a-1"},
    )
    assert lai.status_code == 201 and lai.json()["id"] == gui.json()["id"]
    assert len((await db.execute(select(Message))).scalars().all()) == 1

    # Khiếu nại đến sau: CSKH tra lại và đọc được nội dung.
    tra_cuu = await api_client.get(f"/api/v1/ops/chat/search?user_id={rider.id}", headers=cskh)
    assert tra_cuu.status_code == 200
    assert str(conv.id) in [c["id"] for c in tra_cuu.json()]

    doc = await api_client.get(f"/api/v1/ops/chat/conversations/{conv.id}/messages", headers=cskh)
    assert [m["kind"] for m in doc.json()] == ["image"]


@pytest.mark.integration
async def test_kich_ban_nguoi_nhan_dong_app_thi_nhan_push_dung_mot_lan(db, push_gia):
    """QA-E2E-04. Tài xế đóng app; khách nhắn ba tin liên tiếp.

    Hai điều kiện đi ngược nhau và phải cùng đúng: không được im lặng (tài xế phải biết có
    tin), và không được bắn một thông báo cho mỗi tin — ba tin trong mười giây mà rung ba
    lần là cách làm người ta tắt thông báo của ứng dụng.
    """
    rider, driver_user, _, conv = await _chuyen_da_ghep(
        db, rider_phone="0901000114", driver_phone="0902000114"
    )
    await notifications.register_push_token(
        db, driver_user, token="fcm-e2e", platform=DevicePlatform.ANDROID
    )

    tins = []
    for i, noi_dung in enumerate(["Anh ơi", "Em ở cổng sau", "Anh tới chưa"], start=1):
        tin, _ = await chat.send_message(
            db, conv, body=noi_dung, sender_user=rider, client_msg_id=f"kh-{i}"
        )
        tins.append(tin)

    # Job push chạy sau vài giây cho từng tin. Tin nào tới lượt mà đã đọc thì thôi.
    assert await chat.deliver_offline_push(db, tins[0].id, driver_user.id) == 1

    # Tài xế mở app và đọc tới tin cuối: hai job còn lại phải im.
    member = chat.active_member(conv, user=driver_user)
    await chat.mark_read(db, conv, member, tins[-1].id)
    assert await chat.deliver_offline_push(db, tins[1].id, driver_user.id) == 0
    assert await chat.deliver_offline_push(db, tins[2].id, driver_user.id) == 0

    assert len(push_gia.sent) == 1
    # Nội dung ba tin không được rò ra màn hình khoá.
    for noi_dung in ["Anh ơi", "Em ở cổng sau", "Anh tới chưa"]:
        assert noi_dung not in str(push_gia.sent[0])


@pytest.mark.api
async def test_kich_ban_khieu_nai_tron_vong_tu_mo_ticket_toi_ket_luan(db, api_client):
    """QA-E2E-05. Khách mở ticket, CSKH nhận, trả lời, kết luận — rồi khách mở lại.

    Vòng này chạm vào cả bốn cam kết SLA cùng lúc, và điều phải đúng ở cuối là dấu vết: mọi
    bước còn nguyên trong `ticket_events`, kể cả bước mở lại.
    """
    rider = await create_rider(db, phone="0901000115")
    kh = _headers(rider, UserRole.RIDER)
    cskh = await staff_headers(db, api_client, roles=["cs_lead"], email="lead-vong@goan.vn")

    mo = await api_client.post(
        "/api/v1/support/tickets",
        headers=kh,
        json={"subject": "Bị trừ tiền hai lần", "category": "payment", "body": "Em bị trừ 2 lần"},
    )
    assert mo.status_code == 201
    ticket = mo.json()
    assert ticket["priority"] == "high" and ticket["team"] == "finance"

    tra_loi = await api_client.post(
        f"/api/v1/ops/support/tickets/{ticket['id']}/reply",
        headers=cskh,
        json={"body": "Em đang kiểm tra giao dịch của anh/chị ạ"},
    )
    assert tra_loi.status_code == 200

    ket = await api_client.post(
        f"/api/v1/ops/support/tickets/{ticket['id']}/resolve",
        headers=cskh,
        json={"note": "Đã hoàn tiền giao dịch trùng"},
    )
    assert ket.status_code == 200 and ket.json()["status"] == "resolved"

    lai = await api_client.post(
        f"/api/v1/ops/support/tickets/{ticket['id']}/reopen",
        headers=cskh,
        json={"reason": "Khách báo chưa nhận được tiền"},
    )
    assert lai.status_code == 200 and lai.json()["reopened_count"] == 1
    # Đồng hồ SLA chạy lại: vòng khiếu nại này chưa được trả lời.
    assert lai.json()["first_response_at"] is None

    dau_vet = await api_client.get(
        f"/api/v1/ops/support/tickets/{ticket['id']}/events", headers=cskh
    )
    assert [e["event_type"] for e in dau_vet.json()] == [
        "created",
        "assigned",
        "first_response",
        "resolved",
        "reopened",
    ]

    # Khách vẫn đọc được toàn bộ hội thoại của ticket, kể cả tin hệ thống lúc CSKH vào.
    tin = await api_client.get(
        f"/api/v1/chat/conversations/{ticket['conversation_id']}/messages", headers=kh
    )
    assert [m["kind"] for m in tin.json()] == ["text", "system", "text"]


@pytest.mark.api
async def test_kich_ban_hai_thiet_bi_cua_cung_mot_nguoi_khong_lam_lech_so_chua_doc(db, api_client):
    """QA-E2E-06. Khách mở app trên điện thoại và trên web cùng lúc.

    Hai thiết bị đọc lệch nhau là chuyện thường; số chưa đọc nhảy ngược thì không. Người dùng
    thấy "1 tin chưa đọc" xuất hiện lại sau khi vừa đọc xong sẽ mở ra và không thấy gì mới —
    ba lần như thế là họ ngừng tin vào con số đó.
    """
    rider, driver_user, _, conv = await _chuyen_da_ghep(
        db, rider_phone="0901000116", driver_phone="0902000116"
    )
    kh = _headers(rider, UserRole.RIDER)
    tx = _headers(driver_user, UserRole.DRIVER)

    ids = []
    for i in range(3):
        r = await api_client.post(
            f"/api/v1/chat/conversations/{conv.id}/messages",
            headers=tx,
            json={"body": f"tin {i}", "client_msg_id": f"tx-{i}"},
        )
        ids.append(r.json()["id"])

    # Máy A đọc hết.
    a = await api_client.post(
        f"/api/v1/chat/conversations/{conv.id}/read", headers=kh, json={"message_id": ids[-1]}
    )
    assert a.json()["unread_count"] == 0

    # Máy B (chậm mạng) gửi mốc cũ hơn: KHÔNG được kéo số chưa đọc lên lại.
    b = await api_client.post(
        f"/api/v1/chat/conversations/{conv.id}/read", headers=kh, json={"message_id": ids[0]}
    )
    assert b.json()["unread_count"] == 0

    danh_sach = await api_client.get("/api/v1/chat/conversations", headers=kh)
    assert [c["unread_count"] for c in danh_sach.json()] == [0]


@pytest.mark.security
@pytest.mark.api
async def test_kich_ban_chuyen_ket_thuc_roi_thi_hoi_thoai_dong_va_khong_ai_gui_them(db, api_client):
    """QA-E2E-07. Chuyến xong, 25 giờ sau job dọn chạy, rồi cả hai bên thử nhắn tiếp.

    Đóng hội thoại mà vẫn cho gửi thì việc đóng chỉ là trang trí. Đọc lại thì vẫn phải được:
    khiếu nại đến sau vài tuần và nội dung là bằng chứng.
    """
    rider, driver_user, trip, conv = await _chuyen_da_ghep(
        db, rider_phone="0901000117", driver_phone="0902000117"
    )
    kh = _headers(rider, UserRole.RIDER)
    tx = _headers(driver_user, UserRole.DRIVER)
    await api_client.post(
        f"/api/v1/chat/conversations/{conv.id}/messages",
        headers=kh,
        json={"body": "Cảm ơn anh nhé"},
    )

    trip.status = TripStatus.COMPLETED
    conv.last_message_at = datetime.now(timezone.utc) - timedelta(hours=25)
    await db.commit()
    assert await chat.close_stale_trip_conversations(db) == 1

    for headers in (kh, tx):
        chan = await api_client.post(
            f"/api/v1/chat/conversations/{conv.id}/messages",
            headers=headers,
            json={"body": "Alo"},
        )
        assert chan.status_code == 409

    doc_lai = await api_client.get(f"/api/v1/chat/conversations/{conv.id}/messages", headers=kh)
    assert doc_lai.status_code == 200
    assert [m["body"] for m in doc_lai.json()] == ["Cảm ơn anh nhé"]


@pytest.mark.security
@pytest.mark.api
async def test_kich_ban_ru_thanh_toan_ngoai_app_bi_gan_co_nhung_tin_van_di(db, api_client):
    """QA-E2E-08. Tài xế rủ khách chuyển khoản trực tiếp giữa chuyến.

    Chặn tin là hai bên chuyển sang Zalo và mất luôn dấu vết — lúc đó không còn gì để rà
    soát. Cờ mà không chặn mới giữ được bằng chứng, và đó là lựa chọn có chủ đích.
    """
    rider, driver_user, _, conv = await _chuyen_da_ghep(
        db, rider_phone="0901000118", driver_phone="0902000118"
    )
    tx = _headers(driver_user, UserRole.DRIVER)
    kh = _headers(rider, UserRole.RIDER)

    gui = await api_client.post(
        f"/api/v1/chat/conversations/{conv.id}/messages",
        headers=tx,
        json={"body": "Em chuyển khoản Vietcombank 0123456789 cho anh nhé, khỏi qua app"},
    )
    assert gui.status_code == 201

    # Khách vẫn đọc được tin — không bị chặn, không bị sửa.
    khach_thay = await api_client.get(f"/api/v1/chat/conversations/{conv.id}/messages", headers=kh)
    assert "0123456789" in khach_thay.json()[0]["body"]

    # Nhưng tin đã bị gắn cờ để rà soát.
    tin = (await db.execute(select(Message))).scalars().one()
    assert tin.flagged_off_app is True
    assert tin.flag_reason


@pytest.mark.api
async def test_kich_ban_cskh_khong_de_lai_lo_hong_khi_roi_hoi_thoai(db, api_client):
    """QA-E2E-09. CSKH rời hội thoại rồi thử đọc tiếp bằng quyền `read_own`.

    Rời đi mà vẫn đọc được là quyền không thu hồi — và đó là loại lỗ hổng không ai phát hiện
    vì mọi thứ trên giao diện trông vẫn đúng.
    """
    _, _, _, conv = await _chuyen_da_ghep(db, rider_phone="0901000119", driver_phone="0902000119")
    agent = await make_staff(db, email="cs-roi@goan.vn", roles=["cs_agent"])
    headers = await staff_headers(db, api_client, roles=["cs_agent"], email="cs-khac-roi@goan.vn")

    await chat.agent_join(db, conv, agent)
    await chat.agent_leave(db, conv, agent)

    # Agent khác (chưa từng vào) đọc bằng read_own: bị từ chối.
    tra_loi = await api_client.get(
        f"/api/v1/ops/chat/conversations/{conv.id}/messages", headers=headers
    )
    assert tra_loi.status_code == 403

    # Chính agent đã rời cũng không còn là thành viên.
    assert chat.active_member(conv, staff=agent) is None


@pytest.mark.integration
async def test_kich_ban_tin_he_thong_khong_bao_gio_bi_gan_co_hay_dem_chua_doc_sai(db):
    """QA-E2E-10. Tin hệ thống do backend sinh ra, đi lẫn trong dòng thời gian của người dùng.

    Hai chỗ dễ sai cùng lúc: quét cờ thanh toán ngoài app trên chính văn bản mình vừa sinh
    (báo động giả vĩnh viễn), và đếm nó vào số chưa đọc của người gửi.
    """
    rider, driver_user, _, conv = await _chuyen_da_ghep(
        db, rider_phone="0901000120", driver_phone="0902000120"
    )
    agent = await make_staff(db, email="cs-he-thong@goan.vn", roles=["cs_agent"])

    await chat.send_message(db, conv, body="Anh ơi", sender_user=rider)
    await chat.agent_join(db, conv, agent)

    tins = (await db.execute(select(Message))).scalars().all()
    he_thong = [m for m in tins if m.kind is MessageKind.SYSTEM]
    assert len(he_thong) == 1
    assert he_thong[0].flagged_off_app is False

    # Tài xế chưa đọc gì: đếm đủ cả tin người lẫn tin hệ thống, không thiếu không thừa.
    member = chat.active_member(conv, user=driver_user)
    assert await chat.unread_count(db, conv, member) == 2
