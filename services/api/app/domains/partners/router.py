from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.domains.partners import service as partners_service
from app.domains.partners.schemas import PartnerQrInfo
from app.domains.pricing.schemas import Coordinate

router = APIRouter(prefix="/partners", tags=["partners"])


@router.get("/qr/{token}", response_model=PartnerQrInfo)
async def partner_by_qr(token: str, db: AsyncSession = Depends(get_db)) -> PartnerQrInfo:
    """Endpoint public: mở luồng đặt xe rút gọn với pickup = toạ độ nhà hàng."""
    partner = await partners_service.get_partner_by_qr(db, token)
    pickup = (
        Coordinate(lat=partner.lat, lng=partner.lng)
        if partner.lat is not None and partner.lng is not None
        else None
    )
    return PartnerQrInfo(
        partner_id=partner.id,
        type=partner.type,
        name=partner.name,
        address=partner.address,
        pickup=pickup,
        commission_rate=partner.commission_rate,
    )
