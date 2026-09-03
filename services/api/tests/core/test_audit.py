"""QA-AUD — audit log: che dữ liệu nhạy cảm, suy ra tài nguyên, ghi qua middleware.

Ánh xạ PRD: PRD-OPS-01 (mọi thao tác nội bộ để lại dấu vết), PRD-SEC-04 (không lộ PII).
"""

import pytest
from sqlalchemy import select

from app.domains.audit import service as audit_service
from app.domains.audit.models import AuditLog

pytestmark = [pytest.mark.security, pytest.mark.prd]


@pytest.mark.unit
@pytest.mark.parametrize(
    "field",
    ["password", "otp", "access_token", "refresh_token", "national_id", "qr_token", "cvv"],
)
def test_che_moi_truong_nhay_cam(field):
    """QA-AUD-01: không trường nhạy cảm nào được ghi nguyên văn."""
    out = audit_service.redact({field: "gia-tri-that", "phone": "0901000001"})
    assert out[field] == audit_service.REDACTED
    assert out["phone"] == "0901000001", "Trường không nhạy cảm phải giữ nguyên để còn tra cứu"


@pytest.mark.unit
def test_che_ca_truong_long_nhau():
    """QA-AUD-02: OTP nằm sâu trong payload lồng nhau vẫn phải bị che."""
    out = audit_service.redact({"user": {"profile": {"otp": "123456", "name": "An"}}})
    assert out["user"]["profile"]["otp"] == audit_service.REDACTED
    assert out["user"]["profile"]["name"] == "An"


@pytest.mark.unit
def test_che_khong_treo_voi_payload_long_sau():
    """QA-AUD-03: payload lồng 50 tầng không được làm treo tiến trình."""
    payload: dict = {"otp": "1"}
    for _ in range(50):
        payload = {"nested": payload}
    assert audit_service.redact(payload) is not None


@pytest.mark.unit
def test_cat_bot_chuoi_qua_dai():
    out = audit_service.redact({"note": "x" * 900})
    assert len(out["note"]) < 900


@pytest.mark.unit
@pytest.mark.parametrize(
    "path,expected",
    [
        ("/api/v1/trips/8b1f0c9e-1111-2222-3333-444455556666/complete", "trip"),
        ("/api/v1/drivers/8b1f0c9e-1111-2222-3333-444455556666/wallet/withdraw", "driver"),
        ("/api/v1/auth/verify-otp", None),
        ("/health", None),
    ],
)
def test_suy_ra_loai_tai_nguyen(path, expected):
    """QA-AUD-04: để tra được 'chuyến X đã bị ai đụng vào'."""
    assert audit_service.resolve_resource(path)[0] == expected


@pytest.mark.integration
async def test_ghi_duoc_ban_ghi_audit(db):
    """QA-AUD-05: bản ghi xuống DB đúng và payload đã được che."""
    await audit_service.record(
        db,
        action="POST /api/v1/trips",
        method="POST",
        path="/api/v1/trips",
        status_code=201,
        payload={"otp": "999999", "pickup_address": "12 Nguyễn Huệ"},
        ip_address="1.2.3.4",
        request_id="req-abc",
    )
    await db.commit()

    row = (await db.execute(select(AuditLog))).scalar_one()
    assert row.status_code == 201
    assert row.payload["otp"] == audit_service.REDACTED
    assert row.payload["pickup_address"] == "12 Nguyễn Huệ"
    assert row.request_id == "req-abc"


@pytest.mark.integration
async def test_payload_qua_lon_bi_cat(db):
    """QA-AUD-06: một request khổng lồ không được làm phình bảng audit."""
    await audit_service.record(
        db,
        action="POST /api/v1/trips",
        method="POST",
        path="/api/v1/trips",
        status_code=200,
        payload={"blob": ["x" * 400 for _ in range(50)]},
    )
    await db.commit()
    row = (await db.execute(select(AuditLog))).scalar_one()
    assert row.payload.get("_truncated") is True


@pytest.mark.api
async def test_middleware_tu_ghi_audit_cho_request_ghi(api_client, db):
    """QA-AUD-07: lập trình viên không cần nhớ gọi audit — middleware lo.

    Gửi một POST bất kỳ (kể cả POST hỏng) và kiểm tra đã có bản ghi. OTP trong body
    phải bị che.
    """
    await api_client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": "0901000001", "otp": "123456", "role": "rider", "full_name": "An"},
    )

    rows = (await db.execute(select(AuditLog))).scalars().all()
    assert rows, "Phải có ít nhất một bản ghi audit"
    entry = rows[-1]
    assert entry.method == "POST"
    assert entry.path == "/api/v1/auth/verify-otp"
    assert entry.payload["otp"] == audit_service.REDACTED
    assert entry.payload["phone"] == "0901000001"
    assert entry.request_id, "Phải gắn được request_id để tra cứu"


@pytest.mark.api
async def test_khong_audit_request_doc(api_client, db):
    """QA-AUD-08: GET không ghi audit — nếu ghi thì bảng sẽ phình vô ích."""
    await api_client.get("/health")
    rows = (await db.execute(select(AuditLog))).scalars().all()
    assert rows == []


@pytest.mark.api
async def test_khong_audit_gui_otp(api_client, db):
    """QA-AUD-09: gửi OTP bị loại trừ có chủ đích (quá ồn, không đổi dữ liệu nghiệp vụ)."""
    await api_client.post("/api/v1/auth/request-otp", json={"phone": "0901000001"})
    rows = (await db.execute(select(AuditLog))).scalars().all()
    assert rows == []
