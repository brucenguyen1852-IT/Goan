# KHÔNG DÙNG THƯ MỤC NÀY

Đây là bản backend đầu tiên của GoAn. Nó đã được `services/api` thay thế **hoàn toàn**.

| | `_deprecated-api-v0` (thư mục này) | `services/api` |
|---|---|---|
| Endpoint | 9 | 33 |
| Dòng code | ~1.400 | ~6.300 |
| Test | 1 file | 51 test, chạy xanh |
| Migration | không có | có, 18 bảng |
| Nghiệp vụ | auth, tạo/huỷ chuyến, ví (khung) | đầy đủ: pricing, matching, QR, ký quỹ, chống gian lận, thanh toán, đối tác, đối soát |

## Vì sao còn giữ

`apps/customer-web` hiện vẫn viết theo API của thư mục này (và vì vậy đang gọi sai backend thật).
Giữ lại để đối chiếu trong lúc chuyển `apps/customer-web` sang `@goan/api-client`.

**Xoá thư mục này ngay sau khi task P4-12 hoàn thành.** Không sửa, không import, không deploy.
