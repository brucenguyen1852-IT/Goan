#!/bin/sh
# Khôi phục từ bản sao lưu (P0-18).
#
# Bản sao lưu chưa từng khôi phục thử KHÔNG phải là bản sao lưu. Chạy bài này ít nhất mỗi quý,
# vào một cơ sở dữ liệu tạm, rồi so số dư ký quỹ với báo cáo đối soát cùng ngày.
#
# Chạy: restore.sh <file.dump> [tên-db-đích]
set -eu

FILE="${1:?Cú pháp: restore.sh <file.dump> [tên-db-đích]}"
TARGET="${2:-goan_restore_test}"

: "${PGHOST:=postgres}"
: "${PGUSER:=goan}"
export PGHOST PGUSER

echo "Khôi phục $FILE vào cơ sở dữ liệu '$TARGET'…"
dropdb --if-exists "$TARGET"
createdb "$TARGET"
pg_restore -d "$TARGET" --no-owner --no-privileges "$FILE"

echo
echo "Kiểm tra nhanh — những bảng mất đi là mất tiền thật:"
psql -d "$TARGET" -c "
  SELECT 'users' AS bang, count(*) FROM users
  UNION ALL SELECT 'trips', count(*) FROM trips
  UNION ALL SELECT 'escrow_transactions', count(*) FROM escrow_transactions
  UNION ALL SELECT 'wallet_transactions', count(*) FROM wallet_transactions
  UNION ALL SELECT 'audit_logs', count(*) FROM audit_logs;"
