import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import FraudReviewStatus
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.deps import get_current_admin
from app.domains.fraud import service as fraud_service
from app.domains.fraud.models import FraudIncident, FraudReviewQueue
from app.domains.fraud.schemas import FraudIncidentOut, FraudReviewItemOut, ReviewDecision
from app.domains.trips import repository as trips_repo
from app.domains.users import repository as users_repo
from app.domains.users.models import User

router = APIRouter(prefix="/admin/fraud", tags=["fraud"])


@router.get("/incidents", response_model=list[FraudIncidentOut])
async def list_incidents(
    _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> list[FraudIncidentOut]:
    stmt = select(FraudIncident).order_by(FraudIncident.created_at.desc()).limit(200)
    rows = (await db.execute(stmt)).scalars().all()
    return [FraudIncidentOut.model_validate(r) for r in rows]


@router.get("/review-queue", response_model=list[FraudReviewItemOut])
async def list_review_queue(
    _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> list[FraudReviewItemOut]:
    """Tín hiệu nghi ngờ thanh toán ngoài app, chờ admin xử lý thủ công (SPEC 7.3)."""
    stmt = (
        select(FraudReviewQueue)
        .where(FraudReviewQueue.status == FraudReviewStatus.PENDING)
        .order_by(FraudReviewQueue.signal_score.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [FraudReviewItemOut.model_validate(r) for r in rows]


@router.post("/review-queue/{item_id}/decide", response_model=FraudReviewItemOut)
async def decide_review_item(
    item_id: uuid.UUID,
    payload: ReviewDecision,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> FraudReviewItemOut:
    item = await db.get(FraudReviewQueue, item_id)
    if item is None:
        raise NotFoundError("Không tìm thấy mục review")

    item.status = FraudReviewStatus.CONFIRMED if payload.confirmed else FraudReviewStatus.CLEARED
    item.reviewed_by = admin.id
    item.reviewed_at = datetime.now(timezone.utc)

    if payload.confirmed:
        profile = await users_repo.get_driver_profile_by_user(db, item.driver_id)
        driver = await users_repo.get_user(db, item.driver_id)
        if profile is None or driver is None:
            raise NotFoundError("Không tìm thấy tài xế")
        trip = await trips_repo.get_trip(db, payload.trip_id) if payload.trip_id else None
        await fraud_service.confirm_off_app_payment(db, profile=profile, user=driver, trip=trip)
    else:
        await db.commit()

    return FraudReviewItemOut.model_validate(item)
