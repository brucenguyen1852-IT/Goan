"""Schema cho Console (tài liệu phân định §2.3)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    totp_code: str = Field(
        default="",
        max_length=8,
        description="Mã 6 số từ app xác thực. Bỏ trống được nếu gửi `device_token` còn hiệu lực",
    )
    device_token: str = Field(
        default="", max_length=100, description="Token nhớ thiết bị của lần đăng nhập trước"
    )
    remember_device: bool = Field(
        default=False, description="Nhớ thiết bị này 30 ngày để lần sau không phải nhập mã"
    )
    device_label: str | None = Field(default=None, max_length=200)


class StaffTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Số giây access token còn sống")
    session_expires_in: int = Field(description="Số giây còn lại của phiên làm việc")
    device_token: str | None = Field(
        default=None,
        description="Chỉ trả về khi vừa bật nhớ thiết bị. Lưu lại để lần sau khỏi nhập mã 2FA.",
    )


class StaffRefreshRequest(BaseModel):
    refresh_token: str


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    permissions: list[str] = []


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str


class RolePermissionsRequest(BaseModel):
    permissions: list[str]


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    roles: list[str] = []
    permissions: list[str] = []
    last_login_at: datetime | None = None
    locked_until: datetime | None = None
    deactivated_reason: str | None = None


class StaffCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128, description="Tối thiểu 12 ký tự")
    roles: list[str] = Field(default_factory=list)


class StaffCreateResponse(BaseModel):
    staff: StaffOut
    # Chỉ trả về ĐÚNG MỘT LẦN, ngay sau khi tạo. Không có endpoint nào đọc lại được.
    totp_provisioning_uri: str


class StaffRolesRequest(BaseModel):
    roles: list[str]


class StaffDeactivateRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500, description="Vì sao vô hiệu hoá")


class TrustedDeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_label: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_staff_id: uuid.UUID | None = None
    actor_role: str | None = None
    action: str
    method: str
    path: str
    status_code: int
    resource_type: str | None = None
    resource_id: str | None = None
    ip_address: str | None = None
    request_id: str | None = None
    reason: str | None = None
    duration_ms: int | None = None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    next_cursor: str | None = Field(
        default=None, description="Truyền lại vào `cursor` để lấy trang kế tiếp"
    )
