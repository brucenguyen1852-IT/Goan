"""WebSocket cho theo dõi vị trí/trạng thái chuyến đi real-time.

Kiến trúc đơn giản cho MVP: mỗi trip_id có 1 "room" trong bộ nhớ (dict).
Khi scale lên nhiều instance backend, cần thay bằng Redis Pub/Sub để các
instance đồng bộ được với nhau (driver connect vào instance A, customer
connect vào instance B vẫn phải nhận được message của nhau).
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# trip_id -> danh sách các WebSocket đang theo dõi (khách + tài xế)
_rooms: dict[str, list[WebSocket]] = {}


@router.websocket("/ws/trips/{trip_id}/track")
async def track_trip(websocket: WebSocket, trip_id: str) -> None:
    await websocket.accept()
    _rooms.setdefault(trip_id, []).append(websocket)

    try:
        while True:
            # Tin nhắn gửi lên: vị trí tài xế {"lat":..,"lng":..} hoặc ping giữ kết nối
            data = await websocket.receive_json()
            await _broadcast(trip_id, data, exclude=websocket)
    except WebSocketDisconnect:
        _rooms[trip_id].remove(websocket)
        if not _rooms[trip_id]:
            del _rooms[trip_id]


async def _broadcast(trip_id: str, message: dict, exclude: WebSocket | None = None) -> None:
    for ws in _rooms.get(trip_id, []):
        if ws is not exclude:
            await ws.send_json(message)
