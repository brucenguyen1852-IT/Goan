"""Nhân sự nội bộ, vai trò, quyền (tài liệu phân định §2.3).

Ba nguyên tắc đã gắn vào cấu trúc bảng, không để tuỳ ý trong code:

1. **Không dùng chung tài khoản.** Mỗi nhân sự một `staff_users`, định danh bằng email công ty.
2. **Rời công ty là vô hiệu hoá, không xoá.** Có `deactivated_at` + `deactivated_reason`; xoá
   dòng này là mất dấu vết của mọi thao tác người đó từng làm.
3. **Vai trò không cứng trong code.** `role_permissions` nằm ở DB nên sửa quyền không cần deploy.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.model_base import TimestampMixin, uuid_pk
from app.database import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Vai trò hệ thống: seed sinh ra, Console sửa được quyền nhưng không xoá được vai trò.
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    permissions: Mapped[list[Permission]] = relationship(
        secondary="role_permissions", lazy="selectin"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True
    )


class StaffUser(Base, TimestampMixin):
    __tablename__ = "staff_users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Bắt buộc 2FA: tài khoản chưa gắn TOTP thì không đăng nhập được (xem service.authenticate).
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Khoá sau 5 lần sai. Đếm cả sai mật khẩu lẫn sai mã TOTP — kẻ dò mã 6 số cũng phải bị chặn.
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list[Role]] = relationship(secondary="staff_roles", lazy="selectin")


class StaffRole(Base):
    __tablename__ = "staff_roles"
    __table_args__ = (UniqueConstraint("staff_user_id", "role_id", name="uq_staff_role"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    staff_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )


class TrustedDevice(Base):
    """Thiết bị đã qua 2FA, được nhớ trong 30 ngày (P1-13).

    Vì sao lưu ở DB chứ không chỉ ký một token gửi về máy: token đã ký thì không thu hồi được.
    Nhân sự nghỉ việc, máy bị mất, hoặc phát hiện đăng nhập lạ — phải gỡ được ngay, và phải
    nhìn thấy được danh sách máy nào đang được nhớ. Bảng này cho cả hai.

    Chỉ lưu HASH của token: đọc trộm được DB cũng không dựng lại được token để dùng.
    """

    __tablename__ = "staff_trusted_devices"

    id: Mapped[uuid.UUID] = uuid_pk()
    staff_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    device_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
