"""Schema message WebSocket (SPEC 6.3)."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ClientEvent(str, Enum):
    LOCATION_UPDATE = "location_update"
    TRIP_OFFER_RESPONSE = "trip_offer_response"
    PING = "ping"
    # Chat (P2-05, P2-14). "Đang gõ" KHÔNG lưu DB: nó chỉ có nghĩa trong vài giây, lưu lại
    # là ghi hàng triệu dòng cho một thông tin không ai đọc lại bao giờ.
    CHAT_TYPING = "chat.typing"


class ServerEvent(str, Enum):
    TRIP_OFFER = "trip_offer"
    TRIP_MATCHED = "trip_matched"
    TRIP_STATUS_CHANGED = "trip_status_changed"
    TRIP_COMPLETED = "trip_completed"
    DRIVER_LOCATION = "driver_location"
    SELFIE_CHECK_REQUIRED = "selfie_check_required"
    # Thông báo từ Console: duyệt/từ chối hồ sơ, khoá/mở tài khoản (P1-10)
    SYSTEM_NOTICE = "system_notice"
    # Ảnh chụp đội xe đẩy cho Console mỗi vài giây (P1-09)
    OPS_FLEET_UPDATE = "ops.fleet_update"
    # Chat (P2): tin mới, đang gõ, đã đọc
    CHAT_MESSAGE = "chat.message"
    CHAT_TYPING = "chat.typing"
    CHAT_READ = "chat.read"
    # Token hết hạn giữa lúc đang kết nối. Không báo thì client giữ một kết nối vô hiệu
    # và tưởng mình vẫn đang online (P2-14).
    AUTH_EXPIRED = "auth.expired"
    ERROR = "error"
    PONG = "pong"


class LocationUpdateMessage(BaseModel):
    type: ClientEvent = ClientEvent.LOCATION_UPDATE
    lat: float
    lng: float
    trip_id: str | None = None


class TripOfferResponseMessage(BaseModel):
    type: ClientEvent = ClientEvent.TRIP_OFFER_RESPONSE
    trip_id: str
    accept: bool


def server_message(event: ServerEvent, **payload: Any) -> dict[str, Any]:
    return {"type": event.value, **payload}
