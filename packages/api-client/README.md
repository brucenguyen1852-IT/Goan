# @goan/api-client

Client TypeScript **sinh tự động** từ OpenAPI của `services/api`. Đây là contract duy nhất giữa
backend và mọi frontend (app khách, app tài xế, Console, Partner Portal, website).

## Quy tắc

1. **Không viết tay endpoint ở frontend.** Mọi lời gọi API đi qua package này.
2. **Không sửa tay** `openapi.json` hay `src/generated/`. Cả hai đều được sinh lại.
3. Đổi API ở backend → chạy lại lệnh sinh → commit. CI so hai bên, lệch là đỏ.

## Sinh lại

```bash
# từ thư mục gốc repo
pnpm api:client
```

Tương đương:

```bash
python3 services/api/scripts/export_openapi.py packages/api-client/openapi.json
pnpm --filter @goan/api-client generate
```

## Vì sao có package này

Trước đây `apps/customer-web` viết tay đường dẫn API và đã lệch hoàn toàn khỏi backend:
`/auth/otp/request` (frontend) vs `/auth/request-otp` (backend), `/trips/fare-estimate` vs
`/pricing/estimate`, và một endpoint danh sách chuyến không hề tồn tại. Không ai phát hiện ra
cho tới khi chạy thật. Sinh client từ OpenAPI khiến lỗi đó thành lỗi biên dịch.
