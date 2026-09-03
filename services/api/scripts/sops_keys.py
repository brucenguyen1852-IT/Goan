"""Thêm khoá công khai age vào .sops.yaml (P0-11).

Tách ra thành script vì sửa YAML bằng sed rất dễ hỏng, mà hỏng .sops.yaml thì cả đội không
giải mã được gì cho tới khi có người sửa tay.

    python scripts/sops_keys.py add age1...
    python scripts/sops_keys.py list
"""

import re
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[3] / ".sops.yaml"
AGE_LINE = re.compile(r'^(\s*age:\s*)"?([^"\n]*)"?\s*$')
AGE_KEY = re.compile(r"^age1[0-9a-z]{58}$")


def _read() -> list[str]:
    return CONFIG.read_text(encoding="utf-8").splitlines()


def current_keys() -> list[str]:
    for line in _read():
        m = AGE_LINE.match(line)
        if m:
            return [k for k in (x.strip() for x in m.group(2).split(",")) if k]
    return []


def add(key: str) -> int:
    if not AGE_KEY.match(key):
        print(f"Khoá không đúng dạng age công khai: {key}")
        return 1
    keys = current_keys()
    if key in keys:
        print("Khoá đã có trong .sops.yaml, không thêm lại.")
        return 0
    keys.append(key)

    lines = _read()
    for i, line in enumerate(lines):
        m = AGE_LINE.match(line)
        if m:
            lines[i] = f'{m.group(1)}"{",".join(keys)}"'
            break
    else:
        print("Không tìm thấy dòng `age:` trong .sops.yaml")
        return 1
    CONFIG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Đã thêm khoá. Tổng cộng {len(keys)} khoá giải mã được.")
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "add":
        return add(sys.argv[2])
    if len(sys.argv) >= 2 and sys.argv[1] == "list":
        for key in current_keys():
            print(key)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
