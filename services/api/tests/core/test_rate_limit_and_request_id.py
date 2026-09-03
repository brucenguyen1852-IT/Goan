"""QA-RL / QA-OBS — chống lạm dụng và khả năng truy vết.

Ánh xạ PRD: PRD-SEC-03 (chặn spam OTP vì mỗi tin là chi phí thật), PRD-OPS-02 (truy vết sự cố).
"""

import pytest

from app.core import middleware as rate_mw
from app.core.observability import REQUEST_ID_HEADER

pytestmark = [pytest.mark.security, pytest.mark.prd]


@pytest.mark.unit
@pytest.mark.parametrize(
    "path,limit,window",
    [
        ("/api/v1/auth/request-otp", 60, 300),
        ("/api/v1/auth/verify-otp", 60, 300),
        ("/api/v1/trips", 20, 60),
    ],
)
def test_endpoint_nhay_cam_co_han_muc_rieng(path, limit, window):
    """QA-RL-01: các endpoint nhạy cảm không dùng chung hạn mức mặc định 120/phút.

    Hạn mức theo IP ở đây cố ý ĐỂ RỘNG: nhà mạng di động Việt Nam NAT hàng nghìn thuê bao
    vào vài IP công cộng, chặn chặt theo IP là chặn nhầm người dùng thật. Hạn mức chặt gắn
    với chi phí SMS nằm ở tầng nghiệp vụ, tính theo số điện thoại — xem QA-AUTH-13.
    """
    bucket, got_limit, got_window = rate_mw._resolve_rule(path)
    assert (got_limit, got_window) == (limit, window)
    assert bucket != "default"


@pytest.mark.unit
def test_endpoint_thuong_dung_han_muc_mac_dinh():
    bucket, limit, window = rate_mw._resolve_rule("/api/v1/users/me")
    assert bucket == "default"
    assert window == 60


@pytest.mark.api
async def test_chan_khi_vuot_han_muc_otp_cua_mot_so(api_client):
    """QA-RL-02: gửi OTP quá nhiều cho CÙNG MỘT SỐ phải bị chặn.

    Bài test bảo vệ tiền thật: mỗi tin SMS là chi phí, và kẻ xấu có thể vừa đốt ngân sách
    vừa quấy rối chủ số bằng cách gọi liên tục.
    """
    from app.config import settings

    payload = {"phone": "0901000001"}
    codes = []
    for _ in range(settings.OTP_MAX_PER_PHONE_WINDOW + 2):
        resp = await api_client.post("/api/v1/auth/request-otp", json=payload)
        codes.append(resp.status_code)

    assert 429 in codes, f"Phải có request bị chặn, nhận được: {codes}"
    assert codes.index(429) == settings.OTP_MAX_PER_PHONE_WINDOW, (
        f"Phải chặn đúng sau {settings.OTP_MAX_PER_PHONE_WINDOW} lượt, nhận được: {codes}"
    )


@pytest.mark.api
async def test_han_muc_mot_so_khong_anh_huong_so_khac(api_client):
    """QA-RL-05: hai người dùng khác nhau không được chặn lẫn nhau.

    Đây chính là điều hạn mức theo IP làm sai: cả quán cà phê dùng chung một IP.
    """
    from app.config import settings

    for _ in range(settings.OTP_MAX_PER_PHONE_WINDOW + 1):
        await api_client.post("/api/v1/auth/request-otp", json={"phone": "0901000001"})

    resp = await api_client.post("/api/v1/auth/request-otp", json={"phone": "0902000002"})
    assert resp.status_code == 200


@pytest.mark.api
async def test_tra_ve_header_han_muc_con_lai(api_client):
    """QA-RL-03: client biết còn bao nhiêu lượt để tự điều tiết thay vì đâm vào tường."""
    resp = await api_client.get("/api/v1/users/me")
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers


@pytest.mark.api
async def test_khong_gioi_han_endpoint_suc_khoe(api_client):
    """QA-RL-04: probe của load balancer gọi liên tục, không được tính hạn mức."""
    for _ in range(30):
        resp = await api_client.get("/health")
        assert resp.status_code == 200


@pytest.mark.api
async def test_moi_request_co_ma_truy_vet(api_client):
    """QA-OBS-01: khách báo lỗi thì chỉ cần một mã là tra ra toàn bộ dấu vết."""
    resp = await api_client.get("/health")
    assert resp.headers.get(REQUEST_ID_HEADER)


@pytest.mark.api
async def test_giu_ma_truy_vet_do_client_gui_len(api_client):
    """QA-OBS-02: app mobile gửi mã của nó lên thì server dùng lại, để nối được hai đầu log."""
    resp = await api_client.get("/health", headers={REQUEST_ID_HEADER: "ma-tu-app-mobile"})
    assert resp.headers[REQUEST_ID_HEADER] == "ma-tu-app-mobile"


@pytest.mark.api
async def test_cat_ma_truy_vet_qua_dai(api_client):
    """QA-OBS-03: không tin dữ liệu client — mã dài 10.000 ký tự không được vào log."""
    resp = await api_client.get("/health", headers={REQUEST_ID_HEADER: "x" * 10_000})
    assert len(resp.headers[REQUEST_ID_HEADER]) <= 64


@pytest.mark.api
async def test_health_khong_cham_db(api_client):
    """QA-OBS-04: liveness phải trả lời được ngay cả khi DB chết.

    Nếu /health phụ thuộc DB thì một sự cố DB sẽ khiến orchestrator restart container
    hàng loạt — làm sự cố nặng thêm thay vì nhẹ đi.
    """
    resp = await api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "database" not in resp.json()
