# Kết quả smoke test — 03/09/2026

Chạy trên nhánh `chore/p0-foundation`, commit `ef159a1`.
Môi trường: Python 3.10, Redis 6.2.14, SQLite (chế độ dev), uvicorn.

**Kết quả: 22/22 bước đạt.** Lệnh tái hiện: `make -C services/api smoke`

| # | Bước | Kết quả |
|---|---|---|
| 1 | `GET /health` — liveness, không chạm DB | `{"status":"ok"}`, không có trường `database` |
| 2 | Có `X-Request-ID` để truy vết | `f4191fa21aa442d6` |
| 3 | `GET /ready` — kiểm DB + Redis | `{"database":"ok","redis":"ok","ready":true}` |
| 4 | Khách đăng nhập SĐT + OTP | 0901000001 |
| 5 | Tài xế đăng nhập | 0902000001 |
| 6 | `POST /pricing/estimate` | normal · 7,53km · 18 phút · cước 189.600đ |
| 7 | Tài xế lên ca, sinh QR động | `OZAcKmrWT9_rJAswxe…` |
| 8 | `POST /trips` lần 1 | trạng thái `matching`, ước tính 189.600đ |
| 9 | `POST /trips` lần 2 cùng Idempotency-Key | `Idempotent-Replay: true`, cùng trip id |
| 10 | Tài xế nhận chuyến | → `driver_arriving` |
| 11 | Quét QR **sai** | HTTP 403 — bị từ chối |
| 12 | Quét QR **đúng** | → `in_progress` |
| 13 | Ghi 5 điểm GPS | 5/5 |
| 14 | `POST /trips/{id}/complete` | → `completed` |
| 15 | `GET /drivers/me/wallet` | chờ về 72.619đ · khả dụng 0đ |
| 16 | `GET /drivers/me/escrow` | 12.815đ / 3.000.000đ · `accumulating` |
| 17 | Refresh token lần đầu | cấp token mới |
| 18 | Dùng lại token cũ | HTTP 401 — thu hồi cả họ |
| 19 | Token hợp lệ sau đó | HTTP 401 — buộc đăng nhập lại |
| 20 | Spam `/auth/request-otp` | `[200,200,200,429,429,429,429]` |
| 21 | Ghi audit log | 17 bản ghi cho các thao tác GHI |
| 22 | Che OTP trong audit | `{"phone":"0901000001","otp":"***",…}` |

## Chốt tiền một chuyến thật

| Khoản | Số tiền |
|---|---:|
| Quãng đường thực tế (từ GPS) | 5,84 km |
| **Cước cuối** | **147.300đ** |
| Tài xế được chia (58%) | 85.434đ |
| Trích ký quỹ 15% | −12.815đ |
| **Tài xế thực nhận** | **72.619đ** |
| Nền tảng giữ (38%) | 55.974đ |
| ├ phí bảo hiểm | 8.838đ |
| └ phí cổng thanh toán | 2.946đ |
| Phát hiện chạy vòng | Không |

Toàn bộ bút toán nằm trong một transaction; ví tài xế và ký quỹ khớp với số liệu trả về.

## Hai điểm QA ghi nhận trong lúc chạy

### 1. Hạn mức OTP tính theo địa chỉ IP — cần thêm hạn mức theo số điện thoại

Quan sát: hạn mức 5 lượt/5 phút áp cho **một IP**, không phải một số điện thoại. Trong kịch bản
này hai lượt đăng nhập ban đầu đã tiêu mất quota, nên lần thứ 4 của vòng lặp đã bị chặn.

Vì sao đáng lo ở Việt Nam: nhà mạng di động dùng NAT quy mô lớn, hàng nghìn thuê bao chia sẻ
vài IP công cộng. Một quán cà phê hay một toà văn phòng cũng chỉ có một IP. Với hạn mức hiện
tại, người dùng thật sẽ bị chặn nhầm.

Đề xuất: giữ hạn mức theo IP (chống quét hàng loạt) nhưng nới rộng, và thêm hạn mức chặt theo
**số điện thoại** (vd 3 lượt/5 phút cho mỗi số) — đó mới là thứ trực tiếp gắn với chi phí SMS.

Mức độ: **Major** · Chưa có mã PRD → đề xuất thêm `PRD-SEC-10`.

### 2. Quãng đường ước tính và quãng đường thực tế lệch nhau — đúng thiết kế, nhưng cần biết khi test tay

Ước tính 7,53km (đường chim bay × hệ số đường bộ 1,3) nhưng chốt 5,84km (tổng khoảng cách giữa
5 điểm GPS). Không phải lỗi: đây đúng là "ước tính bằng Maps, chốt bằng GPS thật" theo thiết kế.
Nhưng khi tích hợp Directions API thật, QA phải kiểm lại rằng hai con số hội tụ, nếu không khách
sẽ khiếu nại vì cước cuối khác báo giá.

Mức độ: **Minor** (ghi chú kiểm thử) · Liên quan `PRD-TRIP-03`.
