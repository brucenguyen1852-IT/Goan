#!/usr/bin/env python3
"""Xuất OpenAPI schema của backend ra file JSON.

Đây là contract duy nhất giữa backend và mọi frontend. CI so file sinh ra với file đã commit;
lệch nhau nghĩa là ai đó đổi API mà chưa sinh lại client.

    python scripts/export_openapi.py ../../packages/api-client/openapi.json
"""

import json
import os
import pathlib
import sys

# Dùng SQLite để import app không cần Postgres.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./_openapi_tmp.db")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402


def main() -> int:
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    out.write_text(json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                   encoding="utf-8")
    paths = len(schema.get("paths", {}))
    print(f"Đã ghi {out} — {paths} đường dẫn")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
