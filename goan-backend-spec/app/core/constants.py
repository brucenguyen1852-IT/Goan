"""Enum dùng chung toàn hệ thống (SPEC 3, 5.1, 7)."""

from enum import Enum


class UserRole(str, Enum):
    RIDER = "rider"
    DRIVER = "driver"
    ADMIN = "admin"


class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"


class OnlineStatus(str, Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    ON_TRIP = "on_trip"


class EscrowStatus(str, Enum):
    ACCUMULATING = "accumulating"
    FULFILLED = "fulfilled"


class EscrowTransactionType(str, Enum):
    ACCRUAL = "accrual"
    PENALTY_DEDUCTION = "penalty_deduction"
    REFUND = "refund"


class TripStatus(str, Enum):
    REQUESTED = "requested"
    MATCHING = "matching"
    MATCHED = "matched"
    DRIVER_ARRIVING = "driver_arriving"
    QR_VERIFIED = "qr_verified"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED_BY_RIDER = "cancelled_by_rider"
    CANCELLED_BY_DRIVER = "cancelled_by_driver"
    NO_DRIVER_FOUND = "no_driver_found"


TERMINAL_TRIP_STATUSES = frozenset(
    {
        TripStatus.COMPLETED,
        TripStatus.CANCELLED_BY_RIDER,
        TripStatus.CANCELLED_BY_DRIVER,
        TripStatus.NO_DRIVER_FOUND,
    }
)


class TimeBand(str, Enum):
    NORMAL = "normal"
    NIGHT = "night"
    PEAK = "peak"


class FraudType(str, Enum):
    GHOST_TRIP = "ghost_trip"
    ROUTE_DEVIATION = "route_deviation"
    OFF_APP_PAYMENT = "off_app_payment"
    DRIVER_SWAP = "driver_swap"


class FraudDetectedBy(str, Enum):
    SYSTEM = "system"
    REPORT = "report"


class FraudSeverity(str, Enum):
    WARNING = "warning"
    ACCOUNT_LOCKED = "account_locked"


class PartnerType(str, Enum):
    RESTAURANT = "restaurant"
    HOTEL = "hotel"
    INSURANCE = "insurance"


class PaymentMethod(str, Enum):
    IN_APP_CARD = "in_app_card"
    IN_APP_WALLET = "in_app_wallet"
    CASH_DISABLED = "cash_disabled"  # chỉ để log, không cho chọn (SPEC 9)


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class WalletTransactionType(str, Enum):
    TRIP_PAYOUT = "trip_payout"
    ESCROW_HOLD = "escrow_hold"
    PAYOUT_WITHDRAWAL = "payout_withdrawal"


class FraudReviewStatus(str, Enum):
    PENDING = "pending"
    CLEARED = "cleared"
    CONFIRMED = "confirmed"
