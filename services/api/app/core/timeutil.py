"""Chuẩn hoá timestamp về UTC aware.

Postgres (timestamptz) trả về datetime có tzinfo, nhưng SQLite (dev/test) trả về naive.
Mọi phép trừ thời gian trong service phải đi qua `ensure_utc` để không phụ thuộc backend DB.

Hai overload để type checker biết: đưa vào datetime thì luôn nhận lại datetime (không phải
`datetime | None`), nhờ đó các phép trừ thời gian ở service không còn bị báo lỗi kiểu giả.
"""

from datetime import datetime, timezone
from typing import overload


@overload
def ensure_utc(dt: datetime) -> datetime: ...


@overload
def ensure_utc(dt: None) -> None: ...


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
