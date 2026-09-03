## Thay đổi gì

<!-- Một đoạn ngắn: vấn đề là gì, cách xử lý ra sao. Không liệt kê lại từng file. -->

## Ánh xạ PRD

<!-- Mã PRD trong docs/QA/TRACEABILITY.md, vd PRD-SEC-02. Không có thì ghi rõ "không thuộc PRD nào" và vì sao. -->

- PRD-

## Kiểm thử

| Câu hỏi | Trả lời |
|---|---|
| Test mới nằm ở đâu? | |
| **Test này đỏ khi nào?** | |
| Có test cho đường đi sai không? | |
| Đã cập nhật `docs/QA/TRACEABILITY.md` chưa? | |

## Checklist bắt buộc

- [ ] `make check` xanh trên máy (ruff + mypy + pytest)
- [ ] Có test cho **đường đi đúng** và ít nhất **một đường đi sai**
- [ ] Đổi DB thì có migration, và `downgrade` chạy được
- [ ] Đổi API thì đã chạy `make -C services/api openapi` và commit `openapi.json`
- [ ] Không giảm độ phủ quá 1 điểm phần trăm
- [ ] Chạm tiền hoặc quyền: có test mang marker `money` hoặc `security`
- [ ] Log đủ để dựng lại sự cố (`request_id`, tên event)
- [ ] Không có secret, token, hay số CCCD trong code, log hay test

## Thay đổi phá vỡ tương thích

<!-- Client cũ có gãy không? Có cần deploy theo thứ tự không? Không có thì ghi "Không". -->

## Rủi ro và cách quay lui

<!-- Nếu hỏng trên production thì quay lui kiểu gì? Có cần chạy migration ngược không? -->

---

**QA ký duyệt:** <!-- @tên — Pass / Blocked. Blocked thì kèm link issue theo docs/QA/BUG_TEMPLATE.md -->
