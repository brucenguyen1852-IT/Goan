"""Quản lý WS connection theo user_id + cầu nối Redis pub/sub giữa các worker (SPEC 6.1).

Mỗi process giữ map user_id -> set[WebSocket] của riêng nó; message gửi cho user ở process khác
được publish qua Redis channel `user:{user_id}:events` và fan-out bởi listener của process đó.
Nhờ vậy matching service hoàn toàn stateless per-worker, scale ngang được (SPEC 11).
"""

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.core.logging import log_event
from app.redis_client import USER_EVENTS_CHANNEL, get_redis

logger = logging.getLogger("goan.ws")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._listener_task: asyncio.Task | None = None
        self._pubsub = None
        self._lock = asyncio.Lock()

    async def connect(self, user_id: uuid.UUID | str, websocket: WebSocket) -> None:
        await websocket.accept()
        key = str(user_id)
        async with self._lock:
            self._connections[key].add(websocket)
            await self._subscribe(key)
        log_event(logger, "ws_connected", user_id=key)

    async def disconnect(self, user_id: uuid.UUID | str, websocket: WebSocket) -> None:
        key = str(user_id)
        async with self._lock:
            self._connections[key].discard(websocket)
            if not self._connections[key]:
                self._connections.pop(key, None)
                if self._pubsub is not None:
                    await self._pubsub.unsubscribe(USER_EVENTS_CHANNEL.format(user_id=key))
        log_event(logger, "ws_disconnected", user_id=key)

    async def _subscribe(self, key: str) -> None:
        if self._pubsub is None:
            self._pubsub = get_redis().pubsub()
        await self._pubsub.subscribe(USER_EVENTS_CHANNEL.format(user_id=key))
        if self._listener_task is None or self._listener_task.done():
            self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if message.get("type") != "message":
                    continue
                channel = message["channel"]
                user_id = channel.split(":")[1]
                try:
                    payload = json.loads(message["data"])
                except (TypeError, ValueError):
                    continue
                await self._send_local(user_id, payload)
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise
        except Exception:  # pragma: no cover - listener phải tự hồi phục
            logger.exception("ws pubsub listener error")

    async def _send_local(self, user_id: str, payload: dict[str, Any]) -> int:
        sent = 0
        for ws in list(self._connections.get(user_id, ())):
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                self._connections.get(user_id, set()).discard(ws)
        return sent

    async def send_to_user(self, user_id: uuid.UUID | str, payload: dict[str, Any]) -> None:
        """Gửi trực tiếp nếu user đang nối vào process này, ngược lại publish qua Redis."""
        key = str(user_id)
        if await self._send_local(key, payload):
            return
        await get_redis().publish(
            USER_EVENTS_CHANNEL.format(user_id=key), json.dumps(payload, default=str)
        )

    async def broadcast(self, user_ids: list[uuid.UUID | str], payload: dict[str, Any]) -> None:
        await asyncio.gather(*(self.send_to_user(uid, payload) for uid in user_ids))

    async def shutdown(self) -> None:
        if self._listener_task is not None:
            self._listener_task.cancel()
        if self._pubsub is not None:
            await self._pubsub.close()


manager = ConnectionManager()
