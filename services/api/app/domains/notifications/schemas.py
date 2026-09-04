"""Schema đăng ký thiết bị nhận push."""

from pydantic import BaseModel, ConfigDict, Field

from app.domains.notifications.constants import DevicePlatform


class RegisterPushTokenRequest(BaseModel):
    token: str = Field(min_length=8, max_length=255)
    platform: DevicePlatform


class PushTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform: DevicePlatform
    is_active: bool
