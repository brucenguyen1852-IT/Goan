from pydantic import BaseModel, Field

from app.core.constants import UserRole


class OtpRequest(BaseModel):
    phone: str = Field(min_length=9, max_length=20)


class OtpRequestResponse(BaseModel):
    phone: str
    expires_in_sec: int
    # Chỉ trả OTP ở môi trường dev (settings.DEBUG) để test end-to-end, production luôn None.
    debug_otp: str | None = None


class OtpVerify(BaseModel):
    phone: str = Field(min_length=9, max_length=20)
    otp: str
    full_name: str | None = None
    role: UserRole = UserRole.RIDER
    license_number: str | None = None  # bắt buộc khi đăng ký mới với role=driver


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
