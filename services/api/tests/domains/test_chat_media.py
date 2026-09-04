"""Ảnh đính kèm, push khi offline, ẩn danh hoá quá hạn (P2-12, P2-13, P2-20).

Ba thứ ở đây có chung một đặc điểm: chúng đụng tới dữ liệu cá nhân sau khi cuộc trò chuyện
đã kết thúc, tức là lúc không còn ai theo dõi.

  1. Ảnh chat gồm ảnh hiện trường tai nạn, biên lai, giấy tờ. URL cố định = kho ảnh mở.
  2. Push hiện trên màn hình khoá, người ngồi cạnh cũng đọc được.
  3. Giữ nội dung chat vĩnh viễn là giữ một kho dữ liệu cá nhân không ai còn lý do để giữ.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.constants import TripStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import create_access_token
from app.domains.chat import service
from app.domains.chat.constants import ConversationKind, MessageKind
from app.domains.chat.models import Conversation, ConversationMember, Message, MessageAttachment
from app.domains.notifications import service as notifications
from app.domains.notifications.constants import DevicePlatform
from app.domains.notifications.models import PushToken
from app.integrations.push import MockPushProvider, set_push
from tests.conftest import create_driver, create_rider, create_trip


async def _trip_chat(db, *, rider_phone="0901000091", driver_phone="0902000091"):
    rider = await create_rider(db, phone=rider_phone)
    driver_user, _ = await create_driver(db, phone=driver_phone)
    trip = await create_trip(db, rider, driver_user, status=TripStatus.DRIVER_ARRIVING)
    conversation = await service.get_or_create_trip_conversation(
        db, trip_id=trip.id, rider_id=rider.id, driver_id=driver_user.id
    )
    return rider, driver_user, conversation


@pytest.fixture
def push_gia():
    """Bản push giả, thay lại sau mỗi test để không rò trạng thái sang bài kế tiếp."""
    from app.integrations import push as push_module

    cu = push_module.get_push()
    gia = MockPushProvider()
    set_push(gia)
    yield gia
    set_push(cu)


# --- Ảnh đính kèm (P2-12) -------------------------------------------------------------


@pytest.mark.integration
async def test_xin_url_tai_len_tra_ve_link_co_han(db):
    """QA-MEDIA-01. Không có URL cố định: link rò ra thì cũng chỉ rò trong 15 phút."""
    rider, _, conversation = await _trip_chat(db)

    attachment, presigned = await service.create_upload(
        db, conversation, content_type="image/jpeg", size_bytes=200_000, uploader_user=rider
    )

    assert attachment.message_id is None  # chưa gắn vào tin nào
    assert attachment.storage_key in presigned.upload_url
    assert "X-Signature=" in presigned.upload_url
    assert presigned.expires_at > datetime.now(timezone.utc)
    assert presigned.expires_at < datetime.now(timezone.utc) + timedelta(hours=1)


@pytest.mark.integration
@pytest.mark.parametrize(
    "content_type,size",
    [
        ("video/mp4", 100),  # không phải ảnh
        ("application/pdf", 100),
        ("image/jpeg", 6 * 1024 * 1024),  # quá 5MB
        ("image/jpeg", 0),
    ],
)
async def test_tu_choi_ngay_luc_xin_url_chu_khong_doi_tai_xong(db, content_type, size):
    """QA-MEDIA-02. Từ chối sau khi người dùng ngồi chờ tải xong 20MB qua 4G là cách làm
    hỏng trải nghiệm một cách hoàn toàn tránh được."""
    rider, _, conversation = await _trip_chat(db)

    with pytest.raises(ConflictError):
        await service.create_upload(
            db, conversation, content_type=content_type, size_bytes=size, uploader_user=rider
        )


@pytest.mark.integration
async def test_khoa_luu_tru_do_server_sinh_va_khong_trung_nhau(db):
    """Cho client đặt tên khoá là cho phép ghi đè tệp của người khác bằng cách đoán tên."""
    rider, _, conversation = await _trip_chat(db)

    a, _ = await service.create_upload(
        db, conversation, content_type="image/jpeg", size_bytes=1000, uploader_user=rider
    )
    b, _ = await service.create_upload(
        db, conversation, content_type="image/jpeg", size_bytes=1000, uploader_user=rider
    )

    assert a.storage_key != b.storage_key
    assert str(conversation.id) in a.storage_key


@pytest.mark.integration
async def test_gan_anh_vao_tin_nhan_thi_tin_thanh_loai_image(db):
    """QA-MEDIA-03."""
    rider, _, conversation = await _trip_chat(db)
    attachment, _ = await service.create_upload(
        db, conversation, content_type="image/png", size_bytes=1000, uploader_user=rider
    )

    lay = await service.claim_attachment(db, conversation, attachment.id, uploader_user=rider)
    tin, moi = await service.send_message(
        db,
        conversation,
        body="Ảnh hiện trường",
        sender_user=rider,
        kind=MessageKind.IMAGE,
        attachment=lay,
    )

    assert moi is True and tin.kind is MessageKind.IMAGE
    await db.refresh(attachment)
    assert attachment.message_id == tin.id
    await db.refresh(tin, ["attachments"])
    assert tin.attachment_id == attachment.id


@pytest.mark.security
@pytest.mark.integration
async def test_khong_gan_duoc_anh_cua_nguoi_khac_vao_tin_cua_minh(db):
    """QA-MEDIA-04. Thiếu bước này thì ai cũng gắn được ảnh của người khác vào tin của mình."""
    rider, driver_user, conversation = await _trip_chat(db)
    cua_tai_xe, _ = await service.create_upload(
        db, conversation, content_type="image/jpeg", size_bytes=1000, uploader_user=driver_user
    )

    with pytest.raises(PermissionDeniedError):
        await service.claim_attachment(db, conversation, cua_tai_xe.id, uploader_user=rider)


@pytest.mark.security
@pytest.mark.integration
async def test_khong_keo_duoc_anh_tu_hoi_thoai_khac_sang(db):
    """Ảnh thuộc về một hội thoại. Kéo sang hội thoại khác là đưa bằng chứng ra khỏi ngữ cảnh."""
    rider, _, conversation = await _trip_chat(db)
    khac = Conversation(kind=ConversationKind.SUPPORT, subject="Hỗ trợ")
    db.add(khac)
    await db.flush()
    db.add(ConversationMember(conversation_id=khac.id, user_id=rider.id, role="rider"))
    await db.commit()
    await db.refresh(khac)
    attachment, _ = await service.create_upload(
        db, khac, content_type="image/jpeg", size_bytes=1000, uploader_user=rider
    )

    with pytest.raises(NotFoundError):
        await service.claim_attachment(db, conversation, attachment.id, uploader_user=rider)


@pytest.mark.integration
async def test_mot_anh_chi_gui_duoc_mot_lan(db):
    """Dùng lại một ảnh cho nhiều tin là đường né kiểm duyệt: quét một lần, gửi nhiều nơi."""
    rider, _, conversation = await _trip_chat(db)
    attachment, _ = await service.create_upload(
        db, conversation, content_type="image/jpeg", size_bytes=1000, uploader_user=rider
    )
    lay = await service.claim_attachment(db, conversation, attachment.id, uploader_user=rider)
    await service.send_message(
        db, conversation, body="Ảnh", sender_user=rider, kind=MessageKind.IMAGE, attachment=lay
    )

    with pytest.raises(ConflictError):
        await service.claim_attachment(db, conversation, attachment.id, uploader_user=rider)


@pytest.mark.security
@pytest.mark.integration
async def test_nguoi_ngoai_khong_lay_duoc_url_doc_anh(db):
    """QA-MEDIA-05. Ảnh chat gồm ảnh giấy tờ; ràng buộc thành viên phải giống hệt đọc tin."""
    rider, _, conversation = await _trip_chat(db)
    attachment, _ = await service.create_upload(
        db, conversation, content_type="image/jpeg", size_bytes=1000, uploader_user=rider
    )
    nguoi_la = await create_rider(db, phone="0901000092")

    assert await service.get_attachment_for_member(db, attachment.id, user=rider)
    with pytest.raises(PermissionDeniedError):
        await service.get_attachment_for_member(db, attachment.id, user=nguoi_la)


@pytest.mark.security
@pytest.mark.integration
async def test_anh_khong_ton_tai_bao_cung_mot_loi_voi_anh_cua_nguoi_khac(db):
    """Trả lỗi khác nhau là cho người dò biết mã nào có thật."""
    rider, _, _ = await _trip_chat(db)

    with pytest.raises(PermissionDeniedError):
        await service.get_attachment_for_member(db, uuid.uuid4(), user=rider)


@pytest.mark.integration
async def test_don_anh_xin_url_roi_bo_ngang(db):
    """QA-MEDIA-06. Người dùng chọn ảnh rồi đổi ý là chuyện thường; không dọn thì kho phình
    ra vì những tệp không ai từng nhìn thấy — mà vẫn là dữ liệu cá nhân đang được giữ."""
    rider, _, conversation = await _trip_chat(db)
    bo_ngang, _ = await service.create_upload(
        db, conversation, content_type="image/jpeg", size_bytes=1000, uploader_user=rider
    )
    da_gui, _ = await service.create_upload(
        db, conversation, content_type="image/jpeg", size_bytes=1000, uploader_user=rider
    )
    lay = await service.claim_attachment(db, conversation, da_gui.id, uploader_user=rider)
    await service.send_message(
        db, conversation, body="Ảnh", sender_user=rider, kind=MessageKind.IMAGE, attachment=lay
    )

    sau = datetime.now(timezone.utc) + timedelta(hours=30)
    assert await service.purge_orphan_attachments(db, now=sau) == 1

    con_lai = (await db.execute(select(MessageAttachment))).scalars().all()
    assert [a.id for a in con_lai] == [da_gui.id]
    assert bo_ngang.id not in [a.id for a in con_lai]


@pytest.mark.api
async def test_luong_gui_anh_qua_http(db, api_client):
    """QA-MEDIA-07. Trọn vòng: xin URL → gửi tin kèm ảnh → lấy URL đọc."""
    rider, _, conversation = await _trip_chat(
        db, rider_phone="0901000093", driver_phone="0902000093"
    )
    headers = {
        "Authorization": f"Bearer {create_access_token(str(rider.id), UserRole.RIDER.value)}"
    }

    xin = await api_client.post(
        "/api/v1/chat/attachments",
        headers=headers,
        json={
            "conversation_id": str(conversation.id),
            "content_type": "image/jpeg",
            "size_bytes": 150_000,
        },
    )
    assert xin.status_code == 201, xin.text
    attachment_id = xin.json()["attachment_id"]

    gui = await api_client.post(
        f"/api/v1/chat/conversations/{conversation.id}/messages",
        headers=headers,
        json={"body": "Ảnh hiện trường", "attachment_id": attachment_id},
    )
    assert gui.status_code == 201, gui.text
    assert gui.json()["kind"] == "image"

    doc = await api_client.get(f"/api/v1/chat/attachments/{attachment_id}", headers=headers)
    assert doc.status_code == 200
    assert doc.json()["download_url"].startswith("https://")


@pytest.mark.api
async def test_xin_url_qua_5mb_bi_tu_choi_qua_http(db, api_client):
    rider, _, conversation = await _trip_chat(
        db, rider_phone="0901000094", driver_phone="0902000094"
    )
    headers = {
        "Authorization": f"Bearer {create_access_token(str(rider.id), UserRole.RIDER.value)}"
    }

    tra_loi = await api_client.post(
        "/api/v1/chat/attachments",
        headers=headers,
        json={
            "conversation_id": str(conversation.id),
            "content_type": "image/jpeg",
            "size_bytes": 6 * 1024 * 1024,
        },
    )

    assert tra_loi.status_code == 409
    assert "5MB" in tra_loi.json()["error"]["message"]


# --- Push khi offline (P2-13) ---------------------------------------------------------


@pytest.mark.integration
async def test_dang_ky_lai_cung_token_khong_tao_dong_thu_hai(db):
    """QA-MEDIA-08. App gọi đăng ký mỗi lần mở; mỗi lần một dòng thì gửi push n lần cho
    cùng một máy."""
    rider = await create_rider(db, phone="0901000095")

    await notifications.register_push_token(
        db, rider, token="fcm-abc", platform=DevicePlatform.ANDROID
    )
    await notifications.register_push_token(
        db, rider, token="fcm-abc", platform=DevicePlatform.ANDROID
    )

    assert len((await db.execute(select(PushToken))).scalars().all()) == 1


@pytest.mark.security
@pytest.mark.integration
async def test_token_doi_chu_khi_may_do_dang_nhap_tai_khoan_khac(db):
    """QA-MEDIA-09. Không đổi chủ theo là gửi tin nhắn của người này tới màn hình khoá của
    người kia — trên đúng cái máy vừa đổi tay."""
    a = await create_rider(db, phone="0901000096")
    b = await create_rider(db, phone="0901000097")

    await notifications.register_push_token(db, a, token="fcm-may", platform=DevicePlatform.IOS)
    await notifications.register_push_token(db, b, token="fcm-may", platform=DevicePlatform.IOS)

    rows = (await db.execute(select(PushToken))).scalars().all()
    assert len(rows) == 1 and rows[0].user_id == b.id


@pytest.mark.integration
async def test_go_token_cua_mot_may_khong_dung_toi_may_khac(db):
    rider = await create_rider(db, phone="0901000098")
    await notifications.register_push_token(db, rider, token="may-1", platform=DevicePlatform.IOS)
    await notifications.register_push_token(
        db, rider, token="may-2", platform=DevicePlatform.ANDROID
    )

    await notifications.revoke_push_token(db, "may-1")

    con_lai = await notifications.active_tokens(db, rider.id)
    assert [t.token for t in con_lai] == ["may-2"]


@pytest.mark.integration
async def test_token_chet_bi_go_ngay_sau_lan_gui_that_bai(db, push_gia):
    """QA-MEDIA-10. Giữ token chết nghĩa là mỗi tin nhắn về sau tốn thêm một lời gọi mạng
    chắc chắn thất bại, nhân với số người dùng đã cài lại app."""
    rider = await create_rider(db, phone="0901000099")
    await notifications.register_push_token(
        db, rider, token="invalid-cu", platform=DevicePlatform.IOS
    )
    await notifications.register_push_token(db, rider, token="fcm-moi", platform=DevicePlatform.IOS)

    gui = await notifications.send_push(db, rider.id, title="GoAn", body="Tin mới")

    assert gui == 1
    assert [t.token for t in await notifications.active_tokens(db, rider.id)] == ["fcm-moi"]


@pytest.mark.integration
async def test_chua_doc_thi_nhan_push(db, push_gia):
    """QA-MEDIA-11. DoD của P2-13."""
    rider, driver_user, conversation = await _trip_chat(db)
    await notifications.register_push_token(
        db, driver_user, token="fcm-tx", platform=DevicePlatform.ANDROID
    )
    tin, _ = await service.send_message(db, conversation, body="Anh ơi", sender_user=rider)

    assert await service.deliver_offline_push(db, tin.id, driver_user.id) == 1
    assert len(push_gia.sent) == 1


@pytest.mark.security
@pytest.mark.integration
async def test_noi_dung_tin_khong_di_vao_payload_push(db, push_gia):
    """QA-MEDIA-12. Thông báo hiện trên màn hình khoá — người ngồi cạnh cũng đọc được."""
    rider, driver_user, conversation = await _trip_chat(db)
    await notifications.register_push_token(
        db, driver_user, token="fcm-tx", platform=DevicePlatform.ANDROID
    )
    bi_mat = "Số tài khoản của em là 0123456789 nhé"
    tin, _ = await service.send_message(db, conversation, body=bi_mat, sender_user=rider)

    await service.deliver_offline_push(db, tin.id, driver_user.id)

    da_gui = push_gia.sent[0]
    assert bi_mat not in da_gui["body"] and bi_mat not in str(da_gui["data"])
    assert da_gui["data"]["conversation_id"] == str(conversation.id)


@pytest.mark.integration
async def test_da_doc_roi_thi_khong_push_nua(db, push_gia):
    """QA-MEDIA-13. Bắn thông báo cho tin người ta vừa đọc xong là cách làm người dùng tắt
    thông báo của ứng dụng — sau đó thì không còn kênh nào tới được họ nữa."""
    rider, driver_user, conversation = await _trip_chat(db)
    await notifications.register_push_token(
        db, driver_user, token="fcm-tx", platform=DevicePlatform.ANDROID
    )
    tin, _ = await service.send_message(db, conversation, body="Anh ơi", sender_user=rider)
    member = service.active_member(conversation, user=driver_user)
    await service.mark_read(db, conversation, member, tin.id)

    assert await service.deliver_offline_push(db, tin.id, driver_user.id) == 0
    assert push_gia.sent == []


@pytest.mark.integration
async def test_khong_co_thiet_bi_nao_thi_bo_qua_yen_lang(db, push_gia):
    """Người dùng chưa cho phép thông báo là chuyện bình thường, không phải lỗi."""
    rider, driver_user, conversation = await _trip_chat(db)
    tin, _ = await service.send_message(db, conversation, body="Anh ơi", sender_user=rider)

    assert await service.deliver_offline_push(db, tin.id, driver_user.id) == 0


@pytest.mark.integration
async def test_nguoi_da_roi_hoi_thoai_khong_nhan_push(db, push_gia):
    """CSKH rời đi rồi vẫn nhận thông báo là rò rỉ kéo dài sau khi đã hết quyền."""
    rider, driver_user, conversation = await _trip_chat(db)
    await notifications.register_push_token(
        db, driver_user, token="fcm-tx", platform=DevicePlatform.ANDROID
    )
    member = service.active_member(conversation, user=driver_user)
    member.left_at = datetime.now(timezone.utc)
    await db.commit()
    tin, _ = await service.send_message(db, conversation, body="Anh ơi", sender_user=rider)

    assert await service.deliver_offline_push(db, tin.id, driver_user.id) == 0


# --- Ẩn danh hoá quá hạn lưu trữ (P2-20) ----------------------------------------------


@pytest.mark.integration
async def test_chat_chuyen_qua_12_thang_bi_an_danh_hoa(db):
    """QA-MEDIA-14. DoD của P2-20."""
    rider, _, conversation = await _trip_chat(db)
    tin, _ = await service.send_message(
        db, conversation, body="Số nhà 12 ngõ 5 anh nhé", sender_user=rider
    )

    sau_13_thang = datetime.now(timezone.utc) + timedelta(days=400)
    assert await service.anonymize_expired_conversations(db, now=sau_13_thang) == 1

    await db.refresh(tin)
    assert tin.body == service.ANONYMIZED_BODY
    # Dòng vẫn còn: câu hỏi "hai người này có từng nhắn tin cho nhau không" vẫn trả lời được.
    assert (await db.execute(select(Message))).scalars().all()


@pytest.mark.integration
async def test_chat_ho_tro_giu_lau_gap_doi_vi_la_bang_chung_khieu_nai(db):
    """QA-MEDIA-15. Khiếu nại đến muộn; xoá chat hỗ trợ theo cùng hạn với chat chuyến là vứt
    bằng chứng đúng lúc cần dùng."""
    rider = await create_rider(db, phone="0901000100")
    ho_tro = Conversation(kind=ConversationKind.SUPPORT, subject="Khiếu nại")
    db.add(ho_tro)
    await db.flush()
    db.add(ConversationMember(conversation_id=ho_tro.id, user_id=rider.id, role="rider"))
    await db.commit()
    await db.refresh(ho_tro)
    tin, _ = await service.send_message(
        db, ho_tro, body="Em bị trừ tiền hai lần", sender_user=rider
    )

    sau_13_thang = datetime.now(timezone.utc) + timedelta(days=400)
    assert await service.anonymize_expired_conversations(db, now=sau_13_thang) == 0
    await db.refresh(tin)
    assert tin.body == "Em bị trừ tiền hai lần"

    sau_25_thang = datetime.now(timezone.utc) + timedelta(days=760)
    assert await service.anonymize_expired_conversations(db, now=sau_25_thang) == 1


@pytest.mark.integration
async def test_chay_lai_khong_dem_lai_tin_da_an_danh_hoa(db):
    """Quét lại mỗi đêm; đếm lại dòng đã xử lý làm log báo động giả vĩnh viễn."""
    rider, _, conversation = await _trip_chat(db)
    await service.send_message(db, conversation, body="Nội dung cũ", sender_user=rider)

    sau = datetime.now(timezone.utc) + timedelta(days=400)
    assert await service.anonymize_expired_conversations(db, now=sau) == 1
    assert await service.anonymize_expired_conversations(db, now=sau) == 0


@pytest.mark.integration
async def test_tin_con_trong_han_khong_bi_dung_toi(db):
    """Cặp của test trên: một lỗi so sánh ngược dấu sẽ xoá sạch nội dung chat đang chạy."""
    rider, _, conversation = await _trip_chat(db)
    tin, _ = await service.send_message(db, conversation, body="Anh tới chưa", sender_user=rider)

    assert await service.anonymize_expired_conversations(db) == 0
    await db.refresh(tin)
    assert tin.body == "Anh tới chưa"


@pytest.mark.integration
async def test_gui_lai_anh_cung_client_msg_id_khong_bi_bao_da_gui_roi(db):
    """QA-MEDIA-16. Bài kịch bản E2E bắt được lỗi này: người dùng mất sóng lúc gửi ảnh, bấm
    gửi lại, và nhận 409 "tệp đã được gửi rồi" — đúng lúc họ đang cố gửi ảnh hiện trường."""
    rider, _, conversation = await _trip_chat(
        db, rider_phone="0901000121", driver_phone="0902000121"
    )
    attachment, _ = await service.create_upload(
        db, conversation, content_type="image/jpeg", size_bytes=1000, uploader_user=rider
    )
    lan_1 = await service.claim_attachment(
        db, conversation, attachment.id, uploader_user=rider, client_msg_id="a-1"
    )
    tin, _ = await service.send_message(
        db,
        conversation,
        body="Ảnh",
        sender_user=rider,
        client_msg_id="a-1",
        kind=MessageKind.IMAGE,
        attachment=lan_1,
    )

    lan_2 = await service.claim_attachment(
        db, conversation, attachment.id, uploader_user=rider, client_msg_id="a-1"
    )
    lai, moi = await service.send_message(
        db,
        conversation,
        body="Ảnh",
        sender_user=rider,
        client_msg_id="a-1",
        kind=MessageKind.IMAGE,
        attachment=lan_2,
    )

    assert moi is False and lai.id == tin.id
    assert len((await db.execute(select(Message))).scalars().all()) == 1

    # Nhưng client_msg_id KHÁC thì vẫn là dùng lại ảnh cho tin thứ hai — phải bị chặn.
    with pytest.raises(ConflictError):
        await service.claim_attachment(
            db, conversation, attachment.id, uploader_user=rider, client_msg_id="a-2"
        )
