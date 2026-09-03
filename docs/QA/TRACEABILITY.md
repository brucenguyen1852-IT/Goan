# Ma trận truy vết PRD → Test

> Mỗi yêu cầu trong PRD phải chỉ ra được **bài test nào chứng minh nó hoạt động**.
> Ô "Test" trống nghĩa là yêu cầu đó chưa được bảo vệ — không phải là nó không quan trọng.
>
> PRD ở đây gồm 3 tài liệu trong `docs/`: kiến trúc kỹ thuật, thiết kế luồng thanh toán,
> và phân định hệ thống.
>
> Cập nhật: 03/09/2026 · **129 test tự động, độ phủ 81%**

## Quy ước mã

- `PRD-<VÙNG>-<số>` — một yêu cầu kiểm chứng được, trích từ tài liệu.
- `QA-<VÙNG>-<số>` — một test case. Ghi trong docstring của test tương ứng.
- Vùng: `PAY` thanh toán · `SEC` bảo mật · `TRIP` chuyến đi · `FRD` gian lận · `ESC` ký quỹ ·
  `MATCH` ghép chuyến · `OPS` vận hành · `CHAT` hội thoại

---

## A. Định giá & Thanh toán

| PRD | Yêu cầu | Nguồn | Test | Trạng thái |
|---|---|---|---|---|
| PRD-PAY-01 | Cước = phí nền + đơn giá/km × km + đơn giá/phút × phút + phụ thu đón xa | Kiến trúc §3.4 | `test_pricing.py` | ✅ |
| PRD-PAY-02 | Áp cước tối thiểu theo khung giờ (100k/110k/120k) | Kiến trúc §3.4 | `test_pricing.py` | ✅ |
| PRD-PAY-03 | Khung giờ chốt theo giờ VN tại thời điểm đặt | Kiến trúc §3.4 | `test_pricing.py` | ✅ |
| PRD-PAY-04 | Phụ thu đón xa >5km = 20.000đ, **100% về tài xế**, không chia take-rate | Kiến trúc §3.4 | `test_pricing.py` | ✅ |
| PRD-PAY-05 | Chia: tài xế 58%, nền tảng 38% | Thanh toán §4 | `test_pricing.py` | ✅ |
| PRD-PAY-06 | Mọi phép tính tiền dùng `Decimal`, làm tròn về VNĐ nguyên | Thanh toán §7 | `test_pricing.py` | ✅ |
| PRD-PAY-07 | Idempotency: gửi trùng không tạo hai giao dịch | Thanh toán §7 | `test_idempotency.py` QA-IDM-01…07 | ✅ |
| PRD-PAY-08 | Đối soát ngày: cước vs thanh toán, payout vs ví + ký quỹ | Thanh toán §9.1 | `test_payments.py` | ✅ |
| PRD-PAY-09 | **Ledger double-entry**, không sửa số dư trực tiếp | Thanh toán §4, §9.3 | — | ❌ **P5** |
| PRD-PAY-10 | State machine thanh toán đầy đủ (pre-auth → capture → settle → payout) | Thanh toán §3 | — | ❌ **P5** |
| PRD-PAY-11 | Retry capture 3 lần rồi chuyển `DEBT_PENDING` | Thanh toán §4 bước 3 | — | ❌ **P5** |
| PRD-PAY-12 | Nhánh tiền mặt + ghi nợ hoa hồng tài xế | Thanh toán §2.2 | — | ⛔ **Chờ quyết định** |
| PRD-PAY-13 | Phí huỷ trả cho tài xế bằng bút toán ví | Thanh toán §6 | — | ❌ **P5** |
| PRD-PAY-14 | Webhook cổng thanh toán verify chữ ký, xử lý idempotent | Thanh toán §7 | — | ❌ **P5** |

## B. Ký quỹ

| PRD | Yêu cầu | Nguồn | Test | Trạng thái |
|---|---|---|---|---|
| PRD-ESC-01 | Trích 15% **của driver_payout**, không phải 15% tổng cước | Kiến trúc §3.5 | `test_escrow.py` | ✅ |
| PRD-ESC-02 | Không trích vượt định mức; đạt định mức thì chuyển `fulfilled` | Kiến trúc §3.5 | `test_escrow.py` | ✅ |
| PRD-ESC-03 | Tài xế **không** đóng tiền trước | Kiến trúc §3.5 | `test_escrow.py` | ✅ |
| PRD-ESC-04 | Phạt gian lận cho phép âm số dư (ghi công nợ, không chặn giao dịch) | Thanh toán §5 | `test_escrow.py` | ✅ |
| PRD-ESC-05 | Hoàn quỹ chỉ khi ngưng hợp tác, chi trả sau 45 ngày | Kiến trúc §3.5 | `test_escrow.py` | ✅ |
| PRD-ESC-06 | Hoàn quỹ cần duyệt hai cấp (maker–checker) | Phân định §2.3 | — | ❌ **P1** |

## C. Chuyến đi & Ghép chuyến

| PRD | Yêu cầu | Nguồn | Test | Trạng thái |
|---|---|---|---|---|
| PRD-TRIP-01 | `in_progress` **chỉ** đến được từ `qr_verified` (chống đơn ma) | Kiến trúc §3.3 | `test_trip_state_machine.py` | ✅ |
| PRD-TRIP-02 | Chuyển trạng thái sai bị từ chối | Kiến trúc §3.3 | `test_trip_state_machine.py` | ✅ |
| PRD-TRIP-03 | Chốt cước theo GPS thật, không theo ước tính | Thanh toán §4 bước 3 | `test_trips_flow.py` | ✅ |
| PRD-TRIP-04 | Kết thúc chuyến phải ở trong bán kính 300m điểm đến | Kiến trúc §3.3 | `test_trips_flow.py` | ✅ |
| PRD-TRIP-05 | Kết thúc chuyến idempotent | Thanh toán §7 | `test_trips_flow.py` | ✅ |
| PRD-TRIP-06 | Huỷ muộn thì tính phí huỷ | Thanh toán §6 | `test_trips_flow.py` | ✅ |
| PRD-MATCH-01 | Nới bán kính 5 → 8 → 12 km | Kiến trúc §3.3 | `test_matching.py` QA-MATCH-01…04 | ✅ |
| PRD-MATCH-02 | Hai tài xế cùng nhận: ai trước thắng (khoá phân tán) | Kiến trúc §3.3 | `test_matching.py` QA-MATCH-06…07 | ✅ |
| PRD-MATCH-03 | Quá 90 giây không ai nhận → `no_driver_found` | Kiến trúc §3.3 | `test_matching.py` QA-MATCH-08…09 | ✅ |
| PRD-MATCH-04 | Chỉ ghép tài xế đang rảnh, chưa quá ngưỡng cảnh cáo, tài khoản còn hoạt động | Kiến trúc §3.2 | `test_matching.py` QA-MATCH-05 | ✅ |

## D. Chống gian lận

| PRD | Yêu cầu | Nguồn | Test | Trạng thái |
|---|---|---|---|---|
| PRD-FRD-01 | Đơn ma: kết thúc khi chưa quét QR → khoá tài khoản, giữ quỹ | Kiến trúc §3.6 | `test_fraud.py` | ✅ |
| PRD-FRD-02 | Chạy vòng: cước cap ở optimal × 1.5 | Kiến trúc §3.6 | `test_fraud.py` | ✅ |
| PRD-FRD-03 | Phạt chạy vòng = phần vượt × đơn giá/km × 2 | Kiến trúc §3.6 | `test_fraud.py` | ✅ |
| PRD-FRD-04 | Thanh toán ngoài app: chỉ **gắn cờ**, admin xác nhận mới xử lý | Kiến trúc §3.6 | `test_fraud.py` | ✅ |
| PRD-FRD-05 | Tráo tài xế: selfie ngẫu nhiên, face-match < 0.85 → khoá | Kiến trúc §3.6 | `test_fraud.py` | ✅ |
| PRD-FRD-06 | QR động đổi mỗi phiên online | Kiến trúc §3.3 | `test_fraud.py` | ✅ |
| PRD-FRD-07 | Phát hiện số tài khoản/link ví trong tin nhắn chat | Phân định §7.6 | — | ❌ **P2** |

## E. Bảo mật & Quyền riêng tư

| PRD | Yêu cầu | Nguồn | Test | Trạng thái |
|---|---|---|---|---|
| PRD-SEC-01 | Access token ngắn hạn (15 phút) | Phân định §3.2 | `test_auth_tokens.py` | ✅ |
| PRD-SEC-02 | **Xoay vòng refresh token + phát hiện tái sử dụng → thu hồi cả họ** | Phân định §3.2 | `test_auth_tokens.py` QA-AUTH-01…09 | ✅ |
| PRD-SEC-03 | Hạn mức riêng cho endpoint tốn tiền (OTP) | Phân định §3.3 | `test_rate_limit_and_request_id.py` QA-RL-01…04 | ✅ |
| PRD-SEC-04 | Không ghi PII/OTP/token vào log hay audit | Phân định §7.6, NĐ13 | `test_audit.py` QA-AUD-01…04 | ✅ |
| PRD-SEC-05 | Mã hoá CCCD at-rest | Kiến trúc §8 | `test_security_crypto.py` QA-SEC-05a…e | ✅ |
| PRD-SEC-06 | Đăng xuất một thiết bị không đá thiết bị khác | Phân định §3.2 | `test_auth_tokens.py` QA-AUTH-05 | ✅ |
| PRD-SEC-07 | 2FA bắt buộc cho nhân sự nội bộ | Phân định §2.3 | — | ❌ **P1** |
| PRD-SEC-08 | Che PII mặc định, xem đầy đủ phải nhập lý do | Phân định §2.3 | — | ❌ **P1** |
| PRD-SEC-09 | Phân quyền `domain:action:scope` | Phân định §3.2 | — | ❌ **P1** |

## F. Vận hành & Quan sát

| PRD | Yêu cầu | Nguồn | Test | Trạng thái |
|---|---|---|---|---|
| PRD-OPS-01 | Mọi thao tác ghi để lại dấu vết: ai, IP, payload, thời điểm | Phân định §2.3 | `test_audit.py` QA-AUD-05…09 | ✅ |
| PRD-OPS-02 | Mỗi request có mã truy vết xuyên log và trả về client | Phân định §3.3 | `test_rate_limit_and_request_id.py` QA-OBS-01…03 | ✅ |
| PRD-OPS-03 | `/health` (liveness) tách khỏi `/ready` (readiness) | Phân định §3.3 | `test_rate_limit_and_request_id.py` QA-OBS-04 | ✅ |
| PRD-OPS-04 | Audit chỉ ghi thêm, không sửa không xoá | Phân định §2.3 | — | ⚠️ **Cần ràng buộc ở tầng DB** |
| PRD-OPS-05 | Maker–checker cho thao tác chạm tiền | Phân định §2.3 | — | ❌ **P1** |
| PRD-OPS-06 | Sentry bật theo cấu hình, không gửi kèm PII | Phân định §3.3 | — | ⚠️ **Thiếu test** |

## G. Chat & Hỗ trợ *(toàn bộ thuộc P2, chưa bắt đầu)*

| PRD | Yêu cầu | Nguồn | Test | Trạng thái |
|---|---|---|---|---|
| PRD-CHAT-01 | Ba loại hội thoại: `trip`, `support`, `internal` | Phân định §7.1 | — | ❌ |
| PRD-CHAT-02 | **CSKH tham gia hội thoại 3 bên, hai bên đều thấy thông báo** | Phân định §7.1 | — | ❌ |
| PRD-CHAT-03 | Khử trùng tin nhắn theo `client_msg_id` | Phân định §7.3 | — | ❌ |
| PRD-CHAT-04 | Mất kết nối rồi nối lại: đồng bộ đủ tin đã lỡ | Phân định §5 | — | ❌ |
| PRD-CHAT-05 | Chat `trip` tự đóng sau 24 giờ | Phân định §7.1 | — | ❌ |
| PRD-CHAT-06 | SLA: `urgent` phản hồi đầu ≤ 2 phút, quá hạn tự escalate | Phân định §7.5 | — | ❌ |

---

## Tổng kết độ bao phủ yêu cầu

| Vùng | Tổng | Đã có test | Thiếu test | Chưa làm |
|---|---:|---:|---:|---:|
| Thanh toán | 14 | 8 | 0 | 6 |
| Ký quỹ | 6 | 5 | 0 | 1 |
| Chuyến & Ghép | 10 | 10 | 0 | 0 |
| Chống gian lận | 7 | 6 | 0 | 1 |
| Bảo mật | 9 | 6 | 0 | 3 |
| Vận hành | 6 | 3 | 2 | 1 |
| Chat | 6 | 0 | 0 | 6 |
| **Tổng** | **58** | **38 (66%)** | **2** | **18** |

**Hai yêu cầu còn thiếu test** — code đã có nhưng chưa chứng minh được:

| Mã | Vì sao chưa có | Kế hoạch |
|---|---|---|
| PRD-OPS-04 | "Chỉ ghi thêm, không sửa không xoá" phải chặn ở tầng DB (thu hồi quyền UPDATE/DELETE trên `audit_logs`), không phải ở tầng ứng dụng | Làm cùng lúc với dựng staging (P0) |
| PRD-OPS-06 | Cần cài `sentry-sdk` và một máy chủ thu nhận giả để kiểm chứng "không gửi kèm PII" | Làm khi bật Sentry thật trên staging (P0) |

**Mười tám yêu cầu "chưa làm" nằm ở P1, P2, P5** — đã có trong Backlog, không phải nợ kỹ thuật.
