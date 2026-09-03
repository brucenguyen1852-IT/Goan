"""Schema message WebSocket (SPEC 6.3)."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ClientEvent(str, Enum):
    LOCATION_UPDATE = "location_update"
    TRIP_OFFER_RESPONSE = "trip_offer_response"
    PING = "ping"


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
