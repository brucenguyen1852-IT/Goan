# Merge Request: `chore/p0-foundation` → `main`

**Tiêu đề đề xuất:** `P0 — Dựng nền monorepo, siết bảo mật backend và thiết lập vai trò QA`

**4 commit · 239 file · +6.867 / −198 dòng**

---

## Thay đổi gì

Giai đoạn P0 theo `docs/GoAn_Phan_Dinh_He_Thong_va_Kien_Truc_Production.md`: dọn lại cấu trúc
repo thành monorepo một backend, dựng cổng chất lượng tự động, siết bốn điểm bảo mật ở backend,
và thiết lập vai trò QA như một vai trò có quyền hạn thay vì "người test cuối cùng".

Không có thay đổi nào ở logic nghiệp vụ (cước, ký quỹ, chống gian lận, ghép chuyến).

| Commit | Nội dung |
|---|---|
| `cc30b41` | Monorepo, contract API sinh tự động, ruff/mypy, CI |
| `ea79c35` | mypy sạch toàn bộ (sửa 3 bug tiềm ẩn), pnpm workspace, CI hết ngoại lệ |
| `ce4f2ee` | Cập nhật bảng theo dõi dự án |
| `399d8ab` | Audit log, xoay vòng refresh token, idempotency, truy vết, vai trò QA |

## Ánh xạ PRD

- **PRD-SEC-01** access token ngắn hạn · **PRD-SEC-02** xoay vòng refresh token
- **PRD-SEC-03** hạn mức riêng cho OTP · **PRD-SEC-04** không ghi PII vào log
- **PRD-SEC-05** mã hoá CCCD at-rest · **PRD-SEC-06** đăng xuất theo thiết bị
- **PRD-PAY-07** idempotency · **PRD-OPS-01** dấu vết thao tác · **PRD-OPS-02** mã truy vết
- **PRD-OPS-03** tách liveness/readiness · **PRD-MATCH-01…04** ghép chuyến

Chi tiết: `docs/QA/TRACEABILITY.md`

## Kiểm thử

| Câu hỏi | Trả lời |
|---|---|
| Test mới nằm ở đâu? | `services/api/tests/core/` (4 file mới), `tests/domains/test_auth_tokens.py`, `tests/domains/test_matching.py` |
| **Test này đỏ khi nào?** | Xem bảng dưới |
| Có test cho đường đi sai không? | Có — 52 test mang marker `security`, phần lớn là đường đi sai |
| Đã cập nhật TRACEABILITY chưa? | Rồi, 58 yêu cầu, 38 đã có test (66%) |

**Vài test đáng chú ý và điều kiện làm chúng đỏ:**

| Test | Đỏ khi |
|---|---|
| `test_dung_lai_token_cu_thi_thu_hoi_ca_ho` | Refresh token bị lộ vẫn dùng được sau khi nạn nhân đã refresh |
| `test_token_cu_khong_co_fam_van_dung_duoc_mot_lan` | Bản deploy này đá toàn bộ người dùng đang đăng nhập ra ngoài |
| `test_gui_trung_thi_phat_lai_ket_qua_cu` | Bấm hai lần lúc mất sóng tạo hai giao dịch |
| `test_chan_khi_vuot_han_muc_otp` | Kẻ xấu đốt được ngân sách SMS bằng cách gọi liên tục |
| `test_middleware_tu_ghi_audit_cho_request_ghi` | Lập trình viên quên gọi audit ở endpoint mới |
| `test_che_moi_truong_nhay_cam` | OTP hoặc số CCCD lọt vào bảng audit |
| `test_chi_mot_tai_xe_thang_khi_cung_nhan` | Hai tài xế cùng chạy tới một điểm đón |
| `test_noi_dan_ban_kinh_khi_khong_co_ai_o_gan` | Chỉ tìm một vòng 5km, khách ở vùng thưa không đặt được xe |
| `test_health_khong_cham_db` | Sự cố DB làm orchestrator restart container hàng loạt |

**Kết quả chạy đầy đủ:**

```
ruff check app tests alembic     All checks passed!
ruff format --check              105 files already formatted
mypy app                         Success: no issues found in 85 source files
pytest                           129 passed
pytest -m money                  16 passed
pytest -m security               52 passed
coverage                         81.01%  (ngưỡng CI: 75%)
pnpm --filter @goan/api-client   typecheck OK
```

## Checklist

- [x] `make check` xanh
- [x] Test cho đường đi đúng và đường đi sai
- [x] Đổi DB có migration (`0002_audit_logs`) và `downgrade` chạy được
- [x] Đổi API đã sinh lại `openapi.json` (34 đường dẫn, thêm `/auth/logout`)
- [x] Độ phủ tăng 78% → 81%
- [x] Chạm tiền/quyền có marker `money` / `security`
- [x] Log có `request_id` và tên event
- [x] Không có secret, token hay số CCCD trong code, log hay test

## Thay đổi phá vỡ tương thích

| Thay đổi | Ảnh hưởng | Xử lý |
|---|---|---|
| Access token 60 → 15 phút | `apps/customer-web` gặp 401 là đăng xuất luôn thay vì tự refresh | Chấp nhận tạm: app này đang gọi sai toàn bộ endpoint nên chưa dùng được. Sửa dứt điểm ở task P4-12 |
| Refresh token có thêm `fam` | Không gãy — token cũ được nâng cấp một lần, có test bảo vệ (`QA-AUTH-06`) | Không cần làm gì |
| Đường dẫn thư mục đổi | Mọi script CI/deploy trỏ `goan-backend-spec/` đều hỏng | Chưa có deploy tự động nên chưa ảnh hưởng |

**Thứ tự triển khai:** chạy `alembic upgrade head` trước khi khởi động bản mới (bảng `audit_logs`).

## Rủi ro và cách quay lui

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Middleware audit đọc body request có thể làm hỏng handler phía sau | Trung bình | Đã phát lại body qua `_receive`; 15 test tầng `api` đi qua đúng chuỗi middleware thật |
| Ba middleware mới làm tăng độ trễ | Thấp | Audit ghi bằng session riêng; idempotency chỉ chạm 5 nhóm endpoint |
| Redis chết làm mất khử trùng và mất phát hiện tái sử dụng token | Đã chấp nhận | Fail-open có chủ ý, ghi log WARNING, có test `QA-AUTH-07` và `QA-IDM-07`. Lý do trong `app/domains/auth/tokens.py` |
| Thu hồi cả họ token có thể đá nhầm người dùng thật | Thấp | Đúng thiết kế OAuth BCP. Người dùng thật đăng nhập lại bằng OTP; kẻ tấn công không có SIM |

**Quay lui:** revert 4 commit. Bảng `audit_logs` để lại không sao (không có gì đọc nó);
muốn sạch thì `alembic downgrade 0001`.

## Chưa nằm trong MR này

Vẫn thuộc P0, chưa làm: dựng staging, quản lý secret, backup PITR, OpenTelemetry và
Prometheus (mới có hook Sentry), và xoá hẳn `services/_deprecated-api-v0` (chờ P4-12).

---

**QA ký duyệt:** _(chờ)_
