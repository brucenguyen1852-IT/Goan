# @goan/ops-console

Console vận hành nội bộ. Đối tượng dùng: điều phối, CSKH, Driver Ops, kiểm soát rủi ro, tài
chính, quản trị hệ thống — 12 vai trò, mỗi người chỉ thấy đúng phần được phép.

## Chạy

```bash
# 1. Backend (cửa sổ khác)
cd ../../services/api
python -m scripts.seed_iam admin@goan.vn "Tên của bạn"   # in ra mật khẩu + URI TOTP một lần
uvicorn app.main:app --port 8000

# 2. Console
pnpm dev        # http://localhost:5174
```

Quét URI TOTP vào Google Authenticator/1Password rồi đăng nhập bằng email + mật khẩu + mã 6 số.
Vite proxy sẵn `/api` sang `localhost:8000`.

## Màn hình

| Đường dẫn | Nội dung | Quyền cần có |
|---|---|---|
| `/fleet` | Tài xế online, ai đang chạy chuyến nào | `ops:fleet:read` |
| `/drivers` | Duyệt / từ chối hồ sơ, khoá / mở tài khoản | `driver:profile:read` |
| `/trips` | Tra cứu chuyến, tua lại lộ trình GPS | `trip:trip:read_all` |
| `/approvals` | Hàng đợi phê duyệt thao tác chạm tiền | (ai cũng xem được, duyệt thì cần quyền) |
| `/staff` | Nhân sự nội bộ, tạo tài khoản, gán vai trò | `iam:staff:read` |
| `/roles` | Ma trận vai trò – quyền | `iam:role:read` |
| `/audit` | Nhật ký thao tác | `audit:log:read` |

## Điểm cần biết khi sửa

**Ẩn nút không phải là phân quyền.** Menu và nút bấm ẩn/hiện theo `permissions` lấy từ
`/ops/auth/me` — đó chỉ là trải nghiệm người dùng. Backend vẫn kiểm quyền cho từng request, và
đó mới là chỗ chặn thật.

**Thao tác nhạy cảm phải hỏi lý do.** Từ chối hồ sơ, khoá tài khoản, xem PII đầy đủ: backend
bắt buộc có `reason` và ghi vĩnh viễn vào nhật ký. Đừng thêm đường tắt bỏ qua bước này.

**Bí mật TOTP chỉ hiện một lần** ngay sau khi tạo tài khoản. Không có endpoint nào đọc lại được.

**Một lần refresh tại một thời điểm.** Backend xoay vòng refresh token; hai request cùng gọi
refresh thì request thứ hai dùng token đã tiêu và cả phiên bị thu hồi. Biến `refreshing` trong
`src/api/client.ts` giữ ràng buộc đó.

## Phần còn thiếu

| Hạng mục | Hiện tại |
|---|---|
| Bản đồ Live Ops | Bảng toạ độ, chưa tích hợp Goong/Mapbox (P1-16) |
| Đẩy real-time | Hỏi lại mỗi 5 giây; WS `ops.fleet_update` thuộc P2 |
| Design system dùng chung | `src/components/ui.tsx`, sẽ tách ra `packages/ui` khi Partner Portal cần (P1-14) |
| Sửa quyền của vai trò từ giao diện | Màn hình vai trò đang chỉ đọc; API `iam:role:write` chưa có |
