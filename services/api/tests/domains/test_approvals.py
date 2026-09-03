"""Maker–checker cho thao tác chạm tiền (PRD-OPS-05).

Toàn bộ giá trị của module này nằm ở ba câu hỏi, và đây là chỗ trả lời chúng:

  - Người tạo tự duyệt được không?  → Không, kể cả super_admin.
  - Có quyền tạo thì có duyệt được không?  → Không, hai quyền tách hẳn.
  - Đề nghị treo mãi được không?  → Không, quá hạn là hết hiệu lực.

Đánh dấu `money` vì đây là cửa chặn cuối trước khi tiền rời khỏi hệ thống.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError, PermissionDeniedError
from app.domains.approvals import service
from app.domains.approvals.constants import ApprovalKind, ApprovalStatus
from app.domains.iam import service as iam_service
from tests.domains.test_iam import PASSWORD

LY_DO = "Chi ví tài xế kỳ 01-15/09 theo bảng đối soát đã ký"


async def _staff(db, email: str, roles: list[str]):
    await iam_service.sync_catalog(db)
    staff, _ = await iam_service.create_staff(
        db, email=email, full_name="Nhân Sự", password=PASSWORD, role_codes=roles
    )
    return staff


@pytest.mark.money
@pytest.mark.integration
async def test_ke_toan_tao_de_nghi_truong_phong_duyet(db):
    ke_toan = await _staff(db, "ketoan@goan.vn", ["finance_accountant"])
    truong_phong = await _staff(db, "truongphong@goan.vn", ["finance_manager"])

    request = await service.create(
        db,
        kind=ApprovalKind.PAYOUT,
        maker=ke_toan,
        reason=LY_DO,
        amount=Decimal("5000000"),
        resource_type="driver",
        resource_id="d-1",
    )
    decided = await service.approve(db, request, truong_phong, note="Khớp đối soát")

    assert decided.status is ApprovalStatus.APPROVED
    assert decided.decided_by == truong_phong.id
    assert decided.decided_at is not None


@pytest.mark.money
@pytest.mark.security
@pytest.mark.integration
async def test_nguoi_tao_khong_duoc_tu_duyet(db):
    """Ràng buộc cốt lõi. Mất nó thì cả module này chỉ là thêm hai cú bấm chuột."""
    ke_toan = await _staff(db, "ketoan2@goan.vn", ["finance_accountant"])
    request = await service.create(
        db, kind=ApprovalKind.PAYOUT, maker=ke_toan, reason=LY_DO, amount=Decimal("1000000")
    )

    with pytest.raises(PermissionDeniedError) as err:
        await service.approve(db, request, ke_toan)

    assert err.value.details["rule"] == "maker_checker"
    assert request.status is ApprovalStatus.PENDING


@pytest.mark.money
@pytest.mark.security
@pytest.mark.integration
async def test_super_admin_cung_khong_tu_duyet_de_nghi_cua_minh(db):
    """Quyền vạn năng không phá được maker-checker: đây là ràng buộc quy trình, không phải quyền."""
    admin = await _staff(db, "admin@goan.vn", ["super_admin"])
    request = await service.create(
        db, kind=ApprovalKind.PAYOUT, maker=admin, reason=LY_DO, amount=Decimal("1000000")
    )

    with pytest.raises(PermissionDeniedError):
        await service.approve(db, request, admin)


@pytest.mark.money
@pytest.mark.security
@pytest.mark.integration
async def test_co_quyen_tao_khong_co_nghia_la_duoc_duyet(db):
    ke_toan_1 = await _staff(db, "kt1@goan.vn", ["finance_accountant"])
    ke_toan_2 = await _staff(db, "kt2@goan.vn", ["finance_accountant"])
    request = await service.create(
        db, kind=ApprovalKind.PAYOUT, maker=ke_toan_1, reason=LY_DO, amount=Decimal("1000000")
    )

    with pytest.raises(PermissionDeniedError) as err:
        await service.approve(db, request, ke_toan_2)

    assert err.value.details["required_permission"] == "finance:payout:approve"


@pytest.mark.security
@pytest.mark.integration
async def test_khong_co_quyen_tao_thi_khong_tao_duoc_de_nghi(db):
    marketing = await _staff(db, "mkt@goan.vn", ["marketing"])

    with pytest.raises(PermissionDeniedError):
        await service.create(
            db, kind=ApprovalKind.PAYOUT, maker=marketing, reason=LY_DO, amount=Decimal("1")
        )


@pytest.mark.money
@pytest.mark.integration
async def test_da_quyet_dinh_roi_thi_khong_quyet_dinh_lai(db):
    """Bấm hai lần vì mạng chậm không được phép thành hai lần chi tiền."""
    ke_toan = await _staff(db, "kt3@goan.vn", ["finance_accountant"])
    truong_phong = await _staff(db, "tp3@goan.vn", ["finance_manager"])
    request = await service.create(
        db, kind=ApprovalKind.PAYOUT, maker=ke_toan, reason=LY_DO, amount=Decimal("1000000")
    )
    await service.approve(db, request, truong_phong)

    with pytest.raises(ConflictError):
        await service.reject(db, request, truong_phong)


@pytest.mark.money
@pytest.mark.integration
async def test_de_nghi_qua_han_thi_khong_duyet_duoc_va_bi_job_dong_lai(db):
    from datetime import datetime, timedelta, timezone

    ke_toan = await _staff(db, "kt4@goan.vn", ["finance_accountant"])
    truong_phong = await _staff(db, "tp4@goan.vn", ["finance_manager"])
    request = await service.create(
        db, kind=ApprovalKind.PAYOUT, maker=ke_toan, reason=LY_DO, amount=Decimal("1000000")
    )
    request.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db.commit()

    with pytest.raises(ConflictError):
        await service.approve(db, request, truong_phong)

    assert await service.expire_due(db) == 1
    await db.refresh(request)
    assert request.status is ApprovalStatus.EXPIRED


@pytest.mark.integration
async def test_chi_nguoi_tao_moi_rut_lai_de_nghi_cua_minh(db):
    ke_toan_1 = await _staff(db, "kt5@goan.vn", ["finance_accountant"])
    ke_toan_2 = await _staff(db, "kt6@goan.vn", ["finance_accountant"])
    request = await service.create(
        db, kind=ApprovalKind.PAYOUT, maker=ke_toan_1, reason=LY_DO, amount=Decimal("1")
    )

    with pytest.raises(PermissionDeniedError):
        await service.cancel(db, request, ke_toan_2)
    assert (await service.cancel(db, request, ke_toan_1)).status is ApprovalStatus.CANCELLED


@pytest.mark.money
@pytest.mark.integration
async def test_phat_gian_lan_di_dung_cap_quyen_rieng(db):
    """Risk analyst đề xuất (maker), ops manager duyệt (checker) — theo ma trận vai trò."""
    analyst = await _staff(db, "risk@goan.vn", ["risk_analyst"])
    manager = await _staff(db, "opsmgr@goan.vn", ["ops_manager"])

    request = await service.create(
        db,
        kind=ApprovalKind.FRAUD_PENALTY,
        maker=analyst,
        reason="Chạy vòng 3 chuyến liên tiếp, vượt 1.5x quãng đường tối ưu",
        amount=Decimal("500000"),
        resource_type="driver",
        resource_id="d-9",
    )
    decided = await service.approve(db, request, manager)

    assert decided.status is ApprovalStatus.APPROVED


@pytest.mark.money
@pytest.mark.api
async def test_luong_maker_checker_qua_http(db, api_client):
    from tests.domains.test_iam import staff_headers

    maker_headers = await staff_headers(
        db, api_client, roles=["finance_accountant"], email="kt-http@goan.vn"
    )
    checker_headers = await staff_headers(
        db, api_client, roles=["finance_manager"], email="tp-http@goan.vn"
    )

    created = await api_client.post(
        "/api/v1/ops/approvals",
        headers=maker_headers,
        json={"kind": "payout", "reason": LY_DO, "amount": "5000000"},
    )
    assert created.status_code == 201
    approval_id = created.json()["id"]

    tu_duyet = await api_client.post(
        f"/api/v1/ops/approvals/{approval_id}/approve", headers=maker_headers, json={}
    )
    nguoi_khac_duyet = await api_client.post(
        f"/api/v1/ops/approvals/{approval_id}/approve", headers=checker_headers, json={}
    )

    assert tu_duyet.status_code == 403
    assert nguoi_khac_duyet.status_code == 200
    assert nguoi_khac_duyet.json()["status"] == "approved"
