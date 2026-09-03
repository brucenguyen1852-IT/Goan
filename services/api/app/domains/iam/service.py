"""Nghiệp vụ IAM: đồng bộ danh mục quyền, đăng nhập nội bộ, phân quyền.

Khác biệt cốt lõi so với đăng nhập của khách/tài xế (OTP qua SĐT): tài khoản nội bộ chạm được
vào tiền và dữ liệu cá nhân của hàng nghìn người, nên **bắt buộc 2FA** và **khoá sau 5 lần sai**.
Một tài khoản CSKH bị dò mật khẩu thành công là đủ để lộ toàn bộ số điện thoại khách hàng.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    UnauthorizedError,
)
from app.core.logging import log_event
from app.core.security import hash_password, verify_password
from app.domains.iam.constants import PERMISSIONS, ROLES, WILDCARD
from app.domains.iam.models import Permission, Role, RolePermission, StaffRole, StaffUser

logger = logging.getLogger("goan.iam")

# Một thông điệp duy nhất cho mọi kiểu sai: email lạ, sai mật khẩu, sai mã 2FA. Trả lời khác
# nhau là chỉ cho kẻ tấn công biết email nào có thật.
_SAI_THONG_TIN = "Email, mật khẩu hoặc mã xác thực không đúng"


# --- Danh mục quyền -------------------------------------------------------------------


async def sync_catalog(db: AsyncSession) -> dict[str, int]:
    """Nạp danh mục quyền và 12 vai trò vào DB. Chạy lại nhiều lần không sao.

    Chỉ **thêm** thứ còn thiếu. Không xoá quyền mà người vận hành đã tự gán thêm từ Console —
    seed không được phép ghi đè quyết định của người đang vận hành hệ thống.
    """
    added_perms = 0
    existing_perms = {p.code: p for p in (await db.execute(select(Permission))).scalars().all()}
    for code, description in PERMISSIONS.items():
        if code not in existing_perms:
            perm = Permission(code=code, description=description)
            db.add(perm)
            existing_perms[code] = perm
            added_perms += 1
    if WILDCARD not in existing_perms:
        perm = Permission(code=WILDCARD, description="Toàn quyền (chỉ super_admin)")
        db.add(perm)
        existing_perms[WILDCARD] = perm
        added_perms += 1
    await db.flush()

    added_roles = 0
    added_links = 0
    existing_roles = {r.code: r for r in (await db.execute(select(Role))).scalars().all()}
    for code, (name, perm_codes) in ROLES.items():
        role = existing_roles.get(code)
        if role is None:
            role = Role(code=code, name=name, is_system=True)
            db.add(role)
            await db.flush()
            existing_roles[code] = role
            added_roles += 1
        current = {
            link.permission_id
            for link in (
                await db.execute(select(RolePermission).where(RolePermission.role_id == role.id))
            )
            .scalars()
            .all()
        }
        for perm_code in perm_codes:
            perm = existing_perms[perm_code]
            if perm.id not in current:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
                added_links += 1

    await db.commit()
    return {"permissions": added_perms, "roles": added_roles, "role_permissions": added_links}


# --- Phân quyền -----------------------------------------------------------------------


def permissions_of(staff: StaffUser) -> set[str]:
    return {perm.code for role in staff.roles for perm in role.permissions}


def has_permission(staff: StaffUser, required: str) -> bool:
    codes = permissions_of(staff)
    return WILDCARD in codes or required in codes


def assert_permission(staff: StaffUser, required: str) -> None:
    """403 kèm ĐÚNG mã quyền còn thiếu — người vận hành cần biết phải xin quyền gì."""
    if not has_permission(staff, required):
        raise PermissionDeniedError(
            f"Thiếu quyền '{required}'",
            details={"required_permission": required, "email": staff.email},
        )


# --- Vòng đời tài khoản ---------------------------------------------------------------


async def get_by_email(db: AsyncSession, email: str) -> StaffUser | None:
    stmt = select(StaffUser).where(StaffUser.email == email.strip().lower())
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_by_id(db: AsyncSession, staff_id: uuid.UUID) -> StaffUser:
    staff = await db.get(StaffUser, staff_id)
    if staff is None:
        raise NotFoundError("Không tìm thấy nhân sự")
    return staff


async def create_staff(
    db: AsyncSession,
    *,
    email: str,
    full_name: str,
    password: str,
    role_codes: list[str],
) -> tuple[StaffUser, str]:
    """Tạo tài khoản nội bộ. Trả về (nhân sự, URI để quét vào app xác thực).

    Bí mật TOTP sinh ngay lúc tạo và chỉ trả về **một lần duy nhất** ở đây. Không có endpoint
    nào đọc lại được nó: đọc lại được nghĩa là ai chiếm được tài khoản admin cũng vượt được 2FA
    của mọi người khác.
    """
    email = email.strip().lower()
    if await get_by_email(db, email) is not None:
        raise ConflictError("Email này đã có tài khoản")

    secret = pyotp.random_base32()
    staff = StaffUser(
        email=email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        totp_secret=secret,
    )
    db.add(staff)
    await db.flush()
    await _replace_roles(db, staff, role_codes)
    await db.commit()
    await db.refresh(staff)

    log_event(logger, "staff_created", staff_id=str(staff.id), roles=role_codes)
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.APP_NAME)
    return staff, uri


async def _replace_roles(db: AsyncSession, staff: StaffUser, role_codes: list[str]) -> None:
    roles = (
        (await db.execute(select(Role).where(Role.code.in_(role_codes)))).scalars().all()
        if role_codes
        else []
    )
    found = {r.code for r in roles}
    missing = [code for code in role_codes if code not in found]
    if missing:
        raise NotFoundError("Vai trò không tồn tại", details={"roles": missing})

    for link in (
        (await db.execute(select(StaffRole).where(StaffRole.staff_user_id == staff.id)))
        .scalars()
        .all()
    ):
        await db.delete(link)
    await db.flush()
    for role in roles:
        db.add(StaffRole(staff_user_id=staff.id, role_id=role.id))
    await db.flush()


async def set_roles(db: AsyncSession, staff: StaffUser, role_codes: list[str]) -> StaffUser:
    await _replace_roles(db, staff, role_codes)
    await db.commit()
    await db.refresh(staff)
    log_event(logger, "staff_roles_changed", staff_id=str(staff.id), roles=role_codes)
    return staff


async def deactivate(db: AsyncSession, staff: StaffUser, reason: str) -> StaffUser:
    """Vô hiệu hoá, KHÔNG xoá: xoá dòng này là mất dấu vết mọi thao tác người đó từng làm."""
    staff.is_active = False
    staff.deactivated_at = datetime.now(timezone.utc)
    staff.deactivated_reason = reason
    await db.commit()
    await db.refresh(staff)
    log_event(logger, "staff_deactivated", staff_id=str(staff.id), reason=reason)
    return staff


async def reactivate(db: AsyncSession, staff: StaffUser) -> StaffUser:
    staff.is_active = True
    staff.deactivated_at = None
    staff.deactivated_reason = None
    staff.failed_attempts = 0
    staff.locked_until = None
    await db.commit()
    await db.refresh(staff)
    log_event(logger, "staff_reactivated", staff_id=str(staff.id))
    return staff


async def unlock(db: AsyncSession, staff: StaffUser) -> StaffUser:
    """Gỡ khoá sớm, không phải chờ hết thời gian — dùng khi người thật gõ nhầm 5 lần."""
    staff.failed_attempts = 0
    staff.locked_until = None
    await db.commit()
    await db.refresh(staff)
    log_event(logger, "staff_unlocked", staff_id=str(staff.id))
    return staff


# --- Đăng nhập ------------------------------------------------------------------------


def is_locked(staff: StaffUser, *, now: datetime | None = None) -> bool:
    if staff.locked_until is None:
        return False
    moment = now or datetime.now(timezone.utc)
    locked_until = staff.locked_until
    if locked_until.tzinfo is None:  # SQLite trả về datetime không có tzinfo
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return locked_until > moment


async def _register_failure(db: AsyncSession, staff: StaffUser) -> None:
    staff.failed_attempts += 1
    if staff.failed_attempts >= settings.STAFF_MAX_FAILED_ATTEMPTS:
        staff.locked_until = datetime.now(timezone.utc) + timedelta(
            minutes=settings.STAFF_LOCKOUT_MINUTES
        )
        log_event(
            logger,
            "staff_locked_out",
            staff_id=str(staff.id),
            failed_attempts=staff.failed_attempts,
        )
    await db.commit()


async def authenticate(db: AsyncSession, *, email: str, password: str, totp_code: str) -> StaffUser:
    """Email + mật khẩu + TOTP. Thiếu bất kỳ yếu tố nào cũng trả về cùng một lỗi."""
    staff = await get_by_email(db, email)
    if staff is None:
        # Vẫn băm một lần để thời gian trả lời không tố cáo email nào có thật.
        hash_password(password)
        raise UnauthorizedError(_SAI_THONG_TIN)

    if not staff.is_active:
        raise PermissionDeniedError("Tài khoản đã bị vô hiệu hoá")
    if is_locked(staff):
        raise PermissionDeniedError(
            "Tài khoản đang bị khoá tạm thời do nhập sai nhiều lần",
            details={
                "locked_until": staff.locked_until.isoformat() if staff.locked_until else None
            },
        )
    if not staff.totp_secret:
        # Không có 2FA thì không cho vào, kể cả mật khẩu đúng.
        raise PermissionDeniedError("Tài khoản chưa thiết lập xác thực hai lớp")

    if not verify_password(password, staff.password_hash) or not pyotp.TOTP(
        staff.totp_secret
    ).verify(totp_code, valid_window=1):
        await _register_failure(db, staff)
        raise UnauthorizedError(_SAI_THONG_TIN)

    staff.failed_attempts = 0
    staff.locked_until = None
    staff.last_login_at = datetime.now(timezone.utc)
    if staff.totp_confirmed_at is None:
        staff.totp_confirmed_at = staff.last_login_at
    await db.commit()
    await db.refresh(staff)
    log_event(logger, "staff_login", staff_id=str(staff.id))
    return staff


async def change_password(db: AsyncSession, staff: StaffUser, new_password: str) -> None:
    staff.password_hash = hash_password(new_password)
    await db.commit()
    log_event(logger, "staff_password_changed", staff_id=str(staff.id))
