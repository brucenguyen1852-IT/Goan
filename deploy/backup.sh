#!/bin/sh
# Sao lưu PostgreSQL hằng ngày (P0-18).
#
# Vì sao bắt buộc: bảng escrow_transactions là TIỀN CỦA TÀI XẾ. Mất nó không chỉ là mất dữ liệu
# mà là không chứng minh được mình còn nợ ai bao nhiêu — tranh chấp pháp lý, không phải sự cố
# kỹ thuật.
#
# Hai lớp:
#   1. Bản dump đầy đủ mỗi ngày (file này) — khôi phục về thời điểm chạy dump.
#   2. WAL archiving liên tục (bật trong docker-compose.prod.yml) — khôi phục về BẤT KỲ thời
#      điểm nào giữa hai lần dump. Chỉ có (1) thì mọi chuyến phát sinh trong ngày là mất trắng.
#
# Chạy: backup.sh [thư-mục-đích]
set -eu

BACKUP_DIR="${1:-/backup}"
KEEP_DAYS="${GOAN_BACKUP_KEEP_DAYS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$BACKUP_DIR/goan-$STAMP.dump"

: "${PGHOST:=postgres}"
: "${PGUSER:=goan}"
: "${PGDATABASE:=goan}"
export PGHOST PGUSER PGDATABASE

mkdir -p "$BACKUP_DIR"

# Định dạng custom (-Fc): nén sẵn, và pg_restore chọn được từng bảng khi cần khôi phục một phần.
pg_dump -Fc -f "$FILE"

# Kiểm chứng ngay tại chỗ: một bản sao lưu chưa từng được đọc thử thì chưa phải bản sao lưu.
if ! pg_restore --list "$FILE" > /dev/null 2>&1; then
	echo "LỖI: bản dump vừa tạo không đọc được — $FILE" >&2
	rm -f "$FILE"
	exit 1
fi

SIZE=$(wc -c < "$FILE")
if [ "$SIZE" -lt 10000 ]; then
	echo "LỖI: bản dump chỉ $SIZE byte, gần như chắc chắn là hỏng" >&2
	exit 1
fi

# Dọn bản cũ. Giữ 30 ngày: đủ để phát hiện một lỗi âm thầm làm hỏng dữ liệu từ mấy tuần trước.
find "$BACKUP_DIR" -name 'goan-*.dump' -mtime "+$KEEP_DAYS" -delete

echo "Đã sao lưu: $FILE ($SIZE byte). Còn giữ $(find "$BACKUP_DIR" -name 'goan-*.dump' | wc -l) bản."
