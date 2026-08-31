"""Wallet Service — chia ví (settlement) sau mỗi chuyến hoàn thành, đúng luồng
mô tả trong tài liệu Thiết kế chi tiết luồng thanh toán, mục 4 (Bước 4).

Nguyên tắc: mọi thay đổi số dư đều là 1 INSERT bút toán mới vào wallet_transactions,
không bao giờ UPDATE trực tiếp số dư. Toàn bộ hàm dưới đây PHẢI chạy trong 1 DB
transaction ở tầng gọi (endpoint/service cha) để đảm bảo tính ACID.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.driver import DriverProfile, EscrowStatus
from app.models.wallet import DriverDebt, TxDirection, WalletTransaction, WalletType


def get_wallet_balance(db: Session, wallet_type: WalletType, owner_id: uuid.UUID | None) -> int:
    """Tính số dư ví bằng cách cộng dồn toàn bộ bút toán — luôn là nguồn sự thật duy nhất."""
    credit = (
        db.query(func.coalesce(func.sum(WalletTransaction.amount), 0))
        .filter(
            WalletTransaction.wallet_type == wallet_type,
            WalletTransaction.owner_id == owner_id,
            WalletTransaction.direction == TxDirection.CREDIT,
        )
        .scalar()
    )
    debit = (
        db.query(func.coalesce(func.sum(WalletTransaction.amount), 0))
        .filter(
            WalletTransaction.wallet_type == wallet_type,
            WalletTransaction.owner_id == owner_id,
            WalletTransaction.direction == TxDirection.DEBIT,
        )
        .scalar()
    )
    return int(credit) - int(debit)


def _record(db: Session, wallet_type: WalletType, owner_id, trip_id, amount: int,
            direction: TxDirection, description: str) -> None:
    if amount <= 0:
        return
    db.add(
        WalletTransaction(
            wallet_type=wallet_type,
            owner_id=owner_id,
            trip_id=trip_id,
            amount=amount,
            direction=direction,
            description=description,
        )
    )


def settle_trip(
    db: Session,
    trip_id: uuid.UUID,
    driver: DriverProfile,
    total_fare: int,
    surcharge_far_pickup: int,
    partner_id: uuid.UUID | None,
    partner_commission_rate: float,
    insurance_fee_rate: float,
    is_cash_payment: bool,
) -> None:
    """Chia ví cho 1 chuyến đã hoàn thành. Áp dụng cho cả 2 nhánh online/tiền mặt
    (xem tài liệu Payment Flow mục 4, Bước 4)."""

    fare_excl_surcharge = total_fare - surcharge_far_pickup

    platform_take = round(fare_excl_surcharge * settings.PLATFORM_TAKE_RATE)
    driver_share = round(fare_excl_surcharge * settings.DRIVER_SHARE_RATE) + surcharge_far_pickup

    partner_commission = round(fare_excl_surcharge * partner_commission_rate) if partner_id else 0
    insurance_fee = round(fare_excl_surcharge * insurance_fee_rate)
    platform_net = platform_take - partner_commission - insurance_fee

    # 1) Doanh thu nền tảng (net, sau khi trừ hoa hồng đối tác & phí bảo hiểm)
    _record(db, WalletType.PLATFORM_REVENUE, None, trip_id, platform_net,
            TxDirection.CREDIT, "Doanh thu nền tảng (take-rate - hoa hồng ĐT - phí BH)")

    if partner_id and partner_commission > 0:
        _record(db, WalletType.PARTNER_COMMISSION, partner_id, trip_id, partner_commission,
                TxDirection.CREDIT, "Hoa hồng đối tác (nhà hàng/khách sạn)")

    if insurance_fee > 0:
        _record(db, WalletType.INSURANCE_FEE, None, trip_id, insurance_fee,
                TxDirection.CREDIT, "Phí bảo hiểm theo chuyến")

    # 2) Thu nhập tài xế — trích ký quỹ 15% nếu chưa đủ định mức
    escrow_cut = 0
    if driver.escrow_status == EscrowStatus.ACCUMULATING:
        escrow_cut = round(driver_share * settings.ESCROW_DEDUCTION_RATE)
        remaining_target = driver.escrow_target - driver.escrow_balance
        escrow_cut = min(escrow_cut, max(remaining_target, 0))

    earning_cut = driver_share - escrow_cut

    if escrow_cut > 0:
        _record(db, WalletType.DRIVER_ESCROW, driver.id, trip_id, escrow_cut,
                TxDirection.CREDIT, "Trích ký quỹ 15% từ chuyến")
        driver.escrow_balance += escrow_cut
        if driver.escrow_balance >= driver.escrow_target:
            driver.escrow_status = EscrowStatus.FULL

    _record(db, WalletType.DRIVER_EARNING, driver.id, trip_id, earning_cut,
            TxDirection.CREDIT, "Thu nhập tài xế sau ký quỹ")

    # 3) Nhánh tiền mặt: tài xế đã giữ 100% tiền mặt của khách -> ghi nợ hoa hồng
    #    bằng cách debit ngay phần platform_take khỏi ví thu nhập/ký quỹ tài xế.
    if is_cash_payment:
        _apply_cash_commission_debt(db, driver, trip_id, platform_take)


def _apply_cash_commission_debt(db: Session, driver: DriverProfile, trip_id: uuid.UUID, commission_owed: int) -> None:
    """Tài xế thu tiền mặt => nợ nền tảng phần hoa hồng. Cấn trừ ưu tiên từ earning
    wallet, sau đó escrow (không vượt định mức tối thiểu), phần còn thiếu ghi nợ."""
    available_earning = get_wallet_balance(db, WalletType.DRIVER_EARNING, driver.id)
    debit_from_earning = min(available_earning, commission_owed)
    remaining = commission_owed - debit_from_earning

    if debit_from_earning > 0:
        _record(db, WalletType.DRIVER_EARNING, driver.id, trip_id, debit_from_earning,
                TxDirection.DEBIT, "Cấn trừ hoa hồng chuyến thanh toán tiền mặt")

    if remaining > 0:
        db.add(DriverDebt(driver_id=driver.id, trip_id=trip_id, source="cash_commission", amount=remaining))
