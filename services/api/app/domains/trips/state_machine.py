"""State machine chuyến đi (SPEC 5.1) — bảng transition, không dùng if-else lồng nhau.

Ràng buộc cốt lõi chống đơn ma: `in_progress` CHỈ đến được từ `qr_verified`.
"""

from app.core.constants import TripStatus
from app.core.exceptions import InvalidTransitionError

ALLOWED_TRANSITIONS: dict[TripStatus, frozenset[TripStatus]] = {
    TripStatus.REQUESTED: frozenset({TripStatus.MATCHING, TripStatus.CANCELLED_BY_RIDER}),
    TripStatus.MATCHING: frozenset(
        {TripStatus.MATCHED, TripStatus.NO_DRIVER_FOUND, TripStatus.CANCELLED_BY_RIDER}
    ),
    TripStatus.MATCHED: frozenset(
        {
            TripStatus.DRIVER_ARRIVING,
            TripStatus.CANCELLED_BY_RIDER,
            TripStatus.CANCELLED_BY_DRIVER,
        }
    ),
    TripStatus.DRIVER_ARRIVING: frozenset(
        {
            TripStatus.QR_VERIFIED,
            TripStatus.CANCELLED_BY_RIDER,
            TripStatus.CANCELLED_BY_DRIVER,
        }
    ),
    TripStatus.QR_VERIFIED: frozenset({TripStatus.IN_PROGRESS}),
    TripStatus.IN_PROGRESS: frozenset({TripStatus.COMPLETED, TripStatus.CANCELLED_BY_DRIVER}),
    TripStatus.COMPLETED: frozenset({TripStatus.RATED}),
    TripStatus.RATED: frozenset(),
    TripStatus.CANCELLED_BY_RIDER: frozenset(),
    TripStatus.CANCELLED_BY_DRIVER: frozenset(),
    TripStatus.NO_DRIVER_FOUND: frozenset({TripStatus.MATCHING}),  # cho phép retry tìm tài xế
}


def can_transition(current: TripStatus, target: TripStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: TripStatus, target: TripStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(
            f"Không thể chuyển chuyến từ '{current.value}' sang '{target.value}'",
            details={"from": current.value, "to": target.value},
        )
