"""Đẩy trạng thái đội xe cho Console theo thời gian thực (P1-09).

Vì sao gom 3 giây một lần chứ không đẩy theo từng điểm GPS: 500 tài xế ping mỗi 2 giây là
250 message/giây cho MỖI người đang mở Console. Điều phối viên không đọc nổi tốc độ đó, và
trình duyệt cũng không vẽ lại kịp. Gom lại thành một ảnh chụp mỗi 3 giây thì tải xuống bằng
một phần trăm, mà cảm giác "đang sống" vẫn nguyên.

Chỉ chạy khi có ít nhất một Console đang mở. Người cuối cùng đóng tab thì vòng lặp tự dừng —
không ai xem thì không việc gì phải truy vấn DB ba giây một lần suốt đêm.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select

from app.config import settings
from app.core.constants import OnlineStatus, TripStatus
from app.core.logging import log_event
from app.core.pii import mask_name
from app.database import SessionFactory
from app.domains.trips.models import Trip
from app.domains.users.models import DriverProfile
from app.websocket.events import ServerEvent

logger = logging.getLogger("goan.ws.ops")

ACTIVE_TRIP_STATUSES = (
    TripStatus.MATCHED,
    TripStatus.DRIVER_ARRIVING,
    TripStatus.QR_VERIFIED,
    TripStatus.IN_PROGRESS,
)


async def build_snapshot() -> dict[str, Any]:
    """Cùng dữ liệu với `GET /ops/fleet`, và cũng KHÔNG kèm PII: bản đồ không cần số điện thoại."""
    async with SessionFactory() as db:
        profiles = list(
            (
                await db.execute(
                    select(DriverProfile).where(DriverProfile.online_status != OnlineStatus.OFFLINE)
                )
            )
            .scalars()
            .all()
        )
        active = list(
            (await db.execute(select(Trip).where(Trip.status.in_(ACTIVE_TRIP_STATUSES))))
            .scalars()
            .all()
        )
    trip_by_driver = {t.driver_id: str(t.id) for t in active if t.driver_id}
    return {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "drivers_online": sum(1 for p in profiles if p.online_status is OnlineStatus.ONLINE),
        "drivers_on_trip": sum(1 for p in profiles if p.online_status is OnlineStatus.ON_TRIP),
        "trips_active": len(active),
        "drivers": [
            {
                "driver_id": str(p.user_id),
                "full_name_masked": mask_name(p.user.full_name if p.user else None),
                "online_status": p.online_status.value,
                "lat": p.current_lat,
                "lng": p.current_lng,
                "current_trip_id": trip_by_driver.get(p.user_id),
            }
            for p in profiles
        ],
    }


class OpsFleetBroadcaster:
    """Một vòng lặp duy nhất cho tất cả Console đang mở, không phải mỗi tab một vòng."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def viewer_count(self) -> int:
        return len(self._clients)

    async def subscribe(self, websocket: WebSocket, staff_id: uuid.UUID | str) -> None:
        async with self._lock:
            self._clients.add(websocket)
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._run())
        log_event(
            logger, "ops_fleet_subscribed", staff_id=str(staff_id), viewers=len(self._clients)
        )

    async def unsubscribe(self, websocket: WebSocket) -> None:
        task: asyncio.Task | None = None
        async with self._lock:
            self._clients.discard(websocket)
            if not self._clients and self._task is not None:
                task, self._task = self._task, None
                task.cancel()
        if task is not None:
            # Chờ nó dừng HẲN, không chỉ gửi tín hiệu huỷ: một truy vấn DB đang dở sẽ chạy tiếp
            # tới điểm await kế tiếp và có thể chạm vào phiên đã đóng.
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._clients.clear()

    async def broadcast_once(self) -> int:
        """Gửi một ảnh chụp cho mọi Console đang mở. Trả về số client nhận được."""
        if not self._clients:
            return 0
        message = {"type": ServerEvent.OPS_FLEET_UPDATE.value, "data": await build_snapshot()}
        sent = 0
        for websocket in list(self._clients):
            try:
                await websocket.send_json(message)
                sent += 1
            except Exception:
                # Tab đã đóng mà chưa kịp báo: bỏ ra khỏi danh sách, không để một client chết
                # làm hỏng lượt gửi của những người còn lại.
                self._clients.discard(websocket)
        return sent

    async def _run(self) -> None:
        while True:
            try:
                await self.broadcast_once()
            except Exception:  # pragma: no cover - vòng lặp nền không được chết vì một lỗi
                logger.warning("Lỗi khi đẩy trạng thái đội xe", exc_info=True)
            await asyncio.sleep(settings.OPS_FLEET_PUSH_SECONDS)


broadcaster = OpsFleetBroadcaster()
