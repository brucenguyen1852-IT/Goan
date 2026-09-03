# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

GoAn — nền tảng lái hộ (marketplace 2 phía: khách có xe, tài xế lái hộ về nhà). Monorepo
pnpm + turbo: **một** backend duy nhất phục vụ 5 sản phẩm frontend (mới có app khách).

| Thư mục | Vai trò |
|---|---|
| `services/api` | Backend FastAPI — **nguồn sự thật** của toàn hệ thống |
| `services/_deprecated-api-v0` | Bản nháp cũ. **Không sửa, không import, không đọc để tham chiếu** |
| `apps/customer-web` | Web MVP cho khách (React + Vite + Zustand + axios) |
| `packages/api-client` | Client TS sinh từ OpenAPI — contract giữa backend và mọi frontend |
| `docs/` | PRD: kiến trúc, luồng thanh toán, phân định hệ thống + `docs/QA/` |

## Lệnh

Backend chạy trong `services/api` với venv đã kích hoạt (`source .venv/bin/activate`).

| Việc | Lệnh |
|---|---|
| Cổng chất lượng trước mỗi commit | `make -C services/api check` (ruff + mypy + pytest) |
| Test | `make -C services/api test` · một file: `pytest tests/domains/test_pricing.py` · một test: `pytest tests/domains/test_pricing.py::test_ten_test` |
| Test theo nhóm | `pytest -m unit` · `-m money` · `-m security` · `-m "not api"` |
| Độ phủ | `make -C services/api cov` (CI chặn dưới 75%) |
| Sửa lint tự động | `make -C services/api fmt` |
| Dev server | `make -C services/api dev` → http://localhost:8000/docs |
| Migration | `alembic upgrade head` · `alembic check` (model lệch migration là đỏ) |
| Sinh lại contract API | `make -C services/api openapi` rồi `pnpm --filter @goan/api-client generate` (gộp: `pnpm api:client`) |
| Smoke E2E (server thật) | `make -C services/api smoke` — 22 bước, một luồng nghiệp vụ |
| Rà soát ngang API | `make -C services/api audit` — mọi endpoint, mọi vai trò, cả trường hợp phải bị từ chối |
| Frontend | `pnpm dev` · `pnpm build` · `pnpm typecheck` (turbo, từ thư mục gốc) |

Dev nhanh không cần Postgres: đặt `DATABASE_URL=sqlite+aiosqlite:///./goan_dev.db` trong `.env`,
`redis-server --daemonize yes`, rồi `python -m scripts.init_db && python -m scripts.seed`.
`smoke`/`audit` cần server đang chạy ở cửa sổ khác; `audit` cần thêm
`python -m scripts.create_admin 0900000000 "Quản trị viên"` lần đầu. `pytest` **không** cần
Postgres/Redis (SQLite in-memory + `tests/fakes.FakeRedis`).

## Kiến trúc

**Vertical slice theo domain.** `app/domains/<tên>/` gồm `router.py` (HTTP) → `service.py`
(nghiệp vụ) → `models.py` (ORM) + `schemas.py` (Pydantic). Router không chứa logic; service
không biết HTTP. Domain hiện có: `auth`, `users`, `pricing`, `trips`, `matching`, `fraud`,
`escrow`, `payments`, `partners`, `notifications`, `audit`.

**Thứ tự middleware trong `app/main.py` là ràng buộc, không phải sở thích.** Starlette chạy
ngược thứ tự `add_middleware`, nên chuỗi thực thi là
`RequestId → RateLimit → Idempotency → Audit → router`. Đổi thứ tự add sẽ làm audit log mất
status code cuối hoặc rate-limit log mất `request_id`.

**Khử trùng request là hạ tầng, không phải việc của endpoint.** `core/idempotency.py` chặn ở
middleware theo danh sách `PROTECTED_SUFFIXES` / `PROTECTED_EXACT`. Thêm endpoint tạo tiền
hoặc bản ghi không hoàn tác được thì **phải** thêm vào danh sách đó, không tự viết lại cơ chế.

**Mọi con số nghiệp vụ nằm ở `app/config.py`** (take-rate, tỷ lệ ký quỹ, ngưỡng gian lận,
phụ thu) và `app/domains/pricing/constants.py` (biểu giá). Không hardcode rải rác.

**Tiền luôn là `Decimal`, đi qua `core/money.vnd()`** (ROUND_HALF_UP về đồng nguyên). Không
dùng `float` ở bất kỳ đâu chạm tiền — có test riêng chặn việc này. Ra JSON, `Decimal` thành
**chuỗi**; frontend hiển thị bằng `formatVnd()`, không ép về `number`.

**Vòng đời chuyến là bảng transition** (`domains/trips/state_machine.py`), không phải if-else.
Ràng buộc chống đơn ma: `in_progress` chỉ đến được từ `qr_verified`. Thêm trạng thái thì sửa
bảng, và kiểm lại `SETTLED_TRIP_STATUSES` / `TERMINAL_TRIP_STATUSES` trong `core/constants.py`
— đã từng có lỗi thật: thêm `rated` làm chuyến được đánh giá biến mất khỏi báo cáo đối soát.

**Thêm ORM model thì phải import vào `app/models_registry.py`.** Alembic autogenerate và
`Base.metadata.create_all` (test, `init_db`) chỉ thấy model qua file này.

**Lỗi trả về theo một khuôn duy nhất.** Ném `AppError` con cháu (`NotFoundError`,
`PermissionDeniedError`, `ConflictError`, `FraudRejectedError`…) từ `core/exceptions.py`;
handler chuyển thành `{"error": {"code", "message", "details"}}` với thông điệp tiếng Việt.
Đừng `raise HTTPException` trực tiếp.

**Phân quyền qua dependency**, không kiểm trong thân hàm: `get_current_rider` /
`get_current_driver` / `get_current_admin` / `get_driver_profile` trong `app/deps.py`.

**Real-time**: `app/websocket/` — một endpoint `/ws?token=`, `connection_manager` fan-out qua
Redis pub/sub (nhiều instance). Vị trí tài xế nằm ở Redis GEO nên matching chạy được cả khi
DB là SQLite (dev). Job nền ở `app/workers/tasks.py` (Celery beat: nhả ví, hết hạn matching,
đối soát ngày, quét tín hiệu ngoài app, chi hoàn ký quỹ).

**Hai thế giới tài khoản tách hẳn nhau.** Khách/tài xế ở `users` (đăng nhập OTP theo SĐT);
nhân sự nội bộ ở `staff_users` (email + mật khẩu + TOTP). Token nội bộ mang `role="staff"` và
`sub` trỏ vào `staff_users`, nên không token nào dùng lẫn được. Endpoint Console dùng
`Depends(require_permission("domain:action:scope"))` — **đừng** kiểm tra tên vai trò trong code
nghiệp vụ, vai trò chỉ là tập hợp quyền lưu ở DB và sửa được từ Console. Audit của nhân sự ghi
vào `actor_staff_id` (khác khoá ngoại với `actor_id`).

**Quan sát hệ thống**: `/metrics` (Prometheus) nằm ngoài OpenAPI và ngoài cùng chuỗi middleware.
Nhãn `path` **phải** là template route — `core/metrics.route_label()` lo việc đó, đường dẫn lạ gom
vào `unmatched`; đừng gắn nhãn bằng `request.url.path`. Sentry và OpenTelemetry bật theo biến môi
trường, gói cài riêng từ `requirements-observability.txt`, thiếu gói thì cảnh báo chứ không sập.

**Contract frontend–backend sinh tự động.** Backend đổi API → chạy `make -C services/api openapi`
→ commit `packages/api-client/openapi.json` (`src/generated/` thì **không** commit). CI có job
riêng so bản sinh mới với bản đã commit, lệch là đỏ. Lý do: `apps/customer-web` từng tự đặt tên
endpoint và lệch hoàn toàn khỏi backend (`/auth/otp/request` vs `/auth/request-otp`) mà không ai
biết cho tới lúc chạy thật. Lưu ý: `apps/customer-web` **hiện vẫn gọi axios thủ công**
(`src/api/*.ts`) chứ chưa chuyển sang `@goan/api-client` — app mới thì dùng package, sửa app cũ
thì đừng thêm đường dẫn viết tay.

**Refresh token xoay vòng**: mỗi lần refresh vô hiệu token cũ, dùng lại token đã tiêu là bị thu
hồi cả phiên. Client chỉ được có đúng một lần refresh chạy tại một thời điểm — xem biến
`refreshing` trong `apps/customer-web/src/api/client.ts`, đừng bỏ.

**Phần mock chưa thay**: cổng thanh toán (`domains/payments/gateway.py`), eKYC
(`integrations/ekyc.py`), Maps (`integrations/maps.py`, Haversine × 1.3), hoá đơn VAT, SMS OTP
(in ra log khi `DEBUG=true`, response trả `debug_otp`).

## Kiểm thử

`tests/conftest.py` cho hai lối vào: fixture `db` (SQLite in-memory, dựng lại từng test) để test
service, và fixture `api_client` chạy qua **đúng chuỗi middleware thật** để bắt lỗi tầng
middleware mà test gọi thẳng hàm không thấy. Factory sẵn: `create_rider`, `create_driver`,
`create_trip`.

`--strict-markers` đang bật. Marker: `unit`, `integration`, `api`, `security`, `money`, `prd`.
Nhóm `money` **không bao giờ được đỏ** — đỏ là chặn merge ngay.

Quy ước viết test (đầy đủ ở `docs/QA/TEST_STRATEGY.md`):

- Tên test bằng tiếng Việt, mô tả **hành vi**: `test_dung_lai_token_cu_thi_thu_hoi_ca_ho`.
- Mỗi test phải trả lời được **"nó đỏ khi nào?"**. Không trả lời được thì test vô nghĩa.
- Docstring ghi **vì sao**, không ghi cái gì. Ghi mã `QA-<VÙNG>-<số>` nếu có ánh xạ PRD.
- Đường đi sai được ưu tiên ngang đường đi đúng.
- Không mock service của chính mình; chỉ mock cổng thanh toán / eKYC / SMS.

## Quy ước làm việc

- **Làm thẳng trên `main`.** Chủ dự án yêu cầu commit xong là push luôn, không mở nhánh phụ và
  không chờ merge request (03/09/2026). Ngoại lệ: khi phiên làm việc được chỉ định một nhánh cụ
  thể thì theo nhánh đó.
- Trước mỗi commit: `make -C services/api check` phải xanh.
- Đổi schema DB → có migration trong `services/api/alembic/versions/`, và `downgrade` chạy được.
- Đổi API → chạy lại `openapi` và commit `openapi.json`.
- Chạm tiền hoặc quyền → có test mang marker `money` hoặc `security`, và cập nhật
  `docs/QA/TRACEABILITY.md`.
- Không ghi PII (SĐT, CCCD, token) vào log — audit log và JSON log tự che, xem `redact()` ở `domains/audit/service.py` và `SENSITIVE_KEYS` ở `core/logging.py`.
- Trước phát hành: `make smoke` rồi `make audit`. Vai trò và quyền chặn release: `docs/QA/QA_ROLE.md`.
- Commit message, comment, docstring, tên test và thông điệp lỗi viết bằng tiếng Việt.
