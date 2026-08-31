"""Partners service (SPEC 10): nhà hàng (QR đặt xe tại bàn), khách sạn (VAT), bảo hiểm."""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PartnerType
from app.core.exceptions import NotFoundError
from app.core.logging import log_event
from app.core.money import vnd
from app.domains.partners.models import MarketingSubsidy, Partner, PartnerCommission, SatelliteZone
from app.domains.trips.models import Trip

logger = logging.getLogger("goan.partners")


async def get_partner_by_qr(db: AsyncSession, token: str) -> Partner:
    stmt = select(Partner).where(Partner.qr_code_token == token, Partner.active.is_(True))
    partner = (await db.execute(stmt)).scalar_one_or_none()
    if partner is None:
        raise NotFoundError("Mã QR đối tác không hợp lệ")
    return partner


async def record_trip_commission(db: AsyncSession, trip: Trip) -> PartnerCommission | None:
    """Hoa hồng nhà hàng tính trên final_fare khi chuyến hoàn thành (SPEC 10.1)."""
    if trip.restaurant_partner_id is None or trip.final_fare is None:
        return None
    partner = await db.get(Partner, trip.restaurant_partner_id)
    if partner is None or partner.type is not PartnerType.RESTAURANT:
        return None

    amount = vnd(trip.final_fare * partner.commission_rate / Decimal("100"))
    if amount <= 0:
        return None
    commission = PartnerCommission(partner_id=partner.id, trip_id=trip.id, amount=amount)
    db.add(commission)
    await db.flush()
    log_event(
        logger,
        "partner_commission_recorded",
        partner_id=str(partner.id),
        trip_id=str(trip.id),
        amount=str(amount),
    )
    return commission


async def get_insurance_fee_rate(db: AsyncSession) -> Decimal | None:
    """Rate bảo hiểm lấy từ partner type=insurance đang active (5-8%), None nếu chưa cấu hình."""
    stmt = select(Partner).where(
        Partner.type == PartnerType.INSURANCE, Partner.active.is_(True)
    ).limit(1)
    partner = (await db.execute(stmt)).scalar_one_or_none()
    if partner is None:
        return None
    return Decimal(partner.commission_rate) / Decimal("100")


async def find_new_zone_for_pickup(
    db: AsyncSession, lat: float, lng: float
) -> SatelliteZone | None:
    """Vùng mới mở gần điểm đón -> trip được trợ cấp từ ngân sách marketing (SPEC 6.4)."""
    from app.core.geo import haversine_m

    stmt = select(SatelliteZone).where(
        SatelliteZone.active.is_(True), SatelliteZone.is_new_zone.is_(True)
    )
    for zone in (await db.execute(stmt)).scalars().all():
        if haversine_m(lat, lng, zone.lat, zone.lng) <= zone.radius_m:
            return zone
    return None


async def record_marketing_subsidy(
    db: AsyncSession, trip: Trip, zone: SatelliteZone, amount: Decimal
) -> MarketingSubsidy:
    subsidy = MarketingSubsidy(
        trip_id=trip.id,
        zone_id=zone.id,
        amount=vnd(amount),
        note=f"Trợ cấp vùng mới: {zone.name}",
    )
    db.add(subsidy)
    await db.flush()
    return subsidy


async def list_satellite_zones(db: AsyncSession) -> list[SatelliteZone]:
    stmt = select(SatelliteZone).where(SatelliteZone.active.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def get_partner(db: AsyncSession, partner_id: uuid.UUID) -> Partner:
    partner = await db.get(Partner, partner_id)
    if partner is None:
        raise NotFoundError("Không tìm thấy đối tác")
    return partner
