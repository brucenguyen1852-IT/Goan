# @goan/customer-web

Web MVP cho khách hàng. Bản React Native chính thức sẽ thay thế ở giai đoạn P4; đến lúc đó
app này vẫn là kênh đặt xe dự phòng chạy trên trình duyệt.

## Chạy

```bash
# 1. Backend (cửa sổ khác)
cd ../../services/api && uvicorn app.main:app --port 8000

# 2. App
pnpm dev        # http://localhost:5173
```

Vite proxy sẵn `/api` và `/ws` sang `localhost:8000` nên không vướng CORS khi dev.

## Tài khoản mẫu (sau khi chạy `python -m scripts.seed` ở backend)

| Vai trò | SĐT |
|---|---|
| Khách | 0901000001, 0901000002 |
| Tài xế | 0902000001, 0902000002, 0902000003 |

Ở môi trường dev (`DEBUG=true`) backend trả kèm `debug_otp`, app tự điền vào ô OTP nên không
cần dựng SMS thật.

## Điểm cần biết khi sửa

**Không viết tay đường dẫn API.** Contract nằm ở `packages/api-client/openapi.json`, sinh từ
backend. Trước đây app này tự đặt tên endpoint và đã lệch hoàn toàn khỏi backend
(`/auth/otp/request` vs `/auth/request-otp`, `/trips/fare-estimate` vs `/pricing/estimate`) —
không ai phát hiện cho tới khi chạy thật.

**Tiền là chuỗi, không phải số.** Backend trả `Decimal` dưới dạng chuỗi để không mất chính xác
khi qua JSON. Dùng `formatVnd()` trong `src/types` để hiển thị, đừng ép sang `number` rồi tính toán.

**Access token sống 15 phút.** `src/api/client.ts` tự làm mới khi gặp 401 và phát lại request.
Backend xoay vòng refresh token nên chỉ được có đúng một lần refresh chạy tại một thời điểm —
nếu hai request cùng gọi refresh, request thứ hai dùng token đã tiêu và backend sẽ thu hồi cả
phiên. Biến `refreshing` trong file đó giữ ràng buộc này, đừng bỏ đi.

**Đăng xuất phải gọi backend.** Chỉ xoá token trong máy thì refresh token vẫn sống 30 ngày ở
phía server.

## Phần còn thiếu (P4)

| Hạng mục | Hiện tại |
|---|---|
| Bản đồ | `MapPlaceholder` — chưa tích hợp Goong/Mapbox |
| Địa chỉ | Hai điểm cố định ở TP.HCM, chưa có autocomplete |
| Quét QR | Nhập tay mã; app React Native sẽ dùng camera |
| Thanh toán | Chưa có màn hình liên kết thẻ/ví |
| Chia sẻ hành trình, SOS | Chưa có |
