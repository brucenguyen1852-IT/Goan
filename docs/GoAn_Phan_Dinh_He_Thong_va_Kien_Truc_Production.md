# GoAn — Phân định hệ thống & Kiến trúc Production

> Tài liệu này chốt ranh giới giữa các sản phẩm (app khách, app tài xế, hệ thống quản lý nội bộ,
> portal đối tác, website), quy định **một backend duy nhất** phục vụ tất cả, và bổ sung hai module
> mới: **Theo dõi hành trình (Tracking)** và **Chat trực tiếp CSKH ↔ Tài xế ↔ Khách**.
>
> Nó thay thế phần "Frontend" trong `GoAn_Kien_Truc_Ky_Thuat_Va_Ke_Hoach_Trien_Khai.md` và bổ sung
> cho `GoAn_Thiet_Ke_Luong_Thanh_Toan.md`. Mọi con số nghiệp vụ (cước, take-rate, ký quỹ) giữ nguyên
> theo hai tài liệu đó.
>
> Quyết định stack đã chốt: **React Native + Expo** cho 2 app mobile, **chat tự xây** trên hạ tầng
> WebSocket + Redis pub/sub sẵn có.

---

## 0. Tóm tắt một trang

| # | Sản phẩm | Đối tượng | Stack | Backend surface |
|---|---|---|---|---|
| 1 | **GoAn Rider** | Khách hàng | React Native + Expo | `/api/v1/rider/*` |
| 2 | **GoAn Driver** | Tài xế | React Native + Expo | `/api/v1/driver/*` |
| 3 | **GoAn Console** | Nhân sự nội bộ (Ops, CSKH, Tài chính, Risk, HR tài xế, Marketing) | React + Vite + TS | `/api/v1/ops/*` |
| 4 | **GoAn Partner Portal** | Nhà hàng / khách sạn / bảo hiểm | React + Vite + TS | `/api/v1/partner/*` |
| 5 | **goan.vn (Website)** | Công chúng, ứng viên tài xế | Next.js + Headless CMS | `/api/v1/public/*` + CMS riêng |

**Một backend duy nhất**: `services/api` (FastAPI modular monolith, phát triển tiếp từ
`goan-backend-spec`). Không có backend thứ hai cho website — website chỉ dùng CMS riêng cho nội dung
tĩnh và gọi vài endpoint public của backend chính cho form đăng ký tài xế / lead đối tác.

**Hai module mới**: `domains/tracking` và `domains/chat`.

**Việc phải dọn trước khi bắt đầu**: xoá `goan-backend` (bản nháp cũ), viết lại API client của
`goan-customer-app` (đang trỏ sai toàn bộ endpoint — xem mục 9.1).

---

## 1. Nguyên tắc phân định

1. **Một nguồn sự thật cho nghiệp vụ.** Toàn bộ logic tính tiền, state machine chuyến, ký quỹ, chống
   gian lận nằm ở backend. Client **không được** tự tính lại cước, tự suy ra trạng thái, hay tự quyết
   quyền. Client chỉ hiển thị và gửi ý định.
2. **Phân định theo đối tượng sử dụng, không theo tính năng.** Một tính năng có thể xuất hiện ở nhiều
   app (vd: xem chuyến), nhưng dữ liệu trả về và quyền thao tác khác nhau hoàn toàn theo vai trò.
3. **API surface tách theo audience, service dùng chung.** 5 nhóm router riêng, nhưng gọi chung một
   tầng `domains/*/service.py`. Tách router giúp: phân quyền rõ, rate-limit riêng, versioning riêng,
   và sau này tách microservice không phải viết lại logic.
4. **Không có endpoint "đa năng".** Một endpoint phục vụ đúng một vai trò. `GET /ops/trips` và
   `GET /rider/trips` là hai endpoint khác nhau dù cùng đọc bảng `trips` — vì phạm vi dữ liệu, phân
   trang, filter và audit khác nhau.
5. **Website không chạm vào core.** Nội dung marketing nằm ở CMS riêng, sự cố website không được
   ảnh hưởng khả năng đặt xe.
6. **Mọi thao tác của nhân sự nội bộ đều để lại dấu vết.** Không có hành động nào trên Console mà
   không ghi `audit_logs`.

---

## 2. Ranh giới từng sản phẩm

### 2.1 GoAn Rider — app khách hàng

| Nhóm | Chức năng | Ghi chú |
|---|---|---|
| Tài khoản | SĐT + OTP, hồ sơ, ảnh đại diện, người liên hệ khẩn cấp | |
| Đặt xe | Chọn điểm đón/đến, xem **giá ước tính minh bạch** (tách phí nền / km / phút / phụ thu đón xa), chọn phương thức thanh toán | Giá do backend trả, app không tự tính |
| Chuyến | Theo dõi tài xế real-time, xem ETA, **quét QR tài xế để bắt đầu chuyến**, huỷ chuyến, xem cước cuối | QR là bắt buộc — chống đơn ma |
| An toàn | **Chia sẻ hành trình** cho người thân (link public có hạn), nút SOS, xem thông tin + biển số tài xế | Mục 6.4 |
| Chat | Nhắn với tài xế trong chuyến; nhắn với CSKH bất cứ lúc nào | Mục 7 |
| Sau chuyến | Đánh giá, khiếu nại (mở ticket kèm chuyến), xem hoá đơn, lịch sử | |
| Thanh toán | Liên kết thẻ/ví, xem giao dịch | |
| Khác | Nhận deep-link QR bàn nhà hàng đối tác, khuyến mãi | |

**Không có trong app khách:** bất kỳ thông tin nào về ký quỹ, công nợ, take-rate, hay dữ liệu tài xế
ngoài tên/ảnh/biển số/đánh giá.

### 2.2 GoAn Driver — app tài xế

| Nhóm | Chức năng | Ghi chú |
|---|---|---|
| Onboarding | Nộp CCCD + GPLX, eKYC, chờ duyệt, xem lý do từ chối | Duyệt ở Console |
| Ca làm | Bật/tắt nhận chuyến, **sinh QR động mỗi phiên online**, xem bản đồ nhiệt gợi ý vị trí trực | QR đổi mỗi phiên |
| Nhận chuyến | Nhận offer (WS, TTL 20s), accept/từ chối, điều hướng đến điểm đón | Ai accept trước thắng |
| Chạy chuyến | Gửi GPS nền, xác nhận đến nơi, đợi khách quét QR, kết thúc chuyến | Kết thúc phải ở trong bán kính 300m điểm đến |
| Chống gian lận | **Selfie ngẫu nhiên** 30–90 phút/phiên đối chiếu eKYC | Sai ngưỡng 0.85 → khoá |
| Tài chính | Ví (pending / khả dụng), **ký quỹ** (số dư, định mức, lịch sử trích), rút tiền, đối soát chuyến | Ký quỹ tách bạch, không rút được |
| Chat | Nhắn với khách trong chuyến; nhắn với CSKH | Mục 7 |
| Hỗ trợ | Mở ticket, xem quyết định xử lý gian lận, khiếu nại phạt | |

**Đặc thù kỹ thuật app tài xế (khác hẳn app khách):**

| Vấn đề | Yêu cầu |
|---|---|
| GPS nền | Chạy khi app ở background/khoá màn hình — `expo-location` background task + foreground service (Android), `UIBackgroundModes: location` (iOS) |
| Pin | Tần suất ping thích ứng: 3s khi `in_progress`, 10s khi `online` chờ chuyến, 60s khi đứng yên |
| Mất mạng | Hàng đợi ping offline, gửi bù khi có mạng; **không được mất điểm GPS** vì ảnh hưởng tính cước và đối soát chạy vòng |
| Đánh thức | Push high-priority (FCM) khi có offer, kể cả app bị kill |
| Camera | Quét QR không dùng (QR nằm ở tài xế, khách quét), nhưng cần camera cho selfie + chụp giấy tờ |

> Vì các yêu cầu nền này, app tài xế là phần rủi ro kỹ thuật cao nhất của cả dự án. Nếu Expo managed
> workflow không đáp ứng được background location ổn định, chuyển riêng app tài xế sang
> **Expo + development build (config plugin native)** — vẫn giữ chung codebase TS, không cần đổi stack.

### 2.3 GoAn Console — hệ thống quản lý nội bộ

Đây là "hệ thống quản lý chuẩn một công ty": chia theo **phòng ban**, có **phân tách trách nhiệm
(separation of duties)** và **maker–checker** cho mọi thao tác chạm tiền.

| Module | Phòng ban | Chức năng chính |
|---|---|---|
| **Live Ops** | Điều phối | Bản đồ toàn hệ thống real-time (tài xế online / chuyến đang chạy), chuyến kẹt matching, gán tài xế thủ công, huỷ chuyến hộ |
| **Support Desk** | CSKH | Hàng đợi hội thoại, ticket, SLA, tham gia chat 3 bên, gọi điện, canned response, lịch sử chuyến + chat của khách/tài xế |
| **Driver Ops** | Vận hành tài xế | Duyệt hồ sơ/eKYC, khoá/mở tài khoản, quản lý cảnh cáo, đào tạo, xếp hạng |
| **Risk & Fraud** | Kiểm soát rủi ro | Hàng đợi review gian lận, xem bằng chứng (route thực vs tối ưu, selfie, tỷ lệ online/đơn), quyết định phạt/khoá |
| **Finance** | Tài chính – Kế toán | Đối soát ngày, sổ ví & ký quỹ, duyệt rút tiền, duyệt hoàn ký quỹ, hoá đơn VAT, báo cáo doanh thu/take-rate |
| **Pricing & Promo** | Marketing / Vận hành giá | Bảng giá theo khung giờ, khung cao điểm, vùng trợ cấp đón xa, mã khuyến mãi |
| **Partners** | Kinh doanh B2B | Hồ sơ đối tác, QR bàn, tỷ lệ hoa hồng, đối soát chi trả đối tác |
| **Analytics** | Ban lãnh đạo | KPI: tỷ lệ hoàn thành, GMV, take-rate thực, unit economics, cohort tài xế |
| **IAM & Audit** | Quản trị hệ thống | Người dùng nội bộ, vai trò, quyền, nhật ký thao tác, phiên đăng nhập |

**Ma trận vai trò (RBAC theo permission, không theo role cứng):**

| Vai trò | Quyền tiêu biểu | Không được |
|---|---|---|
| `super_admin` | Toàn quyền + quản lý IAM | — |
| `ops_manager` | Xem toàn bộ vận hành, duyệt cấp 2 các quyết định Ops | Chạm sổ tiền |
| `dispatcher` | Gán/huỷ chuyến, xem bản đồ live | Xem CCCD, chạm tiền |
| `cs_agent` | Chat, ticket, xem chuyến của khách đang hỗ trợ | Hoàn tiền, khoá tài khoản |
| `cs_lead` | + Escalate, duyệt hoàn tiền ≤ hạn mức, xem toàn bộ hội thoại | Duyệt payout |
| `driver_ops` | Duyệt hồ sơ, khoá/mở tài xế | Quyết định phạt tiền |
| `risk_analyst` | Xem bằng chứng, đề xuất phạt/khoá (maker) | Tự phê duyệt phạt của mình |
| `finance_accountant` | Tạo lệnh chi, đối soát (maker) | Tự duyệt lệnh chi |
| `finance_manager` | Duyệt lệnh chi, duyệt hoàn ký quỹ (checker) | Tạo lệnh chi |
| `partner_manager` | Quản lý đối tác, hoa hồng | Chạm ví tài xế |
| `marketing` | Bảng giá, khuyến mãi, vùng trợ cấp | Xem PII |
| `auditor` | Read-only toàn hệ thống + audit log | Mọi thao tác ghi |

**Nguyên tắc bắt buộc của Console:**

| Nguyên tắc | Cụ thể |
|---|---|
| Maker–checker | Payout, hoàn ký quỹ, điều chỉnh cước, phạt gian lận, hoàn tiền > hạn mức: người tạo ≠ người duyệt |
| Audit log | Mọi request ghi: ai, IP, thiết bị, endpoint, payload trước/sau, lý do. Bắt buộc nhập lý do cho thao tác nhạy cảm |
| Che PII | Số điện thoại/CCCD hiển thị dạng che; bấm "xem đầy đủ" phải nêu lý do và bị ghi log |
| Hạn mức | Mỗi vai trò có trần giá trị thao tác/ngày |
| Đăng nhập | Email công ty + mật khẩu + **bắt buộc 2FA (TOTP)**, phiên 8 giờ, IP allowlist tuỳ chọn |
| Không dùng chung tài khoản | Mỗi nhân sự một tài khoản; rời công ty là vô hiệu hoá, không xoá (giữ audit trail) |

### 2.4 GoAn Partner Portal

| Chức năng | Ghi chú |
|---|---|
| Đăng nhập đối tác (email + OTP email) | Tách hoàn toàn khỏi tài khoản nội bộ |
| QR bàn / QR quầy lễ tân, in ấn | Sinh từ backend, gắn `partner_id` |
| Báo cáo chuyến phát sinh từ QR của mình | Chỉ dữ liệu của chính đối tác đó |
| Hoa hồng: phát sinh, kỳ chi trả, trạng thái | Read-only, đối soát ở Finance |
| Hoá đơn VAT (khách sạn/B2B) | Tải PDF |
| Quản lý chi nhánh, nhân viên của đối tác | Phân quyền 2 cấp trong 1 đối tác |

### 2.5 Website goan.vn

| Phần | Nguồn dữ liệu | Ghi chú |
|---|---|---|
| Landing, giới thiệu dịch vụ, bảng giá tham khảo | CMS | SEO là mục tiêu chính → Next.js SSG/ISR |
| Blog, tin tức, trang tuyển dụng | CMS | Marketing tự đăng, không cần dev |
| **Form đăng ký làm tài xế** | `POST /api/v1/public/driver-applications` | Ghi thẳng vào hàng đợi Driver Ops |
| **Form đăng ký đối tác** | `POST /api/v1/public/partner-leads` | Vào CRM/Partner module |
| Trang tra cứu chuyến chia sẻ | `GET /api/v1/public/trips/shared/{token}` | Link "chia sẻ hành trình" mở được trên web |
| Trang chính sách, điều khoản, bảo mật | CMS | Bắt buộc để lên store |

**CMS**: khuyến nghị **Payload CMS** (self-host, Postgres, TypeScript — cùng ngôn ngữ với FE) hoặc
Strapi. Chạy như một service riêng, DB riêng, **không dùng chung DB với backend chính**.

Ba endpoint public trên là **toàn bộ** bề mặt mà website được phép chạm vào core. Chúng phải có
rate-limit chặt + CAPTCHA vì đứng ngoài xác thực.

---

## 3. Backend — cấu trúc một backend cho tất cả

### 3.1 Bề mặt API theo đối tượng

```
services/api/app/
├── api/
│   ├── rider/        # router cho app khách
│   ├── driver/       # router cho app tài xế
│   ├── ops/          # router cho Console (RBAC theo permission)
│   ├── partner/      # router cho Partner Portal
│   └── public/       # không cần đăng nhập (website, link chia sẻ)
├── domains/          # NGHIỆP VỤ — dùng chung, không biết client là ai
│   ├── auth/  users/  pricing/  trips/  matching/
│   ├── fraud/ escrow/ payments/ partners/ notifications/
│   ├── tracking/     ← MỚI
│   ├── chat/         ← MỚI
│   ├── support/      ← MỚI (ticket, SLA, phân công CSKH)
│   └── iam/          ← MỚI (nhân sự nội bộ, vai trò, quyền, audit)
├── realtime/         # WebSocket gateway (đổi tên từ websocket/)
├── integrations/     # maps, ekyc, sms, push, payment gateway, invoice
├── workers/          # Celery
└── core/
```

Quy tắc: **router không chứa logic**. Router = xác thực + kiểm quyền + chuyển đổi DTO + gọi service.
Cùng một `trips.service.complete_trip()` được gọi từ `api/driver` (tài xế bấm kết thúc) và
`api/ops` (CSKH kết thúc hộ khi tài xế mất mạng), khác nhau ở lớp quyền và audit, không khác logic.

### 3.2 Xác thực & phân quyền

| Đối tượng | Cách đăng nhập | Token | Ghi chú |
|---|---|---|---|
| Khách, tài xế | SĐT + OTP | Access 15 phút + Refresh 30 ngày, **xoay vòng refresh** | Gắn `device_id`, phát hiện dùng lại refresh cũ → thu hồi cả họ token |
| Nhân sự nội bộ | Email + mật khẩu + TOTP | Access 15 phút, phiên 8 giờ | Danh sách thu hồi lưu Redis |
| Đối tác | Email + OTP email | Access 30 phút | Scope giới hạn theo `partner_id` |
| Website | Không | — | Chỉ 3 endpoint public + CAPTCHA |

Hiện tại code đang để access token **60 phút và không xoay refresh** — cần sửa trước khi lên
production.

Phân quyền: `permission` dạng `domain:action:scope` (vd `finance:payout:approve`,
`support:conversation:read_all`). Vai trò chỉ là tập hợp permission, lưu DB, sửa được từ IAM.

### 3.3 Chuẩn production cần bổ sung

| Hạng mục | Hiện trạng | Cần làm |
|---|---|---|
| Rate limit | Middleware in-process | Chuyển sang Redis (token bucket theo user + IP + endpoint) |
| Idempotency | Có ở tạo/kết thúc chuyến | Middleware chung: header `Idempotency-Key`, lưu Redis 24h, áp cho mọi POST chạm tiền |
| Quan sát | JSON log + `/health` | + OpenTelemetry trace, Sentry, Prometheus metrics, `/ready` tách khỏi `/health` |
| Ledger | Cập nhật số dư trực tiếp | **Double-entry** như `GoAn_Thiet_Ke_Luong_Thanh_Toan.md` yêu cầu (mục 9.2) |
| Migration | 1 file initial | Mỗi thay đổi = 1 migration, CI chặn nếu model lệch migration |
| Cấu hình | `.env` | Secret manager, tách config theo môi trường, không có secret trong repo |
| CI/CD | Chưa có | GitHub Actions: lint + type + test + migration check → staging → production (duyệt tay) |
| Môi trường | Chỉ local | `dev` / `staging` / `production` tách DB, tách khoá |
| Backup | Chưa có | PostgreSQL daily + PITR — bắt buộc vì có dữ liệu ký quỹ |
| Tải | Chưa đo | Load test matching + WS trước khi mở thành phố thứ 2 |
| API contract | OpenAPI tự sinh | Sinh SDK TypeScript trong CI → `packages/api-client`, FE không viết tay endpoint nữa |

---

## 4. Cấu trúc monorepo đề xuất

```
goan/
├── apps/
│   ├── rider-app/          Expo (React Native)
│   ├── driver-app/         Expo (React Native)
│   ├── ops-console/        React + Vite
│   ├── partner-portal/     React + Vite
│   └── website/            Next.js
├── packages/
│   ├── api-client/         SINH TỰ ĐỘNG từ OpenAPI — không sửa tay
│   ├── realtime-client/    WS client dùng chung (chat + tracking + offer)
│   ├── ui/                 Design system (RN + web qua tamagui/nativewind)
│   └── shared/             Enum, hằng số, hàm format tiền/khoảng cách
├── services/
│   ├── api/                FastAPI — backend duy nhất
│   └── cms/                Payload CMS cho website
├── infra/                  Docker, compose, k8s manifest, terraform
└── docs/                   Tài liệu (3 file .md hiện tại chuyển vào đây)
```

Công cụ: **pnpm workspace + Turborepo** cho phần JS/TS; `services/api` giữ Python độc lập với
`pyproject.toml` riêng.

Lợi ích quyết định: `packages/api-client` sinh từ OpenAPI của backend nên **lỗi lệch endpoint như
hiện nay (mục 9.1) không thể tái diễn** — CI sẽ đỏ ngay khi FE gọi sai.

---

## 5. Realtime — nền tảng chung cho Tracking và Chat

Cả hai module mới dùng **một kết nối WebSocket duy nhất** mỗi client. Không mở nhiều socket.

```
Client ──WSS /ws?token=<access_token>──▶ FastAPI worker (N instance)
                                              │
                                     Redis Pub/Sub  ──── mọi worker nhận được
                                              │
                              ┌───────────────┴───────────────┐
                         topic: user:{id}                topic: conv:{id}
                                                         topic: ops:live_map
```

| Quyết định | Nội dung |
|---|---|
| Định tuyến | Redis pub/sub theo topic — worker nào cũng phục vụ được, không cần sticky session |
| Xác thực | Token trong query khi handshake; hết hạn giữa chừng → server gửi `auth.expired`, client refresh rồi kết nối lại |
| Đóng gói bản tin | `{ "v":1, "type":"...", "id":"<uuid>", "ts":"<iso8601>", "data":{...} }` |
| Chống mất tin | Client gửi kèm `client_msg_id`; server trả `ack`. Không có ack sau 5s → gửi lại (server khử trùng theo `client_msg_id`) |
| Kết nối lại | Backoff luỹ tiến + jitter; sau khi nối lại, client gọi REST đồng bộ phần đã lỡ (`?since=<cursor>`) |
| Nguồn sự thật | **WebSocket chỉ là kênh vận chuyển.** Mọi dữ liệu đều đọc lại được qua REST. Mất WS không mất dữ liệu |
| Hàng rào | Giới hạn 1 kết nối/thiết bị, tối đa 3 thiết bị/tài khoản; rate-limit bản tin |

### Danh mục sự kiện

| Hướng | `type` | Ý nghĩa |
|---|---|---|
| S→C | `trip.offer` | Chuyến mời tài xế (TTL 20s) |
| S→C | `trip.status_changed` | Đổi trạng thái chuyến |
| S→C | `trip.driver_location` | Vị trí tài xế (cho khách + Console) |
| S→C | `trip.completed` | Chốt cước |
| C→S | `location.ping` | Tài xế gửi toạ độ |
| C→S | `trip.offer_response` | Tài xế accept/từ chối |
| S→C | `chat.message` | Tin nhắn mới |
| C→S | `chat.send` | Gửi tin nhắn |
| C→S / S→C | `chat.typing` | Đang gõ |
| C→S / S→C | `chat.read` | Đã đọc đến `message_id` |
| S→C | `chat.member_joined` | CSKH vào hội thoại 3 bên |
| S→C | `support.assigned` | Ticket được gán cho agent |
| S→C | `ops.fleet_update` | Cập nhật bản đồ đội xe (chỉ Console) |
| S→C | `ack` / `error` / `auth.expired` | Hệ thống |

---

## 6. Module Tracking — theo dõi hành trình

### 6.1 Đường đi của một điểm GPS

```
App tài xế (3s/lần khi đang chạy)
   │  gom 5 điểm/lần gửi, có hàng đợi offline
   ▼
WS location.ping ──▶ Redis GEO (vị trí hiện tại, TTL 60s)   ──▶ matching, bản đồ live
                 └─▶ Hàng đợi ghi (Redis Stream)             ──▶ Celery ghi PostgreSQL theo lô
                                                                  (bảng trip_gps_logs)
```

Lý do tách 2 nhánh: nhánh Redis phục vụ real-time (đọc nhiều, ghi đè), nhánh Postgres phục vụ tính
cước + đối soát chạy vòng + bằng chứng khiếu nại (ghi một lần, đọc ít, giữ lâu).

### 6.2 Các mặt theo dõi

| Đối tượng xem | Thấy gì | Nguồn |
|---|---|---|
| Khách trong chuyến | Vị trí tài xế, ETA, lộ trình dự kiến | WS `trip.driver_location` |
| Người thân qua link chia sẻ | Vị trí + trạng thái, **không thấy SĐT/thông tin cá nhân** | `GET /public/trips/shared/{token}` (SSE, hết hạn khi chuyến kết thúc + 2h) |
| Tài xế | Điều hướng đến điểm đón/đến | Maps SDK |
| Console — Live Ops | Toàn bộ tài xế online + chuyến đang chạy, lọc theo trạng thái/khu vực | WS `ops.fleet_update`, gom mỗi 3s |
| Console — Support | Lộ trình một chuyến cụ thể, tua lại (replay) | `GET /ops/trips/{id}/gps-history` |
| Risk | Route thực vs route tối ưu, tỷ lệ lệch | Đã có trong `fraud` |

### 6.3 Lưu trữ và chi phí

| Hạng mục | Chính sách |
|---|---|
| Tần suất ghi DB | Gộp lô 5 điểm; ~1.200 điểm/chuyến 1 giờ ở mức 3s → nén còn ~240 điểm sau khi lọc điểm trùng |
| Giữ dữ liệu | Chi tiết 90 ngày → nén thành polyline lưu vĩnh viễn ở `trips.route_polyline_actual` |
| Bảng | Cân nhắc TimescaleDB hypertable khi > 300 đơn/ngày |
| Riêng tư | Ngừng ghi GPS ngay khi chuyến kết thúc. Không theo dõi tài xế lúc `offline` — phải nêu rõ trong chính sách riêng tư (Nghị định 13/2023) |

### 6.4 Chia sẻ hành trình (an toàn)

Khách bấm "Chia sẻ chuyến" → backend sinh token ngẫu nhiên, tạo link `goan.vn/t/{token}`.
Link hiển thị: bản đồ, trạng thái, tên tài xế, biển số, ETA. Không hiển thị SĐT, không cho nhắn tin.
Hết hạn 2 giờ sau khi chuyến kết thúc, khách thu hồi được bất cứ lúc nào.

---

## 7. Module Chat — CSKH ↔ Tài xế ↔ Khách

### 7.1 Ba loại hội thoại

| Loại | Thành viên | Vòng đời | Mục đích |
|---|---|---|---|
| `trip` | Khách + tài xế (+ CSKH khi cần) | Mở khi `matched`, **đóng 24h sau khi chuyến kết thúc** | Trao đổi điểm đón, "tôi đứng ở cổng B" |
| `support` | Một người dùng (khách **hoặc** tài xế) + agent CSKH | Mở khi người dùng bấm "Hỗ trợ" hoặc hệ thống tự mở khi có sự cố | Khiếu nại, hỏi đáp, xử lý phạt |
| `internal` | Chỉ nhân sự nội bộ, gắn với 1 ticket | Theo ticket | Ghi chú nội bộ, escalate — **người dùng không bao giờ thấy** |

**Kịch bản 3 bên** (yêu cầu cốt lõi của anh): CSKH đang xử lý một chuyến có sự cố → bấm "Tham gia
hội thoại chuyến" → hệ thống thêm agent vào conversation `trip`, cả khách và tài xế đều thấy thông
báo hệ thống *"Nhân viên hỗ trợ GoAn đã tham gia"*. Từ đó ba bên nhắn chung. Khi đóng ticket, agent
rời hội thoại, cũng có bản tin hệ thống.

### 7.2 Mô hình dữ liệu

```sql
conversations(
  id, type ENUM(trip, support, internal),
  trip_id NULL REFERENCES trips,
  ticket_id NULL REFERENCES support_tickets,
  status ENUM(open, closed) DEFAULT 'open',
  last_message_at, last_message_preview,     -- phi chuẩn hoá, để render danh sách nhanh
  created_at, closed_at
)

conversation_members(
  id, conversation_id, user_id,
  role ENUM(rider, driver, agent, system),
  joined_at, left_at NULL,
  last_read_message_id NULL,                 -- cơ sở tính số tin chưa đọc
  muted BOOLEAN DEFAULT false,
  UNIQUE(conversation_id, user_id)
)

messages(
  id BIGSERIAL,                              -- tăng dần, dùng làm con trỏ phân trang
  conversation_id, sender_id NULL,           -- NULL = tin hệ thống
  client_msg_id VARCHAR(64),                 -- khử trùng khi client gửi lại
  kind ENUM(text, image, location, system, quick_reply),
  body TEXT NULL,
  attachment_id NULL, lat NULL, lng NULL,
  meta JSONB,                                -- vd {"system":"agent_joined","agent":"..."}
  created_at, edited_at NULL, deleted_at NULL,
  UNIQUE(conversation_id, client_msg_id)
)

message_attachments(id, conversation_id, uploader_id, storage_key, mime, size_bytes, scanned_at)

support_tickets(
  id, code,                                  -- mã hiển thị cho khách, vd GA-240918-0042
  subject_type ENUM(rider, driver), subject_id,
  trip_id NULL,
  category ENUM(payment, fraud, safety, app_issue, driver_conduct, rider_conduct, other),
  priority ENUM(low, normal, high, urgent),
  status ENUM(new, assigned, waiting_customer, escalated, resolved, closed),
  assigned_agent_id NULL, team ENUM(cs, risk, finance, driver_ops),
  first_response_at NULL, resolved_at NULL,
  sla_due_at, reopened_count, resolution_note,
  created_at, updated_at
)

ticket_events(id, ticket_id, actor_id, event_type, payload JSONB, created_at)  -- audit
canned_responses(id, team, title, body, shortcut, active)
agent_presence(agent_id, status ENUM(available, busy, away, offline), active_chats, max_chats)
```

Chỉ mục quan trọng: `messages(conversation_id, id DESC)`, `conversations(status, last_message_at DESC)`,
`conversation_members(user_id, left_at)`, `support_tickets(status, sla_due_at)`.

### 7.3 Luồng gửi tin

```
1. Client tạo client_msg_id (uuid) → gửi WS chat.send
2. Server: kiểm tra là thành viên còn hoạt động của conversation
3. Kiểm duyệt: lọc số điện thoại / link thanh toán ngoài app (mục 7.6)
4. INSERT messages (UNIQUE conversation_id+client_msg_id chặn trùng)
5. Trả ack {client_msg_id, message_id, ts} cho người gửi
6. Publish Redis topic conv:{id} → các thành viên đang online nhận chat.message
7. Thành viên offline → hàng đợi Celery gửi push FCM sau 5 giây nếu vẫn chưa đọc
```

Không dùng WS thì client vẫn gửi được qua `POST /chat/conversations/{id}/messages` (cùng logic) —
đây là đường lui khi mạng chặn WebSocket.

### 7.4 API chat & hỗ trợ

| Surface | Method | Path | Ghi chú |
|---|---|---|---|
| rider / driver | GET | `/chat/conversations` | Danh sách + số chưa đọc |
| rider / driver | GET | `/chat/conversations/{id}/messages?before=<id>&limit=50` | Phân trang con trỏ |
| rider / driver | POST | `/chat/conversations/{id}/messages` | Đường lui của WS |
| rider / driver | POST | `/chat/conversations/{id}/read` | Đánh dấu đã đọc |
| rider / driver | POST | `/chat/attachments` | Upload ảnh (presigned URL) |
| rider / driver | POST | `/support/tickets` | Mở ticket → tự tạo conversation `support` |
| ops | GET | `/ops/support/queue?team=cs&status=new` | Hàng đợi CSKH |
| ops | POST | `/ops/support/tickets/{id}/claim` | Agent nhận ticket |
| ops | POST | `/ops/support/tickets/{id}/transfer` | Chuyển đội/agent khác |
| ops | POST | `/ops/chat/conversations/{id}/join` | **Tham gia hội thoại 3 bên** |
| ops | POST | `/ops/chat/conversations/{id}/leave` | Rời hội thoại |
| ops | GET | `/ops/chat/search?user_id=&trip_id=&q=` | Tra cứu lịch sử chat phục vụ khiếu nại |
| ops | POST | `/ops/support/tickets/{id}/resolve` | Kết luận + ghi chú |

### 7.5 Vận hành CSKH (phần "chuẩn công ty")

| Hạng mục | Quy định |
|---|---|
| Phân phối | Tự động theo `agent_presence` (còn slot, đúng đội, ưu tiên agent đã xử lý ticket cũ của khách này) |
| SLA | `urgent` (an toàn/tai nạn): phản hồi đầu ≤ 2 phút · `high` (tiền): ≤ 15 phút · `normal`: ≤ 60 phút · `low`: ≤ 8 giờ. Quá hạn → tự escalate lên `cs_lead` |
| Giờ làm | Ngoài giờ: chỉ trực `urgent` + bot trả lời tự động cho phần còn lại, xếp hàng cho ca sau |
| Chất lượng | Ghi nhận: thời gian phản hồi đầu, thời gian xử lý, tỷ lệ reopen, CSAT sau khi đóng ticket |
| Bàn giao ca | Ticket chưa xong tự chuyển về hàng đợi khi agent `offline` quá 10 phút |
| Mẫu trả lời | `canned_responses` theo đội, gõ tắt `/hoantien`, `/kiemtra` |
| Leo thang | CS → CS Lead → đội chuyên trách (Risk / Finance / Driver Ops), mỗi bước ghi `ticket_events` |

### 7.6 An toàn & tuân thủ trong chat

| Rủi ro | Xử lý |
|---|---|
| Thanh toán ngoài app (deck cảnh báo) | Regex phát hiện số tài khoản / link ví trong tin nhắn → gắn cờ `fraud_review_queue`, **không chặn tin** để tránh sai lệch bằng chứng |
| Lộ số điện thoại | Chat `trip` là kênh chính; nếu cần gọi thì dùng **số ảo (masked calling)** qua nhà cung cấp viễn thông, không lộ số thật |
| Nội dung xúc phạm/quấy rối | Người dùng báo cáo tin nhắn → vào hàng đợi CS, có thể khoá tài khoản |
| Ảnh độc hại | Quét virus + giới hạn 5MB, chỉ ảnh; lưu S3 private, phát qua presigned URL 15 phút |
| Lưu trữ | Chat `trip`: 12 tháng · Chat `support`: 24 tháng (bằng chứng khiếu nại) · Sau đó ẩn danh hoá |
| Quyền đọc | Agent chỉ đọc được hội thoại mình được gán hoặc có quyền `support:conversation:read_all`; mọi lần đọc ghi audit |
| Nghị định 13/2023 | Nêu rõ trong chính sách: chat được lưu và có thể được nhân viên hỗ trợ đọc để xử lý khiếu nại |

---

## 8. Ma trận tính năng × sản phẩm

Bảng này là căn cứ khi có tranh cãi "cái này để ở đâu".

| Tính năng | Rider | Driver | Console | Partner | Web |
|---|:--:|:--:|:--:|:--:|:--:|
| Đăng nhập OTP SĐT | ✅ | ✅ | ❌ (email+2FA) | ❌ (email OTP) | ❌ |
| Đặt chuyến | ✅ | — | 🔧 đặt hộ | — | ❌ |
| Nhận chuyến | — | ✅ | 🔧 gán thủ công | — | — |
| Quét QR bắt đầu chuyến | ✅ quét | ✅ hiển thị | 👁 xem log | — | — |
| Bản đồ real-time | 👁 chuyến mình | 👁 điều hướng | 👁 **toàn đội** | — | 👁 link chia sẻ |
| Chat với đối phương | ✅ | ✅ | ✅ 3 bên | — | — |
| Chat với CSKH | ✅ | ✅ | ✅ (là CSKH) | 📧 email | — |
| Mở ticket | ✅ | ✅ | ✅ tạo hộ | ✅ | — |
| Xem cước & hoá đơn | ✅ | 👁 phần mình | 👁 tất cả | 👁 của mình | — |
| Ví & rút tiền | — | ✅ | 🔧 duyệt | — | — |
| Ký quỹ | — | 👁 | 🔧 duyệt hoàn | — | — |
| eKYC | — | ✅ nộp | 🔧 duyệt | — | — |
| Selfie ngẫu nhiên | — | ✅ | 👁 kết quả | — | — |
| Bảng giá | 👁 ước tính | 👁 thu nhập | 🔧 cấu hình | — | 👁 tham khảo |
| Chống gian lận | — | 👁 quyết định | 🔧 xử lý | — | — |
| Hoa hồng đối tác | — | — | 🔧 | 👁 | — |
| QR bàn nhà hàng | ✅ quét | — | 🔧 cấp | ✅ in | — |
| Báo cáo / KPI | — | 👁 cá nhân | ✅ | 👁 của mình | — |
| Nội dung marketing | — | — | — | — | ✅ |
| Đăng ký làm tài xế | — | — | 🔧 duyệt | — | ✅ form |

✅ làm chính · 👁 chỉ xem · 🔧 quản trị/duyệt · 📧 kênh khác · ❌ không có · — không liên quan

---

## 9. Việc phải dọn trước khi triển khai

### 9.1 Frontend đang trỏ sai backend

`goan-customer-app` viết theo API của `goan-backend` (bản nháp cũ). Không endpoint nào khớp
`goan-backend-spec`:

| FE đang gọi | Backend thật | |
|---|---|---|
| `POST /auth/otp/request` | `POST /auth/request-otp` | 404 |
| `POST /auth/otp/verify` | `POST /auth/verify-otp` | 404 |
| `POST /trips/fare-estimate` | `POST /pricing/estimate` | 404 |
| `GET /trips?mine=true` | *chưa có* | 404 |
| `WS /ws/trips/{id}/track` | `WS /ws?token=<jwt>` | Fail, FE cũng chưa gửi token |
| body có `payment_method` | Spec đang tắt tiền mặt | Bị bỏ qua |

**Xử lý**: xoá `goan-backend`; đổi tên `goan-backend-spec` → `services/api`; sinh
`packages/api-client` từ OpenAPI; viết lại tầng gọi API của app khách theo client sinh tự động.

### 9.2 Code lệch tài liệu thanh toán

| Tài liệu yêu cầu | Code hiện tại | Ưu tiên |
|---|---|---|
| Hỗ trợ tiền mặt + `driver_debts` | `PaymentMethod.CASH_DISABLED`, không có bảng công nợ | **Cần anh quyết** — xem 9.3 |
| Ledger double-entry, không sửa số dư trực tiếp | Cột số dư cập nhật trực tiếp, bút toán một chiều | Cao — ảnh hưởng audit Series A |
| State machine payment đầy đủ (pre-auth → capture → settle → payout, retry, dispute) | 4 trạng thái, charge một lần, không retry | Cao |
| Bảng `payouts`, `invoices` | Chưa có | Trung bình |
| Phí huỷ trả cho tài xế | Chỉ ghi vào `trips`, chưa có bút toán ví | Trung bình |
| 100% − 58% (tài xế) − 38% (nền tảng) = **4% chưa được hạch toán** | Job đối soát không kiểm phần này | Cần xác nhận là cố ý |

### 9.3 Quyết định còn treo

| Câu hỏi | Ảnh hưởng |
|---|---|
| **Có làm nhánh tiền mặt không?** | Kéo theo bảng `driver_debts`, luồng ghi nợ hoa hồng, chặn nhận chuyến khi nợ > ngưỡng, và màn hình "xác nhận đã thu tiền mặt" ở app tài xế. Nếu làm, phải làm trước khi lên production vì chạm ledger |
| Số ảo (masked calling) hay để lộ SĐT thật? | Ảnh hưởng chi phí vận hành và thiết kế chat |
| Bản đồ: Goong hay Mapbox? | Goong rẻ và dữ liệu VN tốt; Mapbox SDK trưởng thành hơn cho RN |
| Ký quỹ: giữ ở tài khoản ngân hàng riêng biệt? | Bắt buộc về pháp lý — quỹ là tài sản của tài xế, không phải doanh thu |

---

## 10. Lộ trình đề xuất

| Giai đoạn | Thời lượng | Nội dung | Xong là có gì |
|---|---|---|---|
| **P0 — Dọn nền** | 2 tuần | Monorepo, xoá backend cũ, sinh `api-client`, CI/CD, staging, migration chuẩn, xoay refresh token, rate-limit Redis | Một backend, một nguồn contract, deploy tự động |
| **P1 — IAM & Console khung** | 3 tuần | `domains/iam`, permission, audit log, Console: đăng nhập 2FA, Live Ops map, Driver Ops duyệt hồ sơ | Nội bộ dùng được, không còn thao tác DB bằng tay |
| **P2 — Chat & Support** | 4 tuần | `domains/chat` + `domains/support`, WS chat, push, Support Desk trên Console, SLA, canned response | **CSKH ↔ khách ↔ tài xế chạy thật** |
| **P3 — Driver App** | 5 tuần | Expo app tài xế: onboarding, ca làm, offer, GPS nền, QR, selfie, ví/ký quỹ, chat | Tài xế không cần công cụ tạm nữa |
| **P4 — Rider App** | 4 tuần | Expo app khách: đặt xe, theo dõi, QR, thanh toán, chia sẻ hành trình, chat | Khách dùng app thật, bỏ web MVP |
| **P5 — Ledger & Finance** | 3 tuần | Double-entry, payouts, invoices, maker–checker, đối soát, (tiền mặt nếu chốt làm) | Sổ sách chuẩn để kiểm toán |
| **P6 — Partner & Website** | 3 tuần | Partner Portal, CMS + goan.vn, form tuyển tài xế | Kênh B2B và tuyển dụng tự chạy |
| **P7 — Hardening** | 2 tuần | Load test, observability đầy đủ, backup/PITR, diễn tập sự cố, pentest | Sẵn sàng mở thành phố thứ 2 |

Chạy tuần tự P0 → P1 → P2 rồi P3/P4 song song nếu có 2 người mobile. Tổng ~24–26 tuần với đội tối
thiểu trong tài liệu kiến trúc (1 tech lead, 2 backend, 2 mobile, 1 frontend, 1 DevOps bán thời gian,
1 QA bán thời gian).

**Vì sao Chat đứng trước app**: CSKH cần công cụ ngay khi có tài xế thật chạy thử, và web MVP hiện tại
vẫn dùng tạm được cho khách. Ngược lại, có app đẹp mà không có kênh hỗ trợ thì mọi sự cố đều phải xử
lý qua điện thoại cá nhân — đúng thứ mà một công ty chuẩn không làm.

---

## 11. Rủi ro cần theo dõi

| Rủi ro | Dấu hiệu sớm | Giảm thiểu |
|---|---|---|
| GPS nền app tài xế bị OS giết | Chuyến mất điểm giữa đường, cước lệch | Foreground service + hàng đợi offline; đo tỷ lệ chuyến thiếu điểm mỗi ngày |
| WebSocket không scale | Độ trễ tin nhắn tăng, rớt kết nối | Redis pub/sub (đã chọn), load test 5.000 kết nối trước P3 |
| CSKH quá tải | SLA phản hồi đầu vượt ngưỡng | Bot trả lời câu hỏi thường gặp, canned response, tự escalate |
| Ledger sai lệch | Job đối soát ngày báo `balanced = false` | Chuyển double-entry ở P5, cảnh báo ngay khi lệch ≠ 0 |
| Lộ PII qua Console | Truy vấn xem CCCD bất thường | Che mặc định + bắt nhập lý do + báo cáo tuần cho quản lý |
| Một backend thành nút thắt | p95 latency tăng theo tải | Ranh giới domain đã rõ → tách `matching` và `chat` ra service riêng trước tiên khi cần |

---

*Tài liệu chốt phân định hệ thống GoAn — 09/2026. Đọc cùng `GoAn_Kien_Truc_Ky_Thuat_Va_Ke_Hoach_Trien_Khai.md`
(nghiệp vụ, công thức cước) và `GoAn_Thiet_Ke_Luong_Thanh_Toan.md` (luồng tiền).*
