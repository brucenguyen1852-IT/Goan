"""Che PII mặc định và xem đầy đủ phải nêu lý do (PRD-SEC-19, PRD-SEC-20).

Vì sao đây là nhóm test `security`: rò rỉ danh sách khách hàng ở Việt Nam không cần hacker —
chỉ cần một tài khoản CSKH và một màn hình hiện số điện thoại đầy đủ. Che mặc định làm việc
lấy dữ liệu hàng loạt trở nên chậm và để lại dấu vết; đó mới là thứ ngăn được, không phải
tường lửa.
"""

import pytest
from sqlalchemy import select

from app.core.pii import mask_email, mask_name, mask_phone
from app.core.security import encrypt_national_id
from app.domains.audit.models import AuditLog
from tests.conftest import create_rider
from tests.domains.test_iam import staff_headers

LY_DO = "Khách gọi tổng đài báo mất đồ trên xe, cần gọi lại xác minh"


@pytest.mark.unit
def test_che_so_dien_thoai_giu_dau_so_va_3_so_cuoi():
    """Giữ đủ để CSKH đối chiếu khi khách đọc số lên, không đủ để chép ra ngoài."""
    assert mask_phone("0912345678") == "0912***678"
    assert mask_phone("") is None
    assert mask_phone("0912") == "****"


@pytest.mark.unit
def test_che_email_va_ten():
    assert mask_email("nguyenvana@goan.vn") == "ngu***@goan.vn"
    assert mask_email("khong-phai-email") is None
    assert mask_name("Nguyễn Văn An") == "Nguyễn *** An"
    assert mask_name("Lê Bình") == "Lê Bình"


@pytest.mark.security
@pytest.mark.api
async def test_console_doc_ho_so_thi_thay_du_lieu_da_che(db, api_client):
    headers = await staff_headers(db, api_client, roles=["dispatcher"])
    rider = await create_rider(db, phone="0912345678")
    rider.national_id_number = encrypt_national_id("079123456789")
    await db.commit()

    body = (await api_client.get(f"/api/v1/ops/users/{rider.id}", headers=headers)).json()

    assert body["phone_masked"] == "0912***678"
    assert body["national_id_masked"] == "********6789"
    assert "0912345678" not in str(body)
    assert "079123456789" not in str(body)


@pytest.mark.security
@pytest.mark.api
async def test_khong_co_quyen_pii_thi_khong_xem_day_du_duoc(db, api_client):
    """Điều phối viên thấy được chuyến của khách, nhưng không được thấy số điện thoại thật."""
    headers = await staff_headers(db, api_client, roles=["dispatcher"])
    rider = await create_rider(db, phone="0912345678")

    response = await api_client.post(
        f"/api/v1/ops/users/{rider.id}/reveal-pii", headers=headers, json={"reason": LY_DO}
    )

    assert response.status_code == 403
    assert response.json()["error"]["details"]["required_permission"] == "pii:full:read"


@pytest.mark.security
@pytest.mark.api
async def test_xem_day_du_khong_nhap_ly_do_thi_bi_tu_choi(db, api_client):
    headers = await staff_headers(db, api_client, roles=["cs_lead"])
    rider = await create_rider(db, phone="0912345678")

    thieu_ly_do = await api_client.post(
        f"/api/v1/ops/users/{rider.id}/reveal-pii", headers=headers, json={}
    )
    ly_do_qua_ngan = await api_client.post(
        f"/api/v1/ops/users/{rider.id}/reveal-pii", headers=headers, json={"reason": "xem"}
    )

    assert thieu_ly_do.status_code == 422
    assert ly_do_qua_ngan.status_code == 422


@pytest.mark.security
@pytest.mark.api
async def test_moi_lan_xem_day_du_deu_ghi_log_kem_ly_do(db, api_client):
    """DoD của P1-06. Không có lý do trong log thì không phân biệt được tra cứu hợp lệ với
    hành vi lấy dữ liệu mang ra ngoài — cả hai để lại đúng một dòng giống hệt nhau."""
    headers = await staff_headers(db, api_client, roles=["cs_lead"])
    rider = await create_rider(db, phone="0912345678")
    rider.national_id_number = encrypt_national_id("079123456789")
    await db.commit()

    response = await api_client.post(
        f"/api/v1/ops/users/{rider.id}/reveal-pii", headers=headers, json={"reason": LY_DO}
    )

    assert response.status_code == 200
    assert response.json()["phone"] == "0912345678"
    assert response.json()["national_id_number"] == "079123456789"

    rows = (
        (await db.execute(select(AuditLog).where(AuditLog.path.like("%reveal-pii"))))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].reason == LY_DO
    assert rows[0].actor_staff_id is not None
    # Bản thân dòng log không được chứa PII: payload đã bị che ở audit/service.redact.
    assert "0912345678" not in str(rows[0].payload)
