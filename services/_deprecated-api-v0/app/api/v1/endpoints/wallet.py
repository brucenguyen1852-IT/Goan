import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.models.driver import DriverProfile
from app.models.user import User
from app.models.wallet import DriverDebt, WalletType
from app.schemas.wallet import WalletSummaryOut
from app.services.wallet_service import get_wallet_balance

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("/driver/{driver_id}", response_model=WalletSummaryOut)
def get_driver_wallet(
    driver_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> WalletSummaryOut:
    driver = db.query(DriverProfile).filter(DriverProfile.id == driver_id).first()
    if driver is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ tài xế")

    # Chỉ chính tài xế đó hoặc ops_admin mới được xem
    if str(user.id) != str(driver.user_id) and user.role not in ("ops_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Không có quyền xem ví này")

    earning_balance = get_wallet_balance(db, WalletType.DRIVER_EARNING, driver.id)
    open_debt = (
        db.query(func.coalesce(func.sum(DriverDebt.amount), 0))
        .filter(DriverDebt.driver_id == driver.id, DriverDebt.status == "open")
        .scalar()
    )

    return WalletSummaryOut(
        earning_balance=earning_balance,
        escrow_balance=driver.escrow_balance,
        escrow_target=driver.escrow_target,
        escrow_status=driver.escrow_status.value,
        open_debt=int(open_debt),
    )
