# @goan/realtime-client

Client WebSocket dùng chung cho web và React Native (P2-15).

Không phụ thuộc DOM ngoài `WebSocket` — thứ mà cả trình duyệt lẫn React Native đều có sẵn.
Vì thế cùng một mã chạy được ở `apps/ops-console`, `apps/customer-web` và app di động sau này;
và vì thế nó nhận `WebSocket` qua tham số để test cắm bản giả vào.

## Vì sao không dùng thẳng `new WebSocket(...)`

Ba thứ mà mọi màn hình realtime đều phải làm lại nếu không có gói này, và cả ba đều dễ làm
sai theo cùng một kiểu:

| Vấn đề | Nếu tự làm | Ở đây |
|---|---|---|
| Mất mạng | Nối lại ngay, mỗi 1 giây, cho tất cả các tab | Lùi dần có nhiễu ngẫu nhiên (1s → 30s) |
| Gửi lúc đang đứt | Ném lỗi hoặc mất tin | Xếp hàng, gửi lại khi nối lại được |
| Không biết server đã nhận chưa | Coi như đã gửi | Chờ `ack`, quá hạn thì gửi lại |

Nối lại ngay lập tức là cách một sự cố ngắn của server biến thành sự cố dài: server vừa sống
lại thì toàn bộ client đập vào cùng một lúc. Nhiễu ngẫu nhiên trong khoảng lùi là thứ tách
đám đông đó ra.

## Dùng

```ts
import { RealtimeClient } from "@goan/realtime-client";

const client = new RealtimeClient({
  url: () => `wss://api.goan.vn/ws?token=${getAccessToken()}`,
  onEvent: (event) => { /* chat.message, trip_matched, ops.fleet_update… */ },
  onStateChange: (state) => setOnline(state === "open"),
});

client.connect();
client.send({ type: "chat.typing", conversation_id: id });   // xếp hàng nếu đang đứt
client.close();
```

`url` là **hàm**, không phải chuỗi: token hết hạn giữa chừng thì lần nối lại phải dùng token
mới. Truyền chuỗi cố định nghĩa là nối lại mãi mãi bằng một token đã chết.
