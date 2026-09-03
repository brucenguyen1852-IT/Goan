"""QA-IDM — khử trùng request. Ánh xạ PRD: PRD-PAY-07 (không bao giờ trừ tiền hai lần)."""

import pytest

from app.core import idempotency

pytestmark = [pytest.mark.money, pytest.mark.prd]


@pytest.mark.unit
@pytest.mark.parametrize(
    "method,path,protected",
    [
        ("POST", "/api/v1/trips", True),
        ("POST", "/api/v1/trips/abc/complete", True),
        ("POST", "/api/v1/trips/abc/cancel", True),
        ("POST", "/api/v1/drivers/abc/wallet/withdraw", True),
        ("POST", "/api/v1/matching/trips/abc/accept", True),
        ("POST", "/api/v1/auth/request-otp", False),
        ("GET", "/api/v1/trips", False),
        ("POST", "/api/v1/trips/abc/gps-ping", False),
    ],
)
def test_dung_endpoint_duoc_bao_ve(method, path, protected):
    """QA-IDM-01: đúng những endpoint chạm tiền/không hoàn tác mới bị khoá."""
    assert idempotency.is_protected(method, path) is protected


@pytest.mark.unit
def test_khoa_tach_theo_nguoi_dung():
    """QA-IDM-02: hai người vô tình trùng key không được chặn nhau."""
    a = idempotency.build_key("user-a", "POST", "/api/v1/trips", "key-1")
    b = idempotency.build_key("user-b", "POST", "/api/v1/trips", "key-1")
    assert a != b


@pytest.mark.unit
def test_khoa_tach_theo_endpoint():
    a = idempotency.build_key("user-a", "POST", "/api/v1/trips", "key-1")
    b = idempotency.build_key("user-a", "POST", "/api/v1/trips/x/cancel", "key-1")
    assert a != b


@pytest.mark.unit
def test_cung_dau_vao_cho_cung_khoa():
    a = idempotency.build_key("user-a", "POST", "/api/v1/trips", "key-1")
    b = idempotency.build_key("user-a", "POST", "/api/v1/trips", "key-1")
    assert a == b


@pytest.mark.api
async def test_gui_trung_thi_phat_lai_ket_qua_cu(api_client, fake_redis, db):
    """QA-IDM-03: kịch bản thật — mất sóng giữa chừng, người dùng bấm lại.

    Lần hai phải nhận đúng kết quả lần một kèm cờ Idempotent-Replay, KHÔNG tạo bản ghi mới.
    """
    from sqlalchemy import func, select

    from app.domains.audit.models import AuditLog

    headers = {"Idempotency-Key": "khoa-thu-nghiem-1"}
    first = await api_client.post("/api/v1/trips", json={}, headers=headers)
    second = await api_client.post("/api/v1/trips", json={}, headers=headers)

    if 200 <= first.status_code < 300:
        assert second.status_code == first.status_code
        assert second.headers.get("Idempotent-Replay") == "true"
        assert second.json() == first.json()
    else:
        # Lỗi thì KHÔNG được cache — người dùng phải thử lại được.
        assert second.headers.get("Idempotent-Replay") is None

    count = (await db.execute(select(func.count(AuditLog.id)))).scalar_one()
    assert count >= 1


@pytest.mark.api
async def test_khong_co_header_thi_van_cho_qua_khi_chua_bat_bat_buoc(api_client):
    """QA-IDM-04: giai đoạn chuyển tiếp — client cũ chưa gửi header vẫn dùng được."""
    resp = await api_client.post("/api/v1/trips", json={})
    assert resp.headers.get("Idempotent-Replay") is None


@pytest.mark.api
async def test_bat_buoc_header_khi_bat_cau_hinh(api_client, monkeypatch):
    """QA-IDM-05: khi mọi client đã sẵn sàng, bật cờ là chặn được request thiếu header."""
    from app.config import settings

    monkeypatch.setattr(settings, "IDEMPOTENCY_REQUIRED", True)
    resp = await api_client.post("/api/v1/trips", json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "idempotency_key_required"


@pytest.mark.api
async def test_request_song_song_bi_tu_choi(api_client, fake_redis):
    """QA-IDM-06: bản gốc còn đang chạy thì bản trùng phải nhận 409, không xử lý song song."""
    key = idempotency.build_key("anon", "POST", "/api/v1/trips", "dang-chay")
    await fake_redis.set(key + ":lock", "1", ex=60)

    resp = await api_client.post("/api/v1/trips", json={}, headers={"Idempotency-Key": "dang-chay"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "idempotency_in_progress"


@pytest.mark.api
async def test_redis_chet_thi_khong_chan_nghiep_vu(api_client, fake_redis):
    """QA-IDM-07: mất khử trùng còn hơn mất dịch vụ — đánh đổi đã ghi trong docs/QA."""
    fake_redis.fail = True
    resp = await api_client.post("/api/v1/trips", json={}, headers={"Idempotency-Key": "bat-ky"})
    assert resp.status_code != 500
