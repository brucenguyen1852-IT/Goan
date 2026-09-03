from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User, UserRole, UserStatus
from app.schemas.auth import OtpRequestIn, OtpVerifyIn, TokenOut
from app.services.otp_service import generate_and_send_otp, verify_otp

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", status_code=204)
def request_otp(payload: OtpRequestIn) -> None:
    generate_and_send_otp(payload.phone)
    return None


@router.post("/otp/verify", response_model=TokenOut)
def verify_otp_and_login(payload: OtpVerifyIn, db: Session = Depends(get_db)) -> TokenOut:
    if not verify_otp(payload.phone, payload.otp):
        raise HTTPException(status_code=400, detail="OTP không đúng hoặc đã hết hạn")

    user = db.query(User).filter(User.phone == payload.phone).first()
    if user is None:
        # Đăng ký tự động khi xác thực OTP thành công lần đầu (chuẩn UX của Grab/Be)
        user = User(
            phone=payload.phone,
            full_name=payload.full_name or "Khách hàng GoAn",
            role=UserRole.CUSTOMER,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.value})
    refresh_token = create_refresh_token(subject=str(user.id))
    return TokenOut(access_token=access_token, refresh_token=refresh_token)
