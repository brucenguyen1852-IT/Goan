# Triển khai staging / production

Mọi thứ trong thư mục này đã chạy được, **trừ bản thân máy chủ**. Có VPS là chạy đúng các lệnh
dưới đây, không phải nghĩ thêm gì.

## Cần chuẩn bị

| Thứ | Ghi chú |
|---|---|
| VPS Ubuntu 22.04+, tối thiểu 2 vCPU / 4GB | Docker + Docker Compose plugin |
| Tên miền trỏ A record về IP máy chủ | Caddy tự xin chứng chỉ Let's Encrypt, không cần làm gì thêm |
| Khoá age của người deploy | `make -C services/api secrets-init` trên máy đó |

## Dựng lần đầu

```bash
git clone <repo> goan && cd goan/deploy

# 1. Secret: giải mã bản đã mã hoá trong repo ra .env
cd ../services/api && make secrets-decrypt ENV=staging && cd ../../deploy

# 2. Tên miền
export GOAN_DOMAIN=staging.goan.vn

# 3. Lên
docker compose -f docker-compose.prod.yml up -d --build

# 4. Nạp danh mục quyền + tài khoản nội bộ đầu tiên
docker compose -f docker-compose.prod.yml exec api python -m scripts.seed_iam admin@goan.vn "Tên"
```

`api` tự chạy `alembic upgrade head` trước khi phục vụ, nên không có bước migrate riêng để quên.

## Kiểm chứng sau khi lên

```bash
curl https://$GOAN_DOMAIN/health     # {"status":"ok"}
curl https://$GOAN_DOMAIN/ready      # database ok, redis ok
docker compose -f docker-compose.prod.yml exec api make smoke   # 22/22
docker compose -f docker-compose.prod.yml exec api make audit   # 76/76
```

## Vì sao `beat` chạy riêng khỏi `worker`

Gộp chung rồi scale worker lên 2 là mỗi job định kỳ chạy hai lần. Với `daily_reconciliation` và
`process_escrow_refunds` thì đó là tiền thật bị chi hai lượt. Beat luôn đúng một bản.

## Sao lưu và khôi phục (P0-18)

Hai lớp, cần cả hai:

| Lớp | Cơ chế | Khôi phục về |
|---|---|---|
| Dump hằng ngày | `backup.sh` chạy trong service `backup` | Thời điểm chạy dump |
| WAL archiving | Postgres `archive_mode=on`, ghi vào volume `wal_archive` | **Bất kỳ thời điểm nào** giữa hai lần dump |

Chỉ có lớp 1 thì mọi chuyến phát sinh trong ngày là mất trắng — bảng `escrow_transactions` là
tiền của tài xế, mất nó là không chứng minh được mình còn nợ ai bao nhiêu.

`backup.sh` tự kiểm bản dump vừa tạo bằng `pg_restore --list` và chặn file quá nhỏ: một bản sao
lưu chưa từng được đọc thử thì chưa phải bản sao lưu.

### Diễn tập khôi phục — mỗi quý một lần

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  sh /backup/../restore.sh /backup/goan-<ngày>.dump goan_restore_test
```

Script in ra số dòng của 5 bảng quan trọng nhất. So số dư ký quỹ trong bản khôi phục với báo
cáo đối soát cùng ngày; lệch là bản sao lưu có vấn đề, và biết sớm ba tháng còn hơn biết lúc
cần dùng thật.

Bài này **đã chạy thật** trong quá trình phát triển: sao lưu rồi khôi phục sang cơ sở dữ liệu
khác, đủ 7 người dùng, 7 chuyến, 5 bút toán ký quỹ, 5 giao dịch ví và 114 dòng audit.

### Khôi phục về một thời điểm (PITR)

```bash
# Dừng api/worker/beat, giữ postgres
docker compose -f docker-compose.prod.yml stop api worker beat

# Khôi phục bản dump gần nhất TRƯỚC thời điểm sự cố, rồi phát lại WAL tới đúng giây cần
# recovery_target_time = '2026-09-03 14:23:00+07'
```

Chi tiết lệnh phụ thuộc phiên bản Postgres đang chạy; giữ mục này ngắn có chủ đích, vì viết dài
mà không diễn tập thì lúc sự cố vẫn không ai dám gõ. Diễn tập quý là thứ làm nó thật.

## Cập nhật phiên bản

```bash
git pull && docker compose -f docker-compose.prod.yml up -d --build api worker beat
```

Migration chạy tự động khi `api` khởi động. Migration nào cũng phải `downgrade` được (quy ước
trong CLAUDE.md), nên quay lui là đổi lại tag rồi dựng lại.
