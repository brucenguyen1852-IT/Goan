# Vai trò QA tại GoAn

> Đội 4 người không có QA chuyên trách. Vai trò QA do Frontend Engineer kiêm nhiệm, nhưng
> **kiêm nhiệm không có nghĩa là làm qua loa** — tài liệu này định nghĩa QA là một vai trò có
> quyền hạn rõ ràng, không phải "người test cuối cùng trước khi deploy".

---

## 1. QA ở GoAn là gì

| QA **là** | QA **không phải là** |
|---|---|
| Người bảo vệ định nghĩa "xong" | Người bấm thử app sau khi dev code xong |
| Người có quyền chặn release | Người báo cáo lỗi rồi hết trách nhiệm |
| Người viết test case **từ PRD, trước khi code** | Người viết test sau khi đọc code (sẽ chỉ test lại đúng cái code đang làm) |
| Người quyết định rủi ro nào chấp nhận được | Người đòi 100% coverage |

**Nguyên tắc nền:** một tính năng chưa có test tương ứng với mục PRD của nó thì **chưa xong**,
dù nó đã chạy trên máy của lập trình viên.

## 2. Quyền hạn

| Quyền | Diễn giải |
|---|---|
| **Chặn merge** | QA đánh dấu `qa-blocked` trên MR. Chỉ Tech Lead được gỡ, và phải ghi lý do vào MR |
| **Chặn release** | Bug mức Blocker/Critical còn mở thì không lên production |
| **Yêu cầu bổ sung test** | Với mọi thay đổi chạm tiền, quyền hạn, hoặc dữ liệu tài xế |
| **Quyết định phạm vi hồi quy** | QA chọn bộ test chạy trước mỗi release |

QA **không** có quyền: quyết định thiết kế kỹ thuật, ước tính thay lập trình viên, hoặc từ chối
một yêu cầu nghiệp vụ.

## 3. Quy trình theo vòng đời một tính năng

```
PRD (docs/*.md)
   │
   ├─(1) QA đọc PRD, viết test case TRƯỚC khi code  ──► TRACEABILITY.md
   │
   ├─(2) Dev code + viết test tự động theo case đó
   │
   ├─(3) MR mở: CI phải xanh, checklist trong PR template phải đủ
   │
   ├─(4) QA review MR: đọc test trước, đọc code sau
   │        Câu hỏi cố định: "Test này đỏ khi nào?" Nếu không trả lời được thì test vô nghĩa
   │
   ├─(5) QA test thăm dò (exploratory) 30 phút trên staging — tìm cái test tự động không thấy
   │
   └─(6) QA đánh dấu Pass/Blocked. Blocked thì ghi bug theo mẫu BUG_TEMPLATE.md
```

**Bước (1) là bước quan trọng nhất.** Viết test case sau khi thấy code thì QA chỉ xác nhận lại
những gì lập trình viên đã nghĩ tới. Viết trước thì QA phát hiện được cái lập trình viên chưa nghĩ tới.

## 4. Định nghĩa hoàn thành (Definition of Done)

Một task chỉ được chuyển sang "Đã xong" trong `GoAn_Project_Tracker.xlsx` khi **đủ tất cả**:

| # | Tiêu chí | Ai kiểm |
|---|---|---|
| 1 | Đạt đúng cột "Định nghĩa hoàn thành" trong Backlog | Dev |
| 2 | `make check` xanh (ruff + mypy + pytest) | CI |
| 3 | Có test tự động cho **đường đi đúng** và ít nhất **một đường đi sai** | QA |
| 4 | Mọi mục PRD liên quan đã có dòng trong `TRACEABILITY.md` | QA |
| 5 | Thay đổi DB có migration, và migration đã chạy ngược được (`downgrade`) | Dev |
| 6 | Không giảm độ phủ tổng thể quá 1 điểm phần trăm | CI |
| 7 | Thay đổi chạm tiền/quyền: có test mang marker `money` hoặc `security` | QA |
| 8 | Đã test thăm dò trên staging | QA |
| 9 | Log đủ để dựng lại sự cố (có `request_id`, có event name) | QA |

## 5. Phân loại mức độ lỗi

| Mức | Định nghĩa | Cam kết xử lý | Ví dụ ở GoAn |
|---|---|---|---|
| **Blocker** | Mất tiền, mất dữ liệu, hoặc nguy hiểm cho người dùng | Sửa ngay, dừng mọi việc khác | Trừ tiền khách hai lần; tài xế nhận sai số dư ký quỹ; SOS không gửi |
| **Critical** | Luồng chính không dùng được, không có cách đi vòng | Trong 24 giờ | Không đặt được xe; tài xế không nhận được cuốc; không quét được QR |
| **Major** | Luồng chính lỗi nhưng có cách đi vòng | Trong sprint | Lịch sử chuyến không tải được; chat mất tin khi đổi mạng |
| **Minor** | Sai lệch nhỏ, không cản trở | Backlog | Sai định dạng ngày; nhãn tiếng Việt sai chính tả |
| **Trivial** | Thẩm mỹ | Khi rảnh | Lệch 2px |

Quy tắc leo thang: Blocker báo ngay trong nhóm chat, không chờ họp đầu ngày.

## 6. Những vùng QA phải soi kỹ nhất ở GoAn

Xếp theo thiệt hại nếu sai, không theo độ khó:

| Ưu tiên | Vùng | Vì sao |
|---|---|---|
| 1 | **Chốt cước & chia ví** | Sai một lần là mất tiền thật của tài xế hoặc của công ty. Không thể "sửa ở bản sau" |
| 2 | **Ký quỹ** | Tiền của tài xế, có thể thành tranh chấp pháp lý |
| 3 | **Chống gian lận** | Sai dương tính = khoá nhầm tài xế thật; sai âm tính = mất tiền |
| 4 | **Phân quyền** | CSKH đọc được dữ liệu không thuộc phạm vi là vi phạm Nghị định 13 |
| 5 | **Trạng thái chuyến** | Kẹt trạng thái = khách đứng đường |
| 6 | **GPS nền app tài xế** | Mất điểm GPS làm sai cước và sai đối soát chạy vòng |

## 7. Nhịp làm việc

| Khi nào | Việc |
|---|---|
| Đầu sprint | QA viết test case cho các task trong sprint, cập nhật `TRACEABILITY.md` |
| Hằng ngày | Review MR trong ngày; bug Blocker báo ngay |
| Trước release | Chạy bộ hồi quy, ký xác nhận trong MR release |
| Sau sự cố production | Viết test tái hiện lỗi **trước khi** sửa. Không có test thì không được đóng sự cố |

## 8. Khi QA và Dev bất đồng

1. QA mô tả **hệ quả với người dùng**, không tranh luận về code.
2. Dev mô tả **chi phí sửa** và rủi ro của việc sửa.
3. Không thống nhất được thì Tech Lead quyết trong 24 giờ và ghi lý do vào MR.
4. Quyết định "chấp nhận rủi ro" phải được ghi lại — không bao giờ chỉ nói miệng.
