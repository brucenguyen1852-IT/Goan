"""Redis giả dùng cho test — đủ lệnh mà middleware và token store cần, không cần server thật.

Chỉ hiện thực đúng phần đang dùng. Thiếu lệnh nào thì AttributeError sẽ chỉ thẳng ra,
tốt hơn là im lặng trả về giá trị sai.
"""

from __future__ import annotations

import math
import time
from typing import Any


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Bản rút gọn của app.core.geo.haversine_km — cố ý viết lại độc lập.

    Nếu dùng chung hàm với code sản phẩm thì một lỗi trong hàm đó sẽ làm cả code lẫn test
    cùng sai, và test sẽ vẫn xanh.
    """
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    def zremrangebyscore(self, key: str, minimum: float, maximum: float) -> FakePipeline:
        self._ops.append(("zremrangebyscore", (key, minimum, maximum)))
        return self

    def zadd(self, key: str, mapping: dict[str, float]) -> FakePipeline:
        self._ops.append(("zadd", (key, mapping)))
        return self

    def zcard(self, key: str) -> FakePipeline:
        self._ops.append(("zcard", (key,)))
        return self

    def expire(self, key: str, ttl: int) -> FakePipeline:
        self._ops.append(("expire", (key, ttl)))
        return self

    async def execute(self) -> list[Any]:
        results = []
        for name, args in self._ops:
            results.append(await getattr(self._redis, name)(*args))
        self._ops.clear()
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.expiries: dict[str, float] = {}
        self.geo: dict[str, dict[str, tuple[float, float]]] = {}
        self.sets: dict[str, set[str]] = {}
        self.fail = False  # bật để mô phỏng Redis chết

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("Redis giả đang được đặt ở trạng thái lỗi")

    def _expired(self, key: str) -> bool:
        deadline = self.expiries.get(key)
        if deadline is not None and deadline <= time.time():
            self.store.pop(key, None)
            self.zsets.pop(key, None)
            self.expiries.pop(key, None)
            return True
        return False

    async def get(self, key: str) -> str | None:
        self._check()
        self._expired(key)
        return self.store.get(key)

    async def set(
        self, key: str, value: Any, *, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        self._check()
        self._expired(key)
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        if ex:
            self.expiries[key] = time.time() + ex
        return True

    async def delete(self, *keys: str) -> int:
        self._check()
        removed = 0
        for key in keys:
            removed += 1 if self.store.pop(key, None) is not None else 0
            self.zsets.pop(key, None)
            self.sets.pop(key, None)
            self.expiries.pop(key, None)
        return removed

    async def exists(self, key: str) -> int:
        self._check()
        self._expired(key)
        return 1 if (key in self.store or key in self.zsets or key in self.sets) else 0

    async def incr(self, key: str) -> int:
        self._check()
        value = int(self.store.get(key, "0")) + 1
        self.store[key] = str(value)
        return value

    async def expire(self, key: str, ttl: int) -> bool:
        self._check()
        self.expiries[key] = time.time() + ttl
        return True

    async def zremrangebyscore(self, key: str, minimum: float, maximum: float) -> int:
        self._check()
        members = self.zsets.setdefault(key, {})
        doomed = [m for m, score in members.items() if minimum <= score <= maximum]
        for m in doomed:
            members.pop(m)
        return len(doomed)

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self._check()
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def zcard(self, key: str) -> int:
        self._check()
        return len(self.zsets.get(key, {}))

    async def sadd(self, key: str, *members: str) -> int:
        self._check()
        current = self.sets.setdefault(key, set())
        before = len(current)
        current.update(str(m) for m in members)
        return len(current) - before

    async def sismember(self, key: str, member: str) -> bool:
        self._check()
        return str(member) in self.sets.get(key, set())

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    # --- Redis GEO (matching dùng) ---

    async def geoadd(self, key: str, values: list) -> int:
        """values dạng [lng, lat, member, lng, lat, member, ...] giống redis-py."""
        self._check()
        members = self.geo.setdefault(key, {})
        for i in range(0, len(values), 3):
            lng, lat, member = float(values[i]), float(values[i + 1]), str(values[i + 2])
            members[member] = (lng, lat)
        return len(members)

    async def geosearch(
        self,
        key: str,
        *,
        longitude: float,
        latitude: float,
        radius: float,
        unit: str = "km",
        sort: str = "ASC",
        count: int | None = None,
        withdist: bool = False,
    ) -> list:
        self._check()
        assert unit == "km", "FakeRedis chỉ hỗ trợ đơn vị km"
        found = []
        for member, (mlng, mlat) in self.geo.get(key, {}).items():
            distance = _haversine_km(latitude, longitude, mlat, mlng)
            if distance <= radius:
                found.append([member, round(distance, 4)] if withdist else member)
        if sort == "ASC" and withdist:
            found.sort(key=lambda item: item[1])
        return found[:count] if count else found

    async def ping(self) -> bool:
        self._check()
        return True
