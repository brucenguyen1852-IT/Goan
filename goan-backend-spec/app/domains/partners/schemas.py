import uuid
from decimal import Decimal

from pydantic import BaseModel

from app.core.constants import PartnerType
from app.domains.pricing.schemas import Coordinate


class PartnerQrInfo(BaseModel):
    """Thông tin trả về khi khách quét QR tại bàn nhà hàng (SPEC 10.1) — không cần đăng nhập."""

    partner_id: uuid.UUID
    type: PartnerType
    name: str
    address: str | None
    pickup: Coordinate | None
    commission_rate: Decimal
