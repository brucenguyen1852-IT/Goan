/**
 * Client realtime: nối lại, xếp hàng khi đứt, chờ ack (P2-15).
 *
 * Ba hành vi này chỉ xảy ra khi mạng hỏng — nghĩa là không bao giờ xảy ra lúc phát triển, và
 * luôn xảy ra với người dùng thật trên 4G. Test là chỗ duy nhất chúng được chạy.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { RealtimeClient, type RealtimeMessage, type SocketLike } from "./index";

class FakeSocket implements SocketLike {
  static last: FakeSocket | null = null;
  static created = 0;

  sent: string[] = [];
  closed = false;
  onopen: ((event: unknown) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;

  constructor(readonly url: string) {
    FakeSocket.last = this;
    FakeSocket.created += 1;
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closed = true;
  }

  open(): void {
    this.onopen?.({});
  }

  drop(): void {
    this.onclose?.({});
  }

  receive(message: RealtimeMessage): void {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  parsed(): RealtimeMessage[] {
    return this.sent.map((s) => JSON.parse(s) as RealtimeMessage);
  }
}

/** Đồng hồ giả: test về lùi dần mà chờ thật thì mất 30 giây và thỉnh thoảng đỏ vu vơ. */
function fakeClock() {
  const hen: { fn: () => void; at: number; id: number }[] = [];
  let now = 0;
  let seq = 0;
  return {
    setTimeoutFn: (fn: () => void, ms: number) => {
      const id = ++seq;
      hen.push({ fn, at: now + ms, id });
      return id;
    },
    clearTimeoutFn: (handle: unknown) => {
      const i = hen.findIndex((h) => h.id === handle);
      if (i >= 0) hen.splice(i, 1);
    },
    advance(ms: number) {
      now += ms;
      const den = hen.filter((h) => h.at <= now).sort((a, b) => a.at - b.at);
      for (const h of den) {
        const i = hen.indexOf(h);
        if (i >= 0) hen.splice(i, 1);
        h.fn();
      }
    },
    pending: () => hen.length,
  };
}

function makeClient(overrides: Record<string, unknown> = {}) {
  const clock = fakeClock();
  const events: RealtimeMessage[] = [];
  const states: string[] = [];
  const client = new RealtimeClient({
    url: () => "wss://test/ws?token=t1",
    createSocket: (url) => new FakeSocket(url),
    onEvent: (e) => events.push(e),
    onStateChange: (s) => states.push(s),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
    randomFn: () => 0.5,
    ...overrides,
  });
  return { client, clock, events, states };
}

beforeEach(() => {
  FakeSocket.last = null;
  FakeSocket.created = 0;
});

describe("nối và nhận", () => {
  it("mở kết nối rồi chuyển sang trạng thái open", () => {
    const { client, states } = makeClient();

    client.connect();
    expect(states).toEqual(["connecting"]);

    FakeSocket.last!.open();
    expect(states).toEqual(["connecting", "open"]);
    expect(client.getState()).toBe("open");
  });

  it("gói JSON hỏng không làm sập kết nối", () => {
    // Một byte lỗi trên đường truyền không được đánh sập cả màn hình đang mở.
    const { client, events } = makeClient();
    client.connect();
    FakeSocket.last!.open();

    FakeSocket.last!.onmessage?.({ data: "{không phải json" });

    expect(events).toEqual([]);
    expect(client.getState()).toBe("open");
  });

  it("chuyển tiếp mọi sự kiện server gửi xuống", () => {
    const { client, events } = makeClient();
    client.connect();
    FakeSocket.last!.open();

    FakeSocket.last!.receive({ type: "chat.message", conversation_id: "c1" });

    expect(events).toEqual([{ type: "chat.message", conversation_id: "c1" }]);
  });
});

describe("gửi lúc đang đứt", () => {
  it("xếp hàng rồi gửi khi nối lại được, không ném lỗi", () => {
    // Người dùng bấm gửi lúc mất sóng và thấy báo lỗi sẽ bấm lại. Khử trùng ở backend cứu
    // được chuyện trùng tin, nhưng không cứu được cảm giác "ứng dụng này hỏng".
    const { client } = makeClient();

    client.send({ type: "chat.typing", conversation_id: "c1" });
    expect(client.pendingCount()).toBe(1);

    client.connect();
    FakeSocket.last!.open();

    expect(FakeSocket.last!.parsed()).toEqual([{ type: "chat.typing", conversation_id: "c1" }]);
    expect(client.pendingCount()).toBe(0);
  });

  it("tin xếp hàng lúc đứt được gửi lại sau khi nối lại", () => {
    const { client, clock } = makeClient();
    client.connect();
    FakeSocket.last!.open();

    FakeSocket.last!.drop();
    client.send({ type: "chat.typing" });
    expect(client.pendingCount()).toBe(1);

    clock.advance(2_000);
    FakeSocket.last!.open();

    expect(FakeSocket.last!.parsed()).toEqual([{ type: "chat.typing" }]);
  });
});

describe("chờ ack", () => {
  it("nhận ack thì thôi giữ tin", () => {
    const { client } = makeClient();
    client.connect();
    FakeSocket.last!.open();

    client.send({ type: "chat.send", body: "xin chào" }, "m-1");
    expect(client.pendingCount()).toBe(1);

    FakeSocket.last!.receive({ type: "ack", ack_id: "m-1" });

    expect(client.pendingCount()).toBe(0);
  });

  it("quá hạn không thấy ack thì gửi lại", () => {
    // "Đã gửi" mà chỉ có nghĩa "đã ghi vào socket" là một câu hoàn toàn khác với "server đã
    // nhận". Không có bước này thì tin mất im lặng.
    const { client, clock } = makeClient({ ackTimeoutMs: 5_000 });
    client.connect();
    FakeSocket.last!.open();
    client.send({ type: "chat.send", body: "xin chào" }, "m-1");

    clock.advance(5_000);

    expect(FakeSocket.last!.parsed()).toHaveLength(2);
    expect(client.pendingCount()).toBe(1);
  });

  it("gửi lại tối đa 5 lần rồi bỏ, không giữ mãi trong hàng đợi", () => {
    const { client, clock } = makeClient({ ackTimeoutMs: 1_000 });
    client.connect();
    FakeSocket.last!.open();
    client.send({ type: "chat.send" }, "m-1");

    for (let i = 0; i < 10; i++) clock.advance(1_000);

    expect(FakeSocket.last!.parsed().length).toBeLessThanOrEqual(5);
    expect(client.pendingCount()).toBe(0);
  });

  it("tin không có ackId thì gửi xong là xong", () => {
    const { client } = makeClient();
    client.connect();
    FakeSocket.last!.open();

    client.send({ type: "chat.typing" });

    expect(client.pendingCount()).toBe(0);
  });
});

describe("nối lại", () => {
  it("lùi dần chứ không đập liên tục vào server vừa sống lại", () => {
    // Nối lại ngay mỗi giây là cách biến một sự cố ngắn thành sự cố dài.
    const { client, clock } = makeClient({ minBackoffMs: 1_000, maxBackoffMs: 30_000 });
    client.connect();
    FakeSocket.last!.open();

    FakeSocket.last!.drop();
    clock.advance(700); // 1000 * 0.75 = 750ms với randomFn = 0.5
    expect(FakeSocket.created).toBe(1);
    clock.advance(100);
    expect(FakeSocket.created).toBe(2);

    FakeSocket.last!.drop();
    clock.advance(800); // lần hai chờ lâu hơn: 2000 * 0.75 = 1500ms
    expect(FakeSocket.created).toBe(2);
    clock.advance(800);
    expect(FakeSocket.created).toBe(3);
  });

  it("khoảng lùi không vượt trần", () => {
    const { client, clock } = makeClient({ minBackoffMs: 1_000, maxBackoffMs: 4_000 });
    client.connect();
    for (let i = 0; i < 6; i++) {
      FakeSocket.last!.open();
      FakeSocket.last!.drop();
      clock.advance(4_000);
    }

    expect(FakeSocket.created).toBe(7);
  });

  it("mở lại bằng URL mới, không dùng lại token đã chết", () => {
    // Token 15 phút hết hạn giữa lúc đang mở. Nối lại bằng chuỗi URL cố định nghĩa là nối
    // lại mãi mãi bằng một token backend đã từ chối.
    let lan = 0;
    const { client, clock } = makeClient({ url: () => `wss://test/ws?token=t${++lan}` });
    client.connect();
    FakeSocket.last!.open();
    FakeSocket.last!.drop();

    clock.advance(1_000);

    expect(FakeSocket.last!.url).toBe("wss://test/ws?token=t2");
  });

  it("tự đóng thì KHÔNG nối lại", () => {
    // Người dùng đăng xuất mà client vẫn nối lại là giữ một kết nối đã hết quyền.
    const { client, clock } = makeClient();
    client.connect();
    FakeSocket.last!.open();

    client.close();
    clock.advance(60_000);

    expect(FakeSocket.created).toBe(1);
    expect(client.getState()).toBe("closed");
  });

  it("đóng rồi thì không còn hẹn giờ nào treo lại", () => {
    // Hẹn giờ mồ côi trong React Native giữ cả tiến trình thức và ngốn pin.
    const { client, clock } = makeClient();
    client.connect();
    FakeSocket.last!.open();
    client.send({ type: "chat.send" }, "m-1");

    client.close();

    expect(clock.pending()).toBe(0);
  });

  it("không tạo nổi socket vẫn thử lại chứ không đứng im", () => {
    const loi = vi.fn(() => {
      throw new Error("không mở được");
    });
    const { client, clock } = makeClient({ createSocket: loi });

    client.connect();
    clock.advance(1_000);

    expect(loi).toHaveBeenCalledTimes(2);
  });
});
