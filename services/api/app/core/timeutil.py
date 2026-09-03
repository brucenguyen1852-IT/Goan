"""Chuẩn hoá timestamp về UTC aware.

Postgres (timestamptz) trả về datetime có tzinfo, nhưng SQLite (dev/test) trả về naive.
Mọi phép trừ thời gian trong service phải đi qua `ensure_utc` để không phụ thuộc backend DB.
"""

from datetime import datetime, timezone


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
