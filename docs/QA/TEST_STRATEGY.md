# Chiến lược kiểm thử GoAn

## 1. Kim tự tháp test — và tỷ lệ thực tế đang có

| Tầng | Marker | Mục tiêu | Hiện có | Chạy ở đâu |
|---|---|---|---|---|
| Unit | `unit` | Hàm thuần: công thức cước, state machine, che PII, đánh giá lệch tuyến | ~55 test | Mọi lần lưu file, < 1 giây |
| Integration | `integration` | Nhiều lớp + DB SQLite in-memory: chốt chuyến, ký quỹ, đối soát | ~35 test | Mọi commit |
| API | `api` | Qua đúng chuỗi middleware thật, kiểm cả mã trạng thái và header | ~16 test | Mọi commit |
| E2E | *(chưa có)* | Kịch bản thật xuyên app ↔ backend | Sẽ có ở P3 | Trước release |

**Vì sao chưa có E2E:** chưa có app tài xế và app khách. Thêm ngay khi P3 bắt đầu, không chờ P4.

## 2. Marker và cách dùng

```bash
make test                      # tất cả
pytest -m unit                 # nhanh, dùng khi đang code
pytest -m money                # mọi thứ chạm tiền — chạy trước mỗi lần đụng vào ví/cước
pytest -m security             # token, phân quyền, chống lạm dụng
pytest -m "not api"            # bỏ qua tầng chậm nhất
make cov                       # kèm báo cáo độ phủ
```

`--strict-markers` đang bật: gõ sai tên marker là test đỏ, không âm thầm bỏ qua.

| Marker | Ý nghĩa |
|---|---|
| `unit` | Không DB, không mạng, dưới 1 giây |
| `integration` | Có DB hoặc nhiều lớp phối hợp |
| `api` | Đi qua HTTP client và toàn bộ middleware |
| `security` | Token, phân quyền, chống lạm dụng |
| `money` | **Không bao giờ được đỏ.** Đỏ là chặn merge ngay lập tức |
| `prd` | Có ánh xạ tới một mục PRD trong `TRACEABILITY.md` |

## 3. Nguyên tắc viết test ở dự án này

**Tên test viết bằng tiếng Việt, mô tả hành vi, không mô tả hàm.**
`test_dung_lai_token_cu_thi_thu_hoi_ca_ho` chứ không phải `test_refresh_tokens_2`.
Khi test đỏ lúc 2 giờ sáng, tên test là thứ đầu tiên người trực đọc.

**Mỗi test phải trả lời được: "Nó đỏ khi nào?"**
Không trả lời được nghĩa là test chỉ chụp lại hành vi hiện tại, không bảo vệ điều gì.

**Docstring ghi *vì sao*, không ghi *cái gì*.**
Code đã nói cái gì rồi. Cái đắt giá là bối cảnh: "kịch bản thật — mất sóng giữa chừng,
người dùng bấm lại".

**Test đường đi sai được ưu tiên ngang đường đi đúng.**
Đường đi đúng thì lập trình viên đã thử bằng tay. Lỗi production gần như luôn nằm ở nhánh sai.

**Không mock thứ mình sở hữu.** Mock cổng thanh toán, eKYC, SMS — đúng.
Mock service của chính mình để test dễ xanh — sai.

**Tiền dùng `Decimal`, không dùng `float`.** Có test riêng chặn việc này.

## 4. Dữ liệu test

- DB là SQLite in-memory, dựng lại cho **từng** test → không có rò rỉ trạng thái giữa các test.
- Redis dùng `tests/fakes.FakeRedis` — hiện thực đúng phần đang dùng. Thiếu lệnh nào thì
  `AttributeError` chỉ thẳng ra, tốt hơn là im lặng trả giá trị sai.
- `FakeRedis.fail = True` mô phỏng Redis chết, để kiểm chứng các quyết định "fail-open" đã ghi trong tài liệu.
- Factory trong `tests/conftest.py`: `create_rider`, `create_driver`, `create_trip`.

## 5. Độ phủ

| Ngưỡng | Giá trị | Ghi chú |
|---|---|---|
| Toàn dự án | **≥ 75%** | Hiện tại: 78% |
| `app/domains/pricing`, `escrow`, `payments` | **≥ 90%** | Vùng chạm tiền |
| `app/core/security`, `app/domains/auth` | **≥ 85%** | Vùng bảo mật |

Độ phủ là **chỉ báo**, không phải mục tiêu. Một module 100% phủ mà không có test đường đi sai
thì vẫn kém một module 70% phủ có test biên tử tế. QA đánh giá chất lượng test khi review MR,
không nhìn mỗi con số.

## 6. Những gì kiểm thử tự động **không** bắt được

Phải xử lý bằng test thăm dò hoặc kiểm tra bằng tay:

| Rủi ro | Cách kiểm |
|---|---|
| GPS nền bị hệ điều hành giết | Chạy thật trên máy Android/iOS, khoá màn hình 30 phút |
| Tiêu hao pin app tài xế | Đo thực tế trong ca 8 giờ |
| Trải nghiệm khi mạng chập chờn | Bật chế độ mạng yếu, tắt/bật máy bay giữa chuyến |
| Nội dung tiếng Việt sai ngữ cảnh | Người đọc |
| Chat 3 bên có gây hiểu nhầm | Diễn thử với người thật đóng vai CSKH |

## 7. Cổng chất lượng trong CI

| Job | Chặn merge |
|---|---|
| `ruff check` + `ruff format --check` | Có |
| `mypy app` | Có |
| `pytest` | Có |
| `alembic upgrade head` + `alembic check` | Có |
| OpenAPI khớp `api-client` | Có |
| `pnpm install --frozen-lockfile` + `build` | Có |

Không job nào còn `continue-on-error`. Một cổng chất lượng có ngoại lệ thì không phải cổng.
