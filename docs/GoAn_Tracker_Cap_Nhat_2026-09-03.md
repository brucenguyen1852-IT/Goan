# Cập nhật tracker — 03/09/2026

`docs/GoAn_Project_Tracker.xlsx` trong repo đã được sửa theo đúng bảng dưới. **Bản trên Google
Drive thì chưa** — phiên làm việc chạy trong máy ảo không mở được `docs.google.com`. Ai giữ bản
Drive thì chép tay theo bảng này, hoặc tải bản trong repo lên đè.

Dashboard tự tính lại từ sheet Backlog nên không cần sửa; chỉ cần mở file một lần là số mới hiện ra.

## Vì sao phải cập nhật

Tracker chốt số liệu ở commit `ef159a1`. Sau đó có 4 commit chưa được ghi nhận, nên Dashboard
đang báo thấp hơn thực tế:

| Commit | Việc |
|---|---|
| `c420f6d` | Smoke test đầu-cuối 22 bước, chạy thật 22/22 |
| `49f623b` | Viết lại tầng API app khách, chạy thật với backend |
| `80567bb` | Rà soát ngang toàn bộ API trên Swagger — sửa 4 lỗi, 62/62 lời gọi đạt |
| `a03e93a` | Hoàn thiện vòng đời chuyến: dấu vết `trip_events`, mốc tới nơi, đánh giá, điều phối thủ công |

## Sheet Backlog — cột K (Trạng thái), L (%), O (Ghi chú)

| ID | Cũ | Mới | Căn cứ |
|---|---|---|---|
| P0-01 | Đang làm 70% | *giữ nguyên*, đổi ghi chú | Điều kiện xoá đã đạt (P4-12 xong). Chỉ còn thao tác xoá thư mục |
| P0-07 | Đang làm 85% | *giữ nguyên*, đổi ghi chú | CI 4 job xanh. Phần còn lại là bật branch protection trên giao diện GitHub |
| P0-08 | Đang làm 85% | **Đã xong 100%** | Job `migration-check` chạy `alembic upgrade head` + `alembic check` trên postgis:16-3.4 |
| P0-09 | Đang làm 70% | **Đang làm 90%** | Compose đủ 4 dịch vụ, `docker compose config` hợp lệ. Còn chạy `up` kiểm chứng |
| P0-16 | Đang làm 40% | **Đang làm 80%** | Xong phần mã: `/metrics` Prometheus + OTel trace + Sentry, 9 test. Còn collector và alert Slack trên staging |
| P4-11 | Chưa bắt đầu | **Đang làm 50%** | Đã có `GET /trips`, `/rate`, `/arrived`, `/events`. Còn tách router `/rider/*` (phụ thuộc P1-08) |
| P4-12 | Chưa bắt đầu | **Đã xong 100%** | 9/9 đường dẫn app khách khớp `openapi.json`; rà soát 62/62 lời gọi đạt |
| P4-13 | Chưa bắt đầu | **Đang làm 40%** | `make smoke` 22/22 trên server thật. DoD đòi 10 chuyến trên staging nên chưa đóng được |

## Sheet Hiện trạng — cột B, C, D, E

| Thành phần | Cũ | Mới |
|---|---|---|
| Backend - Vòng đời chuyến | Gần xong 90% | **Đã xong 100%** — thêm `trip_events`, `/arrived`, `/rate`, `/ops/trips/{id}/assign-driver` |
| Backend - Matching | Gần xong 85% | **Gần xong 95%** — gán thủ công từ ops đã có; còn trợ cấp vùng mới |
| Backend - Auth | Một nửa 60% | **Gần xong 85%** — xoay vòng refresh token + thu hồi phiên đã xong; còn 2FA nội bộ (P1) |
| App khách | Phải làm lại 15% | **Một nửa 60%** — chạy thật với backend; còn bản đồ, thanh toán, SOS |
| Hạ tầng CI/CD, staging | Chưa có 0% | **Một nửa 30%** — CI 4 job xanh; staging/secret/backup vẫn trống |
| Kiểm thử tự động | Một nửa 40% | **Một nửa 70%** — 192 test, độ phủ 81,5%, thêm smoke và audit chạy trên server thật |

## Sheet Nhật ký — 5 dòng cần thêm

Chèn phía trên khối "ĐÁNH GIÁ BAN ĐẦU ĐÃ ĐƯỢC SỬA LẠI".

| Ngày | Commit | Hạng mục | Đã làm gì | Bằng chứng kiểm chứng |
|---|---|---|---|---|
| 03/09/2026 | `c420f6d` | QA | `scripts/smoke_e2e.py`: 22 bước đầu-cuối trên uvicorn + Redis + DB thật, thứ mà test in-process không thấy | Chạy thật 22/22 đạt, kết quả lưu ở `docs/QA/SMOKE_RESULT_2026-09-03.md` |
| 03/09/2026 | `49f623b` | Frontend | Viết lại tầng API app khách theo đúng contract backend; tự làm mới token khi 401, đúng một lần refresh tại một thời điểm | 9/9 đường dẫn khớp `openapi.json` |
| 03/09/2026 | `80567bb` | QA | `scripts/api_audit.py` quét ngang mọi endpoint theo đúng vai trò, kèm các trường hợp phải bị từ chối | 62 lời gọi trên 34 đường dẫn, sửa 4 lỗi phát hiện được |
| 03/09/2026 | `a03e93a` | Chuyến | `trip_events` ghi dấu vết vòng đời, mốc tài xế tới nơi, đánh giá chuyến, điều phối thủ công từ ops | Bổ sung test vòng đời chuyến; `alembic 0003_trip_lifecycle` |
| 03/09/2026 | *(commit này)* | Vận hành | Prometheus `/metrics` (nhãn `path` theo template route, khoá bằng `METRICS_TOKEN`) + OpenTelemetry trace tuỳ chọn | 9 test QA-MET, gồm test chặn nổ cardinality và test thiếu gói OTel thì không sập |

## Việc chưa làm được trong phiên này

| Việc | Vì sao | Ai làm |
|---|---|---|
| Xoá `services/_deprecated-api-v0` | Thao tác xoá hàng loạt bị chặn trong môi trường máy ảo | Chạy `git rm -r services/_deprecated-api-v0` trên máy |
| P0-10 staging (VPS + domain + TLS) | Cần mua VPS và tên miền | Tech Lead |
| P0-11 quản lý secret | Cần chọn SOPS hay Doppler rồi cấp khoá | Tech Lead |
| P0-18 backup PITR | Phụ thuộc P0-10 | Tech Lead |
