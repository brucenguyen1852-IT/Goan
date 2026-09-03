# GoAn — Kiến trúc kỹ thuật & Kế hoạch xây dựng sản phẩm
### Nền tảng "Grab của dịch vụ lái hộ" — Backend Python + Frontend React

> Tài liệu này bám sát mô hình nghiệp vụ trong bản gọi vốn: marketplace 2 chiều (khách có xe cần người lái hộ ↔ tài xế có bằng lái nhận ca), tính cước theo km, hoa hồng ~38%, ký quỹ tài xế trích 15%/chuyến, chống gian lận bằng QR + eKYC + GPS, và hệ sinh thái B2B2C (nhà hàng, khách sạn, bảo hiểm).

---

## 1. Nguyên tắc thiết kế

Vì đây là sản phẩm giai đoạn Seed (300 đơn/ngày, 1 thành phố, runway 12 tháng, đội ngũ nhỏ), kiến trúc ưu tiên:

1. **Modular Monolith trước, Microservices sau** — một backend Python (FastAPI) chia module rõ ràng theo domain, tách thành service riêng khi có tải thật (Năm 2–3, 3–15 thành phố). Tránh over-engineering đốt runway vào hạ tầng.
2. **Dễ maintain** — mỗi module có ranh giới rõ, contract qua interface/service layer, không gọi chéo DB trực tiếp giữa các domain.
3. **Chuẩn để mở rộng** — dùng PostgreSQL + PostGIS ngay từ đầu (bài toán định vị/điều phối là lõi sản phẩm), event-driven cho các tác vụ async (matching, thanh toán, thông báo).
4. **Vận hành thật được ngay** — có đủ Admin/Ops dashboard, hệ thống ký quỹ, chống gian lận, hóa đơn thuế — vì đây là tài liệu "sẵn sàng kinh doanh thử nghiệm", không chỉ demo.

---

## 2. Bức tranh tổng thể hệ thống

```
┌─────────────────┐   ┌─────────────────┐   ┌──────────────────┐   ┌───────────────────┐
│  Customer App    │   │   Driver App     │   │  Admin/Ops Web    │   │  Partner Portal    │
│  (React Native)  │   │  (React Native)  │   │  (React + Vite)   │   │  (React) — QR NH   │
└────────┬─────────┘   └────────┬─────────┘   └─────────┬─────────┘   └─────────┬─────────┘
         │  HTTPS/REST + WSS    │                        │                       │
         └───────────┬──────────┴────────────┬───────────┴───────────┬──────────┘
                      │                       │                       │
              ┌───────▼───────────────────────▼───────────────────────▼───────┐
              │                    API GATEWAY (Kong / Nginx)                   │
              │        Auth check, rate limit, routing, TLS termination         │
              └───────────────────────────────┬─────────────────────────────────┘
                                                │
              ┌─────────────────────────────────▼─────────────────────────────────┐
              │                BACKEND — FastAPI (modular monolith)                 │
              │ ┌───────────┐┌───────────┐┌───────────┐┌───────────┐┌────────────┐ │
              │ │  Auth &   ││  Trip &    ││  Pricing  ││  Wallet & ││  Anti-Fraud│ │
              │ │  eKYC     ││  Dispatch  ││  Engine   ││  Escrow   ││  Engine    │ │
              │ └───────────┘└───────────┘└───────────┘└───────────┘└────────────┘ │
              │ ┌───────────┐┌───────────┐┌───────────┐┌───────────┐┌────────────┐ │
              │ │  Driver   ││  Partner/ ││ Insurance ││ Notify    ││  Admin/    │ │
              │ │  Profile  ││  B2B      ││ Integration││(Push/SMS)││  Reporting │ │
              │ └───────────┘└───────────┘└───────────┘└───────────┘└────────────┘ │
              └───────┬─────────────┬───────────────┬───────────────┬─────────────┘
                      │             │               │               │
             ┌────────▼───┐ ┌───────▼──────┐ ┌──────▼──────┐ ┌──────▼────────┐
             │ PostgreSQL  │ │  Redis        │ │  Celery +   │ │  S3-compatible │
             │ + PostGIS   │ │ (cache, geo,  │ │  RabbitMQ   │ │  Object Storage│
             │ (nguồn sự   │ │ session, real-│ │ (async jobs,│ │ (ảnh CCCD,    │
             │ thật chính) │ │ time location)│ │ matching)   │ │  selfie, hóa   │
             └─────────────┘ └───────────────┘ └─────────────┘ │  đơn PDF)      │
                                                                 └────────────────┘
        Bên thứ 3: Cổng thanh toán (VNPay/MoMo/ZaloPay) · eKYC provider (VNPT/FPT.AI) ·
        SMS/OTP (ESMS/Speedsms) · Bảo hiểm (PVI/MIC API) · Bản đồ (Goong Maps / Mapbox VN) ·
        Hóa đơn điện tử (MISA/VNPT Invoice)
```

**Vì sao FastAPI:** async I/O native (quan trọng cho matching real-time nhiều tài xế/khách cùng lúc), tự sinh OpenAPI docs (dễ cho FE React tích hợp và cho đối tác B2B sau này), hệ sinh thái Python mạnh cho các job tính giá/chống gian lận sau này có thể cần ML.

**Vì sao PostGIS:** bài toán "tìm tài xế trong bán kính 5km, ETA < 10 phút" là truy vấn không gian (geospatial) — PostGIS xử lý native, tránh phải dựng thêm hệ thống riêng ở giai đoạn đầu.

---

## 3. Chi tiết các module backend (bám theo mô hình trong pitch deck)

### 3.1 Auth & eKYC
- Đăng ký/đăng nhập bằng SĐT + OTP (khách và tài xế).
- **Tài xế bắt buộc eKYC**: upload CCCD gắn chip + GPLX (đúng như deck: "Selfie ngẫu nhiên đối chiếu eKYC trước khi Start") → gọi API nhà cung cấp eKYC (VNPT eKYC / FPT.AI) để xác thực khuôn mặt, hạn GPLX, tiền án hình sự (nếu cần đối tác bảo hiểm yêu cầu).
- JWT access token + refresh token, RBAC: `customer`, `driver`, `ops_admin`, `partner_admin`, `super_admin`.

### 3.2 Driver Profile & Onboarding
- Hồ sơ tài xế: bằng lái (hạng, năm kinh nghiệm 3–10 năm theo target trong deck), lịch sử vi phạm nội bộ, trạng thái ký quỹ, rating.
- Quy trình duyệt tài xế: nộp hồ sơ → ops review (thủ công giai đoạn đầu, 50-100 tài xế tiên phong) → active.
- Trạng thái ca làm: `offline` / `online_idle` / `on_trip` — đồng bộ real-time qua Redis (không query DB liên tục).

### 3.3 Trip & Dispatch (lõi hệ thống)
State machine chuyến đi — bám sát flow trong deck:

```
REQUESTED → MATCHING → DRIVER_ASSIGNED → DRIVER_ARRIVING → QR_VERIFIED
   → IN_PROGRESS → COMPLETED → RATED
              ↘ CANCELLED_BY_CUSTOMER / CANCELLED_BY_DRIVER / NO_DRIVER_FOUND
```

- **Matching engine**: query PostGIS tìm tài xế `online_idle` trong bán kính tăng dần (0–5km trước, ưu tiên "tài xế trực vệ tinh" tại quán nhậu đối tác như deck mô tả), fallback mở rộng bán kính + áp dụng "trợ cấp đón xa" nếu vùng mới.
- **Bắt buộc QR Start**: khách quét QR gắn với tài xế/chuyến để chuyển trạng thái `QR_VERIFIED → IN_PROGRESS` — đúng cơ chế chống "đơn ma" trong deck.
- **GPS tracking**: driver app gửi tọa độ mỗi 3–5s qua WebSocket → lưu Redis (vị trí hiện tại) + ghi log route vào PostgreSQL/TimescaleDB (cho đối soát "đi lệch >1.5x tuyến tối ưu").
- Tách riêng thành service độc lập sớm nhất trong roadmap (Năm 2) vì đây là bottleneck tải cao nhất.

### 3.4 Pricing Engine
Implement chính xác công thức trong deck (mục 3.1):

```
Cước = Phí nền (30.000đ)
     + Đơn giá/km × Số km
     + Đơn giá/phút × Số phút
     + Phụ thu đón xa (20.000đ, chỉ khi >5km, 100% cho tài xế)
Áp dụng bảng giá theo khung giờ: Giờ thường / Giờ đêm / Cao điểm đặc biệt
Có mức cước tối thiểu theo từng khung giờ (100k/110k/120k)
```
- Config bảng giá lưu trong bảng `pricing_rules` (không hard-code) để Ops chỉnh từ Admin dashboard mà không cần deploy lại.
- Tính giá **trước khi khách đặt** (báo giá tạm ước lượng theo route Maps API) và **giá cuối** dựa trên route GPS thật khi hoàn thành chuyến.

### 3.5 Wallet & Escrow (Ký quỹ) — module "sống còn" theo deck
- Đúng cơ chế: **không thu tiền mặt trước**, tự động trích **15%** từ mỗi cước tài xế nhận cho đến khi đủ định mức ký quỹ (3-5 triệu).
- Ledger double-entry (bảng `wallet_transactions`) tách bạch: `driver_earning_wallet`, `driver_escrow_wallet`, `platform_revenue`, `partner_commission` (nhà hàng/khách sạn 3-7%), `insurance_fee` (5-8%).
- Hoàn quỹ sau 45-60 ngày ngưng hợp tác — cần job Celery kiểm tra định kỳ + quy trình duyệt thủ công chống rút trộm.
- Tích hợp cổng thanh toán (VNPay/MoMo/ZaloPay) cho khách trả tiền, và đối tác ngân hàng cho payout tài xế theo chu kỳ (hàng tuần).

### 3.6 Anti-Fraud Engine
Bảng ánh xạ trực tiếp từ deck mục 4.2:

| Hành vi | Cơ chế kỹ thuật | Module |
|---|---|---|
| Đơn ma (ghost trip) | Bắt buộc quét QR để Start | Trip service |
| Cố tình chạy vòng | So khớp route thực tế GPS vs route tối ưu (Maps Directions API), cờ nếu lệch >1.5x quãng đường | Anti-fraud engine, batch job sau mỗi chuyến |
| Thanh toán ngoài app | Giám sát tỷ lệ Online-time/Số đơn hoàn thành, cờ tài khoản bất thường | Analytics job (Celery beat, chạy định kỳ) |
| Tráo tài xế | Selfie ngẫu nhiên đối chiếu eKYC trước Start | eKYC service, gọi tại thời điểm `QR_VERIFIED` |

- Toàn bộ được implement như rule-engine (bảng `fraud_rules` + `fraud_flags`), giai đoạn đầu chạy rule-based; Năm 2-3 có thể nâng cấp ML scoring khi đủ dữ liệu.

### 3.7 Partner / B2B2C
- Nhà hàng, quán nhậu: cấp mã QR bàn → deep-link mở app đặt xe kèm partner_id để tính hoa hồng 3-7%.
- Khách sạn 4-5 sao: gói riêng, xuất hóa đơn VAT điện tử (tích hợp MISA/VNPT Invoice).
- Bảo hiểm (PVI, MIC): gọi API mua "bảo hiểm theo chuyến" tại thời điểm `DRIVER_ASSIGNED`, phí 5-8% trừ vào take-rate.
- Có Partner Portal riêng (React) để nhà hàng/khách sạn xem báo cáo hoa hồng, không cần vào chung Admin.

### 3.8 Notification
- Push (FCM) cho app, SMS OTP/thông báo quan trọng (ESMS/Speedsms), tất cả qua Celery task queue để không block API chính.

### 3.9 Admin / Ops & Reporting
- Dashboard quản lý: tài xế (duyệt hồ sơ, khóa/mở khóa theo mức phạt gian lận trong deck), chuyến đi real-time, doanh thu, take-rate, tỷ lệ hoàn thành (KPI >95% theo deck), GMV — map trực tiếp với bảng KPI mục 6.1.
- Export báo cáo tài chính phục vụ gọi vốn Series A sau này (deck mục 6.3: "Kinh tế đơn vị rõ ràng").

---

## 4. Database Schema (các bảng lõi)

```sql
-- Người dùng & tài xế
users(id, phone, role, full_name, created_at, status)
driver_profiles(id, user_id, license_number, license_class, years_experience,
                 ekyc_status, rating_avg, total_trips, escrow_balance,
                 escrow_target, escrow_status, status ENUM(offline,online_idle,on_trip,suspended))
driver_documents(id, driver_id, doc_type ENUM(cccd,gplx,selfie), file_url, verified_at)

-- Chuyến đi
trips(id, customer_id, driver_id, status, pickup_geo, dropoff_geo,
      requested_at, matched_at, started_at, completed_at,
      distance_km, duration_min, base_fare, distance_fare, time_fare,
      surcharge_far_pickup, total_fare, time_band ENUM(normal,night,peak),
      qr_verified_at, route_polyline_actual, route_polyline_optimal,
      route_deviation_ratio, partner_id NULL, cancel_reason NULL)
trip_events(id, trip_id, event_type, payload_json, created_at)  -- audit trail đầy đủ

-- Tài chính / Ký quỹ
wallet_transactions(id, wallet_owner_type, wallet_owner_id, wallet_type
                     ENUM(earning,escrow,platform,partner,insurance),
                     trip_id, amount, direction ENUM(credit,debit), created_at)
payouts(id, driver_id, amount, period_start, period_end, status, bank_ref)

-- Chống gian lận
fraud_flags(id, trip_id, driver_id, rule_code, severity, status ENUM(open,reviewed,confirmed), created_at)

-- Định giá & Đối tác
pricing_rules(id, time_band, base_fee, per_km, per_min, min_fare, far_pickup_fee, effective_from)
partners(id, type ENUM(restaurant,hotel,insurance), name, commission_rate, qr_code, status)
insurance_policies(id, trip_id, provider, premium_amount, coverage_json, status)
```

> Khuyến nghị: dùng **PostGIS `geography` type** cho `pickup_geo`/`dropoff_geo` để query `ST_DWithin` khi matching tài xế gần nhất trong bán kính.

---

## 5. API thiết kế (mẫu endpoint chính)

```
POST   /api/v1/auth/otp/request
POST   /api/v1/auth/otp/verify
POST   /api/v1/driver/ekyc/submit

POST   /api/v1/trips                     # khách tạo yêu cầu (trả giá ước tính ngay)
GET    /api/v1/trips/{id}
WS     /ws/trips/{id}/track              # cả 2 phía theo dõi vị trí real-time
POST   /api/v1/trips/{id}/qr-verify      # bắt buộc trước khi Start
POST   /api/v1/trips/{id}/complete
POST   /api/v1/trips/{id}/cancel

GET    /api/v1/driver/status             # online/offline toggle
POST   /api/v1/driver/location           # gửi vị trí (hoặc qua WS)

GET    /api/v1/wallet/driver/{id}
GET    /api/v1/wallet/driver/{id}/escrow

GET    /api/v1/admin/trips?status=...
GET    /api/v1/admin/fraud-flags
POST   /api/v1/admin/drivers/{id}/suspend

GET    /api/v1/partner/{id}/commissions
```

Real-time dùng **WebSocket** (FastAPI native support) cho: vị trí tài xế, trạng thái chuyến, thông báo matching — REST cho phần còn lại.

---

## 6. Frontend — kiến trúc React

| App | Công nghệ | Ghi chú |
|---|---|---|
| Customer App | **React Native (Expo)** | Bản đồ (react-native-maps + Goong/Mapbox), đặt xe, theo dõi real-time, thanh toán |
| Driver App | **React Native (Expo)** | Nhận cuốc, điều hướng, quét QR (camera), quản lý ví ký quỹ |
| Admin/Ops Web | **React + Vite + TypeScript** | TailwindCSS, TanStack Query cho data-fetching, bản đồ real-time toàn hệ thống (giống "Grab Ops") |
| Partner Portal | **React + Vite** | Đơn giản, chỉ xem báo cáo hoa hồng + QR |

- Dùng chung **1 design system** (component library nội bộ) và **1 API client SDK** (generate từ OpenAPI schema của FastAPI) giữa các app để giảm trùng lặp code và dễ maintain khi scale.
- State management: Zustand/Redux Toolkit (nhẹ, đủ dùng ở quy mô này) + React Query cho cache API.

---

## 7. Hạ tầng & DevOps (giai đoạn Seed — tối ưu chi phí)

- **Hosting**: bắt đầu trên 1 VPS/managed cloud (AWS Lightsail, DigitalOcean, hoặc nhà cung cấp VN như VNG Cloud/Viettel Cloud để dễ tuân thủ lưu trữ dữ liệu trong nước) — Docker Compose cho MVP, chuyển sang Kubernetes khi scale sang 3-5 thành phố (Năm 2, đúng theo roadmap deck).
- **CI/CD**: GitHub Actions → build/test/deploy tự động, staging + production environment tách biệt.
- **Monitoring**: Sentry (lỗi), Grafana + Prometheus (metrics), tối thiểu nhưng đủ để theo dõi KPI tỷ lệ hoàn thành >95%.
- **Backup**: PostgreSQL daily backup + point-in-time recovery — bắt buộc vì đây là dữ liệu tài chính/ký quỹ.

---

## 8. Bảo mật & tuân thủ pháp lý (Việt Nam)

- Nghị định 13/2023 về bảo vệ dữ liệu cá nhân: mã hóa CCCD/GPLX lưu trữ (encryption at rest), có chính sách xóa dữ liệu.
- Hóa đơn điện tử VAT theo yêu cầu Thông tư thuế hiện hành — tích hợp nhà cung cấp hóa đơn điện tử ngay từ Tháng 0-2 (đúng deck mục 6.3).
- Xác thực GPLX với cơ sở dữ liệu ngành GTVT nếu có API công khai/đối tác (tăng độ tin cậy hồ sơ tài xế).
- Toàn bộ giao dịch tiền qua cổng thanh toán được cấp phép (VNPay, MoMo, ZaloPay) — không tự giữ tiền khách ngoài chu trình escrow đã khai báo.

---

## 9. Lộ trình kỹ thuật 12 tháng (khớp với kế hoạch gọi vốn)

| Giai đoạn | Deck (mục 6.3) | Việc kỹ thuật cụ thể |
|---|---|---|
| **Tháng 0-2** | Nền móng | Dựng modular monolith FastAPI + PostgreSQL/PostGIS, Auth/eKYC, Trip state machine cơ bản, Wallet/Escrow, tích hợp cổng thanh toán + hóa đơn điện tử, App MVP (React Native) cho khách & tài xế, Admin dashboard tối thiểu |
| **Tháng 2-4** | Thử nghiệm 1 quận + 20 quán nhậu | Module Partner/QR, GPS tracking + route deviation check, đo lường tỷ lệ hoàn thành, thu thập dữ liệu để tinh chỉnh matching |
| **Tháng 4-8** | Mở rộng phủ thành phố | Tối ưu matching (bán kính động, tài xế vệ tinh), gói Doanh nghiệp B2B, hoàn thiện Anti-fraud rule engine, load testing |
| **Tháng 8-12** | Nhân rộng, KPI 300 đơn/ngày | Tách Dispatch service riêng nếu cần, dashboard Unit Economics cho Series A, chuẩn bị hạ tầng multi-city (Kubernetes) |

---

## 10. Đội ngũ kỹ thuật tối thiểu đề xuất (ứng với ngân sách 250.000 USD, 30% cho Phát triển sản phẩm)

- 1 Tech Lead / Backend chính (Python/FastAPI)
- 1-2 Backend engineer (Trip/Matching, Wallet/Payment)
- 1-2 Mobile engineer (React Native — có thể 1 người phụ trách cả Customer + Driver app giai đoạn đầu)
- 1 Frontend engineer (Admin/Partner web)
- 1 DevOps/bán thời gian (thuê ngoài giai đoạn đầu để tiết kiệm)
- 1 QA/tester bán thời gian

---

## 11. Rủi ro kỹ thuật cần lưu ý sớm

1. **Matching khi mật độ tài xế thấp** (giai đoạn đầu ít tài xế) → cần cơ chế "trợ cấp đón xa" và tài xế vệ tinh hoạt động tốt ngay từ Tháng 0-2, nếu không tỷ lệ no-driver-found sẽ giết trải nghiệm.
2. **Độ chính xác GPS trong đô thị** (nhà cao tầng) ảnh hưởng tính route-deviation chống gian lận → cần ngưỡng dung sai hợp lý (1.5x như deck) và log để Ops review thủ công case biên.
3. **Chu trình ký quỹ 45-60 ngày** cần quy trình đối soát kế toán chặt để tránh tranh chấp pháp lý với tài xế — nên có audit log đầy đủ (`trip_events`, `wallet_transactions`) ngay từ đầu.
4. **Phụ thuộc bên thứ 3** (eKYC, bảo hiểm, hóa đơn điện tử) — cần thiết kế adapter pattern để dễ đổi nhà cung cấp mà không sửa core logic.

---

*Tài liệu này là bản kiến trúc kỹ thuật để triển khai MVP dùng thử kinh doanh thật, bám sát toàn bộ mô hình nghiệp vụ, công thức tính giá, cơ chế ký quỹ và chống gian lận đã nêu trong bản kế hoạch gọi vốn GoAn (08/2026).*
