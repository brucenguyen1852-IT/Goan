# Kết quả chạy thật trên PostgreSQL — 04/09/2026 (sau đợt P2)

Chạy lại toàn bộ trên đúng bộ hạ tầng production sau khi thêm chat, hỗ trợ, ảnh đính kèm và
push: PostgreSQL 16 + PostGIS + Redis + uvicorn.

| Bài | Kết quả |
|---|---|
| `alembic upgrade head` | 12/12 migration sạch |
| `alembic check` | "No new upgrade operations detected" |
| Quay lui từng migration mới (0009→0012) rồi lên lại | sạch cả hai chiều |
| `pytest` | **392 test đạt**, độ phủ 84% |
| `pnpm test` | 32 test frontend đạt (17 Console + 15 realtime-client) |
| `make smoke` | **33/33 bước đạt** (thêm 11 bước cho chat và hỗ trợ) |
| `make audit` | **98/98 lời gọi đúng như mong đợi** (thêm 22 lời gọi) |

## Hai lỗi thật do chính hai bài rà soát này bắt được

**1. Rò rỉ 403 / 404 ở chat.** `make audit` chỉ ra hội thoại không tồn tại trả 404 còn hội
thoại của người khác trả 403. Thông điệp giống nhau nhưng mã trạng thái thì không, nên người
dò chỉ cần quét id rồi lọc theo mã là biết chính xác hội thoại nào đang sống — dù không đọc
được một chữ nào bên trong. Đã sửa: cả hai trả cùng một lỗi 403, và test đã siết lại để so
**cả mã trạng thái** chứ không chỉ so thông điệp.

**2. Gửi lại ảnh sau khi mất sóng bị từ chối.** Bài kịch bản E2E (P2-21) bắt được: người dùng
mất sóng lúc gửi ảnh, bấm gửi lại với đúng `client_msg_id` cũ, và nhận 409 "tệp đính kèm đã
được gửi rồi" — đúng lúc họ đang cố gửi ảnh hiện trường một vụ tai nạn. Nguyên nhân: router
gắn ảnh **trước** khi khử trùng tin. Đã sửa: lần gửi lại mang đúng `client_msg_id` cũ được
nhận, còn `client_msg_id` khác vẫn bị chặn (đó mới là dùng lại ảnh cho tin thứ hai).

Cả hai đều không thể phát hiện bằng test gọi thẳng hàm: một cái nằm ở mã trạng thái HTTP, một
cái nằm ở **thứ tự hai bước** trong router.

## Lưu ý khi chạy lại

Hạn mức OTP và rate limit nằm ở Redis và sống qua các lần chạy. Chạy `make smoke` rồi
`make audit` liên tiếp trong 5 phút thì bài sau nhận 429 ở bước đăng nhập. Dọn bằng
`redis-cli flushdb` giữa hai lần chạy.
