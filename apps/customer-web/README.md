# GoAn Customer App (Web MVP — React + Vite + TypeScript)

Skeleton frontend cho khách hàng đặt tài xế lái hộ. Đây là bản **web** (chạy trong trình duyệt,
tối ưu bố cục cho màn hình điện thoại) để MVP có thể dùng thử kinh doanh ngay mà không cần build
native app + qua duyệt App Store/Play Store trước. Khi sản phẩm cần app native thật (map SDK mượt
hơn, push notification, chạy nền GPS...), phần lớn `api/`, `store/`, `types/` có thể tái sử dụng
gần như nguyên vẹn khi port sang React Native.

## Cấu trúc thư mục

```
src/
  api/          # gọi REST API backend (axios) — auth, trips, history
  store/        # Zustand global state — authStore, tripStore
  pages/        # các màn hình: Login, OtpVerify, Home (đặt xe), TripTracking, History, Profile
  components/
    layout/     # AppLayout (bottom nav), RequireAuth (route guard)
    map/        # MapPlaceholder — chỗ cắm map SDK thật
    ui/         # Button, Input, TripStatusBadge — design system tối giản
  hooks/        # useTripTrackingSocket — WebSocket theo dõi chuyến real-time
  types/        # TypeScript types khớp với Pydantic schemas của backend
```

## Chạy local

```bash
npm install
npm run dev
```

Mặc định `vite.config.ts` proxy `/api` và `/ws` sang `http://localhost:8000` (backend FastAPI) —
chạy backend trước (xem `goan-backend/README.md`) rồi mới chạy frontend.

## Luồng đã implement trong skeleton này

1. Đăng nhập bằng SĐT + OTP (`LoginPage` → `OtpVerifyPage`)
2. Xem giá cước ước tính + chọn phương thức thanh toán (Online/Tiền mặt) (`HomePage`)
3. Đặt chuyến, theo dõi trạng thái + vị trí tài xế real-time qua WebSocket (`TripTrackingPage`)
4. Hủy chuyến khi còn ở trạng thái cho phép
5. Lịch sử chuyến đi (`TripHistoryPage`) — **lưu ý**: cần bổ sung endpoint `GET /trips` (list theo
   customer) ở backend trước khi dùng thật, hiện backend skeleton mới có `GET /trips/{id}`.
6. Trang tài khoản + đăng xuất (`ProfilePage`)

## Việc cần làm tiếp (chưa có trong skeleton)

- Tích hợp map SDK thật (Goong Maps/Mapbox) thay cho `MapPlaceholder`, gồm: hiển thị vị trí hiện
  tại của khách, chọn điểm đón/đến trên bản đồ, animate vị trí tài xế.
- Ô tìm kiếm địa chỉ có autocomplete (hiện `HomePage` demo với 2 điểm cố định).
- Màn hình quét mã QR tài xế (dùng `getUserMedia`/thư viện quét QR) khi trạng thái `driver_arriving`.
- Tích hợp cổng thanh toán thật khi chọn "Thanh toán online" (redirect/deep-link sang VNPay/MoMo).
- Đánh giá tài xế sau khi hoàn thành chuyến (trạng thái `completed` → `rated`).
- i18n nếu cần hỗ trợ thêm ngôn ngữ ngoài tiếng Việt.
