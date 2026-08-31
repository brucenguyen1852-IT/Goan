from pydantic import BaseModel, Field


class OtpRequestIn(BaseModel):
    phone: str = Field(..., examples=["0912345678"])


class OtpVerifyIn(BaseModel):
    phone: str
    otp: str = Field(..., min_length=6, max_length=6)
    full_name: str | None = None  # dùng khi đăng ký lần đầu


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
