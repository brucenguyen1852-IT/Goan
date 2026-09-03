"""QA-AUTH — xoay vòng refresh token và phát hiện tái sử dụng.

Ánh xạ PRD: docs/QA/TRACEABILITY.md mục PRD-SEC-02.
"""

import pytest

from app.core.exceptions import UnauthorizedError
from app.core.security import REFRESH_TOKEN, create_refresh_token, decode_token
from app.domains.auth import service as auth_service
from app.domains.auth import tokens as token_store
from tests.conftest import create_rider

pytestmark = [pytest.mark.security, pytest.mark.prd]


async def test_dang_nhap_tao_ho_token_moi(db, fake_redis):
    """QA-AUTH-01: mỗi lần đăng nhập mở một họ token riêng (một thiết bị = một họ)."""
    rider = await create_rider(db)

    pair_a = await auth_service.issue_tokens(fake_redis, rider)
    pair_b = await auth_service.issue_tokens(fake_redis, rider)

    fam_a = decode_token(pair_a.refresh_token, expected_type=REFRESH_TOKEN)["fam"]
    fam_b = decode_token(pair_b.refresh_token, expected_type=REFRESH_TOKEN)["fam"]
    assert fam_a != fam_b, "Hai lần đăng nhập phải thuộc hai họ khác nhau"


async def test_refresh_xoay_vong_token(db, fake_redis):
    """QA-AUTH-02: refresh trả token MỚI, giữ nguyên họ."""
    rider = await create_rider(db)
    original = await auth_service.issue_tokens(fake_redis, rider)

    rotated = await auth_service.refresh_tokens(db, fake_redis, original.refresh_token)

    assert rotated.refresh_token != original.refresh_token
    assert rotated.access_token != original.access_token
    old = decode_token(original.refresh_token, expected_type=REFRESH_TOKEN)
    new = decode_token(rotated.refresh_token, expected_type=REFRESH_TOKEN)
    assert new["fam"] == old["fam"], "Xoay vòng phải giữ nguyên họ token"
    assert new["jti"] != old["jti"]


async def test_dung_lai_token_cu_thi_thu_hoi_ca_ho(db, fake_redis):
    """QA-AUTH-03: đây là bài test quan trọng nhất của cơ chế này.

    Kịch bản thật: kẻ tấn công lấy được refresh token. Người dùng thật refresh trước
    -> token cũ bị tiêu. Kẻ tấn công dùng token cũ -> hệ thống phát hiện có hai bên cùng
    giữ token và đá cả hai ra. Người dùng thật đăng nhập lại bằng OTP; kẻ tấn công thì không.
    """
    rider = await create_rider(db)
    stolen = await auth_service.issue_tokens(fake_redis, rider)

    # Người dùng thật refresh
    fresh = await auth_service.refresh_tokens(db, fake_redis, stolen.refresh_token)

    # Kẻ tấn công dùng lại token đã tiêu
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh_tokens(db, fake_redis, stolen.refresh_token)

    # Và token hợp lệ của người dùng thật cũng bị vô hiệu -> buộc đăng nhập lại
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh_tokens(db, fake_redis, fresh.refresh_token)


async def test_logout_thu_hoi_ho_token(db, fake_redis):
    """QA-AUTH-04: đăng xuất một thiết bị thì refresh token của thiết bị đó chết hẳn."""
    rider = await create_rider(db)
    pair = await auth_service.issue_tokens(fake_redis, rider)
    claims = decode_token(pair.refresh_token, expected_type=REFRESH_TOKEN)

    await auth_service.logout(fake_redis, claims)

    with pytest.raises(UnauthorizedError):
        await auth_service.refresh_tokens(db, fake_redis, pair.refresh_token)


async def test_logout_khong_anh_huong_thiet_bi_khac(db, fake_redis):
    """QA-AUTH-05: đăng xuất điện thoại không được đá luôn máy tính bảng."""
    rider = await create_rider(db)
    phone = await auth_service.issue_tokens(fake_redis, rider)
    tablet = await auth_service.issue_tokens(fake_redis, rider)

    await auth_service.logout(
        fake_redis, decode_token(phone.refresh_token, expected_type=REFRESH_TOKEN)
    )

    rotated = await auth_service.refresh_tokens(db, fake_redis, tablet.refresh_token)
    assert rotated.access_token


async def test_token_cu_khong_co_fam_van_dung_duoc_mot_lan(db, fake_redis):
    """QA-AUTH-06: người đang đăng nhập trước khi deploy không bị đá ra.

    Token cũ không có trường 'fam'. Lần refresh đầu tiên phải được chấp nhận và nâng cấp
    sang họ mới, thay vì trả 401 cho toàn bộ người dùng ngay sau khi lên bản mới.
    """
    rider = await create_rider(db)
    legacy = create_refresh_token(str(rider.id), rider.role.value)  # không truyền family
    assert "fam" not in decode_token(legacy, expected_type=REFRESH_TOKEN)

    upgraded = await auth_service.refresh_tokens(db, fake_redis, legacy)

    assert "fam" in decode_token(upgraded.refresh_token, expected_type=REFRESH_TOKEN)


async def test_redis_chet_thi_van_refresh_duoc(db, fake_redis):
    """QA-AUTH-07: đánh đổi đã ghi trong docs — ưu tiên sẵn sàng dịch vụ hơn chặt chẽ token.

    Redis chết thì matching và định vị cũng chết; chặn thêm refresh chỉ làm mọi người bị
    đăng xuất hàng loạt mà không tăng an toàn thực tế.
    """
    rider = await create_rider(db)
    pair = await auth_service.issue_tokens(fake_redis, rider)
    fake_redis.fail = True

    rotated = await auth_service.refresh_tokens(db, fake_redis, pair.refresh_token)
    assert rotated.access_token


async def test_khong_the_dung_access_token_de_refresh(db, fake_redis):
    """QA-AUTH-08: nhầm loại token phải bị từ chối."""
    rider = await create_rider(db)
    pair = await auth_service.issue_tokens(fake_redis, rider)

    with pytest.raises(UnauthorizedError):
        await auth_service.refresh_tokens(db, fake_redis, pair.access_token)


async def test_ttl_ho_token_theo_cau_hinh(fake_redis):
    """QA-AUTH-09: khoá thu hồi phải sống ít nhất bằng tuổi refresh token."""
    await token_store.revoke_family(fake_redis, "fam-x")
    assert await token_store.is_family_revoked(fake_redis, "fam-x") is True
    assert await token_store.is_family_revoked(fake_redis, "fam-khac") is False
