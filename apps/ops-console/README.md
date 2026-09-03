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

**Nhớ máy 30 ngày chỉ bỏ qua bước nhập mã, không bỏ qua mật khẩu.** Token nhớ máy lưu tách
khỏi phiên và KHÔNG bị xoá khi đăng xuất: đăng xuất là hết ca làm việc, không phải tuyên bố
"máy này không còn tin được". Muốn quên máy thì gỡ ở màn hình thiết bị — thao tác đó gọi lên
server để token chết thật.

**Một lần refresh tại một thời điểm.** Backend xoay vòng refresh token; hai request cùng gọi
refresh thì request thứ hai dùng token đã tiêu và cả phiên bị thu hồi. Biến `refreshing` trong
`src/api/client.ts` giữ ràng buộc đó.

## Kiểm thử

```bash
pnpm --filter @goan/ops-console test
```

Bộ test trả lời đúng một câu: **mỗi vai trò có thấy đúng phần được phép không?** Nó không thay
thế 92 test phân quyền ở backend — ẩn menu không phải là phân quyền — mà bảo đảm người vận hành
không nhìn thấy những nút bấm vào chỉ nhận 403.

## Bản đồ

Leaflet + nền OpenStreetMap: chạy được ngay, không cần khoá API, không cần hợp đồng với ai.
Đổi sang Goong (tên đường Việt Nam sát thực tế hơn) chỉ là đổi URL tile và thêm khoá trong
`src/components/FleetMap.tsx` — không phải viết lại màn hình.

Vị trí tài xế đến từ WebSocket `/ws/ops/fleet`, backend gom 3 giây một lần. Nếu WS không mở
được (mạng công ty chặn, proxy cũ) thì Console tự lùi về hỏi lại mỗi 5 giây — chỉ báo ●/○ ở
đầu trang cho biết đang chạy ở chế độ nào.

## Phần còn thiếu

| Hạng mục | Hiện tại |
|---|---|
| Nền bản đồ tiếng Việt | OpenStreetMap; chuyển Goong khi có khoá API |
| Thao tác hàng loạt | Duyệt từng hồ sơ một; chưa có chọn nhiều |
