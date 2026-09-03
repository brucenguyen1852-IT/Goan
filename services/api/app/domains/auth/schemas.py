from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from app.core.constants import UserRole
from app.core.phone import InvalidPhoneError, normalize_phone


def _phone(value: str) -> str:
    """Chuẩn hoá ngay ở biên vào, để tầng nghiệp vụ luôn nhận đúng một dạng số."""
    try:
        return normalize_phone(value)
    except InvalidPhoneError as exc:
        raise ValueError(str(exc)) from exc


VietnamPhone = Annotated[str, BeforeValidator(_phone)]


class OtpRequest(BaseModel):
    phone: VietnamPhone = Field(
        description="Số điện thoại Việt Nam. Nhận cả 0912345678, +84912345678, 84912345678 "
        "và có khoảng trắng — hệ thống tự chuẩn hoá về dạng 0912345678.",
        examples=["0901000001"],
    )


class OtpRequestResponse(BaseModel):
    phone: str
    expires_in_sec: int
    # Chỉ trả OTP ở môi trường dev (settings.DEBUG) để test end-to-end, production luôn None.
    debug_otp: str | None = None


class OtpVerify(BaseModel):
    phone: VietnamPhone = Field(examples=["0901000001"])
    otp: str = Field(min_length=4, max_length=8, examples=["123456"])
    full_name: str | None = None
    role: UserRole = UserRole.RIDER
    license_number: str | None = None  # bắt buộc khi đăng ký mới với role=driver


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
