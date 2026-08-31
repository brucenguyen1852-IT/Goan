"""State machine chuyến đi (SPEC 5.1) — trọng tâm: không thể vào in_progress nếu chưa qr_verified."""

import pytest

from app.core.constants import TripStatus
from app.core.exceptions import InvalidTransitionError
from app.domains.trips.state_machine import assert_transition, can_transition


def test_happy_path_transitions():
    path = [
        (TripStatus.REQUESTED, TripStatus.MATCHING),
        (TripStatus.MATCHING, TripStatus.MATCHED),
        (TripStatus.MATCHED, TripStatus.DRIVER_ARRIVING),
        (TripStatus.DRIVER_ARRIVING, TripStatus.QR_VERIFIED),
        (TripStatus.QR_VERIFIED, TripStatus.IN_PROGRESS),
        (TripStatus.IN_PROGRESS, TripStatus.COMPLETED),
    ]
    for current, target in path:
        assert can_transition(current, target)


def test_in_progress_only_reachable_from_qr_verified():
    for status in TripStatus:
        if status is TripStatus.QR_VERIFIED:
            continue
        assert not can_transition(status, TripStatus.IN_PROGRESS)


def test_cannot_skip_qr_verification():
    with pytest.raises(InvalidTransitionError):
        assert_transition(TripStatus.DRIVER_ARRIVING, TripStatus.IN_PROGRESS)
    with pytest.raises(InvalidTransitionError):
        assert_transition(TripStatus.MATCHED, TripStatus.COMPLETED)


def test_matching_timeout_to_no_driver_found_and_retry():
    assert can_transition(TripStatus.MATCHING, TripStatus.NO_DRIVER_FOUND)
    assert can_transition(TripStatus.NO_DRIVER_FOUND, TripStatus.MATCHING)


def test_cancellation_rules():
    assert can_transition(TripStatus.MATCHED, TripStatus.CANCELLED_BY_RIDER)
    assert can_transition(TripStatus.DRIVER_ARRIVING, TripStatus.CANCELLED_BY_RIDER)
    assert can_transition(TripStatus.DRIVER_ARRIVING, TripStatus.CANCELLED_BY_DRIVER)
    # Chuyến đã kết thúc là trạng thái cuối.
    assert not can_transition(TripStatus.COMPLETED, TripStatus.CANCELLED_BY_RIDER)
    assert not can_transition(TripStatus.CANCELLED_BY_RIDER, TripStatus.MATCHING)


def test_invalid_transition_error_carries_details():
    with pytest.raises(InvalidTransitionError) as exc:
        assert_transition(TripStatus.REQUESTED, TripStatus.COMPLETED)
    assert exc.value.details == {"from": "requested", "to": "completed"}
