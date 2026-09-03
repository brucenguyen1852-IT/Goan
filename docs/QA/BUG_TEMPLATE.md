# Mẫu báo lỗi

> Sao chép nguyên khối này khi tạo issue. Một báo lỗi thiếu bước tái hiện thì lập trình viên
> phải đoán, và thường đoán sai.

```markdown
## Tiêu đề
[Mức độ] Mô tả ngắn, nêu hệ quả — không nêu nguyên nhân phỏng đoán
Ví dụ tốt:  [Blocker] Khách bị trừ tiền hai lần khi bấm "Hoàn thành" lúc mất sóng
Ví dụ xấu:  Lỗi ở hàm complete_trip

## Mức độ
Blocker / Critical / Major / Minor / Trivial   (định nghĩa: docs/QA/QA_ROLE.md §5)

## Môi trường
- Nhánh / commit:
- Môi trường: local | staging | production
- Thiết bị / trình duyệt:
- Vai trò tài khoản: khách | tài xế | CSKH | admin

## Bước tái hiện
1.
2.
3.

## Kết quả mong đợi
(Trích PRD nếu có: "theo docs/GoAn_Thiet_Ke_Luong_Thanh_Toan.md §4 thì...")

## Kết quả thực tế

## Bằng chứng
- request_id:            ← lấy từ header X-Request-ID của response
- Ảnh chụp / video:
- Log liên quan:
- Bản ghi audit (nếu có thao tác ghi):

## Ảnh hưởng
- Bao nhiêu người dùng bị ảnh hưởng:
- Có mất tiền hay mất dữ liệu không:
- Có cách đi vòng tạm thời không:

## Ánh xạ PRD
PRD-XXX-NN (nếu có trong docs/QA/TRACEABILITY.md)
```

## Sau khi lỗi được sửa

Bắt buộc, không có ngoại lệ:

1. **Viết test tái hiện lỗi TRƯỚC khi sửa.** Test phải đỏ trên code cũ.
2. Sửa code cho tới khi test xanh.
3. Ghi mã test vào issue.
4. Nếu lỗi lọt qua được CI thì hỏi tiếp: **vì sao cổng chất lượng không bắt được?**
   Trả lời câu này thường có giá trị hơn chính bản sửa lỗi.
