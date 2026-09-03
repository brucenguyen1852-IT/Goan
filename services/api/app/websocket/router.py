"""WebSocket endpoint chung cho rider và driver (SPEC 6.1, 6.3)."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.constants import UserRole
from app.core.exceptions import AppError
from app.core.logging import log_event
from app.core.security import decode_token
from app.database import SessionFactory
from app.domains.matching import service as matching_service
from app.domains.trips import repository as trips_repo
from app.domains.users import repository as users_repo
from app.domains.users import service as users_service
from app.redis_client import get_redis
from app.websocket.connection_manager import manager
from app.websocket.events import ClientEvent, ServerEvent, server_message

logger = logging.getLogger("goan.ws")

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)) -> None:
    try:
        payload = decode_token(token)
    except AppError:
        await websocket.close(code=4401)
        return

    user_id = uuid.UUID(payload["sub"])
    role = UserRole(payload["role"])
    await manager.connect(user_id, websocket)
    try:
        while True:
            message = await websocket.receive_json()
            await _handle_message(user_id, role, message, websocket)
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - đóng kết nối an toàn khi lỗi bất ngờ
        logger.exception("ws handler error")
    finally:
        await manager.disconnect(user_id, websocket)


async def _handle_message(
    user_id: uuid.UUID, role: UserRole, message: dict, websocket: WebSocket
) -> None:
    msg_type = message.get("type")

    if msg_type == ClientEvent.PING.value:
        await websocket.send_json(server_message(ServerEvent.PONG))
        return

    if msg_type == ClientEvent.LOCATION_UPDATE.value and role is UserRole.DRIVER:
        lat, lng = float(message["lat"]), float(message["lng"])
        async with SessionFactory() as db:
            profile = await users_repo.get_driver_profile_by_user(db, user_id)
            if profile is None:
                return
            await users_service.update_location(db, get_redis(), profile, lat, lng)
            trip_id = message.get("trip_id")
            if trip_id:
                trip = await trips_repo.get_trip(db, uuid.UUID(trip_id))
                if trip is not None and trip.driver_id == user_id:
                    await trips_repo.add_gps_log(db, trip.id, lat, lng, datetime.now(timezone.utc))
                    await db.commit()
                    await manager.send_to_user(
                        trip.rider_id,
                        server_message(
                            ServerEvent.DRIVER_LOCATION, trip_id=str(trip.id), lat=lat, lng=lng
                        ),
                    )
        return

    if msg_type == ClientEvent.TRIP_OFFER_RESPONSE.value and role is UserRole.DRIVER:
        if not message.get("accept"):
            return
        trip_id = uuid.UUID(message["trip_id"])
        async with SessionFactory() as db:
            trip = await trips_repo.get_trip(db, trip_id)
            if trip is None:
                return
            try:
                await matching_service.accept_offer(db, get_redis(), trip, user_id)
            except AppError as exc:
                await websocket.send_json(
                    server_message(ServerEvent.ERROR, code=exc.code, message=exc.message)
                )
        return

    log_event(logger, "ws_unknown_message", user_id=str(user_id), msg_type=str(msg_type))
