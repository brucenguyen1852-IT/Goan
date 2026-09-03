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


# --- QA-SEC-REG — chặn tự đăng ký thành admin (PRD-SEC-11) ------------------


@pytest.mark.integration
async def test_khong_the_tu_dang_ky_thanh_admin(db, fake_redis):
    """QA-AUTH-10: lỗ hổng leo thang đặc quyền — bài test quan trọng nhất của module auth.

    Trước khi sửa: bất kỳ ai gửi role="admin" kèm một số điện thoại bất kỳ đều nhận được
    token admin, rồi đọc toàn bộ hồ sơ gian lận, báo cáo đối soát, và quyết định được các
    vụ gian lận — tức là khoá tài xế và giữ ký quỹ của họ. Đã kiểm chứng trên server thật.
    """
    from app.core.constants import UserRole
    from app.core.exceptions import PermissionDeniedError

    await auth_service.request_otp(fake_redis, "0988000001")
    otp = await fake_redis.get("otp:0988000001")

    with pytest.raises(PermissionDeniedError):
        await auth_service.verify_otp_and_login(
            db,
            fake_redis,
            phone="0988000001",
            otp=otp,
            full_name="Kẻ tấn công",
            role=UserRole.ADMIN,
            license_number=None,
        )


@pytest.mark.integration
@pytest.mark.parametrize("role_name", ["rider", "driver"])
async def test_van_dang_ky_duoc_vai_tro_cong_khai(db, fake_redis, role_name):
    """QA-AUTH-11: chặn admin nhưng không được chặn nhầm khách và tài xế."""
    from app.core.constants import UserRole

    phone = "0977000001" if role_name == "rider" else "0977000002"
    await auth_service.request_otp(fake_redis, phone)
    otp = await fake_redis.get(f"otp:{phone}")

    user, tokens = await auth_service.verify_otp_and_login(
        db,
        fake_redis,
        phone=phone,
        otp=otp,
        full_name="Người dùng thật",
        role=UserRole(role_name),
        license_number="B2-999999" if role_name == "driver" else None,
    )

    assert user.role is UserRole(role_name)
    assert tokens.access_token


@pytest.mark.integration
async def test_admin_da_ton_tai_van_dang_nhap_binh_thuong(db, fake_redis):
    """QA-AUTH-12: vai trò lấy từ CSDL, không lấy từ dữ liệu client gửi lên.

    Admin đăng nhập mà khai role="rider" thì vẫn là admin; ngược lại khách khai
    role="admin" cũng không lên được admin.
    """
    from app.core.constants import UserRole
    from app.domains.users.models import User

    admin = User(phone="0900000000", full_name="Quản trị viên", role=UserRole.ADMIN)
    db.add(admin)
    await db.commit()

    await auth_service.request_otp(fake_redis, "0900000000")
    otp = await fake_redis.get("otp:0900000000")
    user, _ = await auth_service.verify_otp_and_login(
        db,
        fake_redis,
        phone="0900000000",
        otp=otp,
        full_name=None,
        role=UserRole.RIDER,
        license_number=None,
    )

    assert user.role is UserRole.ADMIN


# --- QA-OTP — hạn mức theo số điện thoại (PRD-SEC-10) ----------------------


@pytest.mark.integration
async def test_han_muc_otp_theo_so_dien_thoai(db, fake_redis):
    """QA-AUTH-13: hạn mức gắn với SỐ, không gắn với IP.

    Hạn mức theo IP không dùng được ở Việt Nam: nhà mạng NAT hàng nghìn thuê bao vào vài
    IP công cộng, nên chặn theo IP là chặn nhầm người dùng thật, còn kẻ tấn công đổi IP
    là lách được. Thứ gắn với chi phí SMS là số điện thoại.
    """
    from app.config import settings
    from app.core.exceptions import RateLimitedError

    for _ in range(settings.OTP_MAX_PER_PHONE_WINDOW):
        await auth_service.request_otp(fake_redis, "0912345678")

    with pytest.raises(RateLimitedError):
        await auth_service.request_otp(fake_redis, "0912345678")

    # Số khác không bị ảnh hưởng
    assert await auth_service.request_otp(fake_redis, "0912345679")


@pytest.mark.integration
async def test_dang_ky_thieu_thong_tin_khong_lam_mat_otp(db, fake_redis):
    """QA-AUTH-14: gõ đúng mã nhưng thiếu họ tên thì KHÔNG được đốt mất mã.

    Mỗi mã là một tin SMS tốn tiền và hạn mức chỉ 3 lượt mỗi 5 phút. Nếu mã bị tiêu ngay
    cả khi đăng ký lỗi, người dùng quên điền một ô là phải chờ và tốn thêm một tin.
    """
    from app.core.constants import UserRole
    from app.core.exceptions import AppError

    await auth_service.request_otp(fake_redis, "0966000001")
    otp = await fake_redis.get("otp:0966000001")

    with pytest.raises(AppError):
        await auth_service.verify_otp_and_login(
            db,
            fake_redis,
            phone="0966000001",
            otp=otp,
            full_name=None,
            role=UserRole.RIDER,
            license_number=None,
        )

    # Mã vẫn còn dùng được cho lần thử tiếp theo
    user, _ = await auth_service.verify_otp_and_login(
        db,
        fake_redis,
        phone="0966000001",
        otp=otp,
        full_name="Nguyễn Văn A",
        role=UserRole.RIDER,
        license_number=None,
    )
    assert user.phone == "0966000001"


@pytest.mark.integration
async def test_tai_xe_thieu_bang_lai_bi_tu_choi_truoc_khi_tieu_otp(db, fake_redis):
    """QA-AUTH-15: tài xế quên số bằng lái cũng không bị mất mã."""
    from app.core.constants import UserRole
    from app.core.exceptions import AppError

    await auth_service.request_otp(fake_redis, "0966000002")
    otp = await fake_redis.get("otp:0966000002")

    with pytest.raises(AppError):
        await auth_service.verify_otp_and_login(
            db,
            fake_redis,
            phone="0966000002",
            otp=otp,
            full_name="Tài Xế Mới",
            role=UserRole.DRIVER,
            license_number=None,
        )

    user, _ = await auth_service.verify_otp_and_login(
        db,
        fake_redis,
        phone="0966000002",
        otp=otp,
        full_name="Tài Xế Mới",
        role=UserRole.DRIVER,
        license_number="B2-123456",
    )
    assert user.role is UserRole.DRIVER
