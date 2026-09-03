# Kết quả chạy thật trên PostgreSQL — 03/09/2026

Lần đầu toàn bộ hệ thống chạy trên đúng bộ hạ tầng của production: PostgreSQL 16 + PostGIS +
Redis + Celery worker kèm beat + uvicorn. Trước đây mọi thứ chỉ được chạy trên SQLite.

| Bài | Kết quả |
|---|---|
| `alembic upgrade head` | 8/8 migration sạch |
| `alembic check` | "No new upgrade operations detected" |
| `alembic downgrade base` rồi upgrade lại | sạch cả hai chiều |
| `python -m scripts.seed` | 2 rider, 3 driver, 2 partner, 1 satellite zone, 3 pricing rule |
| `GET /health` | `{"status":"ok"}` |
| `GET /ready` | `{"database":"ok","redis":"ok","ready":true}` |
| Celery worker + beat | `celery@vm ready`, beat lên lịch được |
| `make smoke` | **22/22 bước đạt** |
| `make audit` | **76/76 lời gọi đúng như mong đợi** |

## Lỗi nghiêm trọng phát hiện nhờ lần chạy này

**Mọi cột enum ghi sai giá trị trên PostgreSQL.** SQLAlchemy mặc định lưu TÊN thành viên
(`RIDER`), trong khi kiểu enum do migration tạo ra chỉ nhận GIÁ TRỊ viết thường (`rider`).

- Trên SQLite không ai thấy: cả ghi lẫn đọc đều dùng tên, nên 277 test vẫn xanh.
- Trên PostgreSQL thì **không tạo nổi một người dùng**: `invalid input value for enum
  user_role: "RIDER"`. Nghĩa là bản deploy đầu tiên lên staging sẽ chết ngay ở bước seed.
- Đã sửa: thêm `core/model_base.pg_enum()` và đưa cả 23 cột enum đi qua đó.

Bài học ghi lại cho lần sau: **test xanh trên SQLite không chứng minh được gì về PostgreSQL.**
Job `migration-check` của CI có Postgres thật nhưng chỉ chạy migration, không ghi dữ liệu — nên
nó cũng không bắt được lỗi này. Cách bắt được là chạy `make smoke` trên Postgres, và từ nay đó
là việc bắt buộc trước mỗi lần phát hành (`docs/QA/QA_ROLE.md` §7).

## Hai chỗ smoke test tự nó phải sửa để chạy được trên Postgres

1. Bước đọc audit log trước đây mở thẳng file SQLite, nên chạy trên staging là ngã ở đúng bước
   cuối. Nay chọn cách đọc theo `DATABASE_URL` (asyncpg cho Postgres, sqlite3 cho dev).
2. Script không thấy gói `app` khi gọi bằng `python scripts/smoke_e2e.py`, nên âm thầm quay về
   SQLite. Nay tự thêm thư mục cha vào `sys.path`.

## Lưu ý khi chạy lại

Hạn mức OTP và rate limit nằm ở Redis và sống qua các lần chạy. Chạy `make smoke` hai lần liên
tiếp trong 5 phút thì lần sau sẽ nhận 429 ở bước đăng nhập. Dọn bằng `redis-cli flushdb` trước
khi chạy lại.

## Cách dựng lại môi trường này

Không có Docker daemon trong phiên làm việc nên `docker compose up` chưa chạy được; thay vào đó
dựng đúng bộ dịch vụ đó bằng tiến trình thật:

```bash
redis-server --daemonize yes --port 6379
pg_ctlcluster 16 main start                       # hoặc docker compose up -d postgres redis
cd services/api && cp .env.example .env
sed -i 's|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://goan:goan@127.0.0.1:5432/goan|' .env
alembic upgrade head && python -m scripts.seed && python -m scripts.seed_iam
uvicorn app.main:app --port 8000 &
celery -A app.workers.celery_app.celery_app worker -B --loglevel=info &
make smoke && make audit
```
