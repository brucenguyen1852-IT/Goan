# GoAn — Thiết kế chi tiết luồng thanh toán (Payment Flow)

> Thiết kế này mở rộng module **Wallet & Escrow** trong tài liệu kiến trúc trước, xử lý đầy đủ 2 phương thức phổ biến ở VN: **thanh toán online qua app** và **tiền mặt trực tiếp cho tài xế** — vì thực tế thị trường lái hộ tiền mặt vẫn chiếm t�V trọng lớn, nền tảng vẫn phải thu được hoa hồng.

---

## 1. Các bên liên quan trong 1 giao dịch

```
Khách hàng ──trả cước──▶ [Cổng TT: VNPay/MoMo/ZaloPay]  hoặc  [Tiền mặt cho tài xế]
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │   GoAn Ledger (nguồn     │
                        │   sự thật, double-entry) │
                        └────────────┬────────────┘
                     ┌───────────────┼────────────────┬───────────────┐
                     ▼               ▼                ▼               ▼
              Ví thu nhập TX   Ví ký quỹ TX      Doanh thu nền     Hoa hồng đối tác
              (58% cước)       (15% trích từ      tảng (38% -      (3-7% NH/KS,
                                phần TX nhận)      hoa hồng ĐT -    trừ vào phần
                                                    phí BH)         nền tảng giữ)
```

---

## 2. Hai phương thức thanh toán — xử lý khác nhau hoàn toàn

### 2.1 Thanh toán Online (qua ví/thẻ liên kết trong app)
Đây là luồng **ưu tiên khuyến khích** (nền tảng kiểm soát dòng tiền tốt nhất, giảm rủi ro gian lận thanh toán ngoài app mà deck đã cảnh báo).

### 2.2 Tiền mặt (khách đưa trực tiếp cho tài xế)
Tài xế **thu đủ 100% cước bằng tiền mặt**, nhưng nền tảng vẫn phải thu hoa hồng 38% → xử lý bằng cơ chế **"công nợ tài xế" (driver payable)**: hệ thống ghi nhận tài xế đang nợ nền tảng phần hoa hồng, trừ dần vào các chuyến tiếp theo (thanh toán online) hoặc tài xế chủ động nạp trả qua ví.

---

## 3. State machine trạng thái thanh toán

```
PENDING_METHOD_SELECT → (khách chọn Online / Tiền mặt tại bước đặt xe)

  Nhánh ONLINE:
  PENDING_AUTH → AUTHORIZED (giữ tạm/pre-auth nếu cổng hỗ trợ) → CAPTURED (khi trip COMPLETED)
      → SETTLED (đã đối soát, chia ví) → PAYOUT_SCHEDULED → PAYOUT_DONE
      ↘ AUTH_FAILED → cho khách chọn lại phương thức / thẻ khác
      ↘ CAPTURE_FAILED → retry tự động 3 lần (Celery) → nếu vẫn fail: chuyển trạng thái
        DEBT_PENDING (khách nợ), khóa tính năng đặt xe tiếp cho đến khi thanh toán

  Nhánh TIỀN MẶT:
  CASH_DECLARED (tài xế xác nhận đã thu tiền mặt qua app khi bấm "Hoàn thành")
      → COMMISSION_DEBITED (hệ thống ghi nợ hoa hồng vào ví tài xế ngay lập tức)
      → nếu ví ký quỹ + earning không đủ bù → DRIVER_DEBT (cần trả trước khi nhận chuyến mới
        nếu nợ vượt ngưỡng, ví dụ >300.000đ)
```

---

## 4. Luồng chi tiết theo từng bước (Sequence)

### Bước 1 — Trước chuyến đi (Fare Estimate)
1. Khách nhập điểm đón/đến → gọi `Pricing Service` tính **giá ước lượng** theo route Maps API + khung giờ.
2. Khách **chọn phương thức thanh toán** trước khi xác nhận đặt: `Online (ví/thẻ đã liên kết)` hoặc `Tiền mặt`.
3. Nếu chọn Online và cổng thanh toán hỗ trợ pre-authorization (tùy VNPay/thẻ quốc tế): hệ thống **giữ tạm** số tiền ước lượng +10% buffer (tránh trường hợp giá cuối cao hơn do phát sinh đón xa). MoMo/ZaloPay QR nội địa thường **không hỗ trợ pre-auth** → giai đoạn đầu bỏ qua bước này, chỉ capture khi hoàn thành chuyến (chấp nhận rủi ro thấp vì đơn giá đã minh bạch từ đầu).

### Bước 2 — Trong chuyến đi
4. Trạng thái payment = `PENDING_AUTH` (online) hoặc chưa phát sinh gì (tiền mặt) — khách **chưa bị trừ tiền**.
5. Phí bảo hiểm theo chuyến (5-8%) được tính và ghi nhận tại thời điểm `DRIVER_ASSIGNED`, cộng vào công thức giá cuối.

### Bước 3 — Hoàn thành chuyến (`trip.status = COMPLETED`)
6. `Pricing Service` tính **giá cuối cùng** dựa trên route GPS thật (không phải ước lượng).
7. Rẽ nhánh theo phương thức:

**Nhánh Online:**
- Gọi API `capture` của cổng thanh toán với số tiền cuối cùng.
- Thành công → `payment.status = CAPTURED`, bắn event `payment.captured` vào queue.
- Thất bại → retry 3 lần cách nhau 5 phút (Celery), nếu vẫn fail → đánh dấu `DEBT_PENDING`, thông báo khách, khóa đặt chuyến mới cho đến khi thanh toán bù (giữ tài xế không bị ảnh hưởng — tài xế vẫn được trả đủ từ quỹ tạm ứng của nền tảng, đây là rủi ro nền tảng gánh, không đẩy sang tài xế).

**Nhánh Tiền mặt:**
- App tài xế hiện màn hình "Xác nhận đã thu {X}đ tiền mặt" → tài xế bấm xác nhận.
- Hệ thống ngay lập tức ghi bút toán nợ: debit `driver_earning_wallet` số tiền = hoa hồng nền tảng phải thu (38% × cước, cộng phí bảo hiểm nếu áp dụng) — vì tài xế đã giữ 100% tiền mặt.
- Nếu `driver_earning_wallet` không đủ (tài xế mới, chưa tích lũy) → cấn trừ tiếp vào `driver_escrow_wallet` (không được rút quá định mức tối thiểu quỹ) → phần còn thiếu ghi vào `driver_debt`.

### Bước 4 — Chia ví (Settlement) — áp dụng cho cả 2 nhánh, chạy trong 1 transaction DB
```
Cước cuối = X
─────────────────────────────────────
Doanh thu nền tảng (take-rate)  = 38% × X
  - trừ hoa hồng đối tác NH/KS  = 3-7% × X   (nếu trip có partner_id)
  - trừ phí bảo hiểm            = 5-8% × X   (chuyển cho đối tác bảo hiểm theo kỳ)
  = Biên gộp thực nền tảng giữ  (~26% theo deck)

Thu nhập tài xế (58% × X):
  - trích ký quỹ 15%  → driver_escrow_wallet  (nếu escrow_status != FULL)
  - còn lại           → driver_earning_wallet (khả dụng để rút)
```
Toàn bộ 4-5 bút toán trên được ghi trong **1 database transaction ACID** trên bảng `wallet_transactions` (double-entry: mỗi bút toán có cặp debit/credit khớp tổng = 0) — không bao giờ update số dư trực tiếp, luôn tính từ tổng ledger để đảm bảo audit được.

### Bước 5 — Hóa đơn điện tử
8. Sau khi `SETTLED`, job async gọi API nhà cung cấp hóa đơn điện tử (MISA/VNPT Invoice) xuất hóa đơn VAT cho khách (đặc biệt bắt buộc với khách sạn/doanh nghiệp B2B) → lưu PDF vào Object Storage, gửi link qua app/email.

### Bước 6 — Payout tài xế
9. Định kỳ (đề xuất **hàng tuần**, thứ 2 hàng tuần), Celery Beat job tổng hợp `driver_earning_wallet` khả dụng của từng tài xế → tạo `payout` batch → gọi API chuyển khoản ngân hàng (qua đối tác như VNPay Payout/Paybox) → cập nhật `payout.status = DONE`.
10. Tài xế có thể xem tạm ứng "rút nhanh" (instant payout, trừ phí nhỏ) nếu nền tảng muốn tăng sức hút tuyển tài xế giai đoạn đầu — **tính năng optional, thêm ở Năm 2** khi dòng tiền ổn định.

---

## 5. Xử lý Ký quỹ (Escrow) trong luồng thanh toán

- `driver_escrow_wallet` có 2 trường quan trọng: `current_balance`, `target_amount` (3.000.000 – 5.000.000đ tùy chính sách).
- Mỗi chuyến hoàn thành (dù online hay tiền mặt) đều trích 15% thu nhập tài xế vào escrow **cho đến khi `current_balance >= target_amount`** → sau đó dừng trích, 100% thu nhập vào ví khả dụng.
- Escrow **không xuất hiện trong "ví khả dụng để rút"** — tách bảng riêng, chỉ hoàn trả (`refund_escrow` job) sau 45-60 ngày kể từ ngày tài xế ngưng hợp tác **và** không có `fraud_flags` mở/confirmed nào liên quan.
- Escrow được dùng để **bù trừ tự động** khi: (a) tài xế bị phạt gian lận (deck mục 4.2: "Phạt = Mức chênh lệch x2"), (b) tài xế có `driver_debt` từ giao dịch tiền mặt mà không trả kịp.

---

## 6. Hoàn tiền & Hủy chuyến

| Tình huống | Xử lý thanh toán |
|---|---|
| Khách hủy trước khi tài xế `DRIVER_ASSIGNED` | Không phát sinh phí, hủy pre-auth nếu có |
| Khách hủy sau khi tài xế đã đến điểm đón (`DRIVER_ARRIVING`) | Phí hủy cố định (vd 20.000đ) trả cho tài xế, trừ trực tiếp qua cổng TT hoặc ghi nợ nếu tiền mặt |
| Tài xế hủy / không đến | Không thu phí khách, hoàn pre-auth ngay, tài xế bị trừ điểm uy tín (ops review) |
| Tranh chấp giá cuối (khách khiếu nại lệch route) | Đóng băng `payment.status = DISPUTED`, Ops review `route_deviation_ratio`, quyết định giữ nguyên/điều chỉnh giá trước khi capture |
| Sự cố bảo hiểm cần bồi thường | Trigger riêng ngoài luồng payment thường, qua `insurance_policies`, không ảnh hưởng ví tài xế |

---

## 7. Idempotency & An toàn giao dịch

- Mọi request gọi cổng thanh toán đều có `idempotency_key = trip_id + attempt_number` để tránh double-charge khi retry mạng.
- Webhook từ cổng thanh toán (VNPay/MoMo callback) phải **verify chữ ký (signature)** trước khi xử lý, và xử lý idempotent (nếu đã `CAPTURED` thì bỏ qua webhook trùng).
- Toàn bộ thao tác trừ/cộng ví chạy trong DB transaction với `SELECT ... FOR UPDATE` trên dòng ví liên quan để tránh race condition khi 2 job chạy song song (vd: 1 chuyến settlement + 1 payout job cùng lúc).

---

## 8. Bảng dữ liệu bổ sung cho luồng thanh toán

```sql
payments(id, trip_id, method ENUM(online,cash), gateway ENUM(vnpay,momo,zalopay,none),
         status ENUM(pending_auth,authorized,captured,capture_failed,debt_pending,
                     settled,refunded,disputed),
         estimated_amount, final_amount, gateway_txn_ref, idempotency_key,
         created_at, captured_at, settled_at)

driver_debts(id, driver_id, source ENUM(cash_commission,fraud_penalty,other),
             trip_id NULL, amount, status ENUM(open,cleared), created_at, cleared_at)

payouts(id, driver_id, total_amount, period_start, period_end,
        status ENUM(scheduled,processing,done,failed), bank_txn_ref)

invoices(id, trip_id, invoice_number, pdf_url, tax_amount, issued_at)
```

---

## 9. Tóm tắt quyết định thiết kế chính

1. **Không giữ tiền pre-auth cho MoMo/ZaloPay** giai đoạn đầu (hạn chế kỹ thuật cổng nội địa) — chấp nhận capture sau khi hoàn thành, đơn giá minh bạch từ đầu giảm rủi ro tranh chấp.
2. **Tiền mặt vẫn được hỗ trợ đầy đủ** (thực tế thị trường VN) nhưng qua cơ chế ghi nợ hoa hồng tự động — không đánh mất doanh thu nền tảng.
3. **Mọi bút toán là double-entry, immutable** — không sửa/xóa, chỉ ghi thêm bút toán điều chỉnh → phục vụ audit khi gọi vốn Series A ("Kinh tế đơn vị rõ ràng" theo deck mục 6.3).
4. **Rủi ro thanh toán thất bại nền tảng gánh trước, không đẩy sang tài xế** — giữ trải nghiệm tài xế ổn định để giữ chân nguồn cung giai đoạn đầu (đúng tinh thần deck: tài xế là tài sản khan hiếm cần giữ).
