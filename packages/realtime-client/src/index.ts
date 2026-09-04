/**
 * Client WebSocket dùng chung cho mọi frontend GoAn (P2-15).
 *
 * Ba việc mà mọi màn hình realtime đều phải làm, và cả ba đều dễ làm sai theo cùng một kiểu:
 *
 *   1. **Nối lại khi mất mạng** — nhưng lùi dần và có nhiễu ngẫu nhiên. Nối lại ngay mỗi giây
 *      là cách biến một sự cố ngắn của server thành sự cố dài: server vừa sống lại thì toàn
 *      bộ client đập vào cùng lúc.
 *   2. **Gửi lúc đang đứt** — xếp hàng chứ không ném lỗi. Người dùng bấm gửi lúc mất sóng và
 *      thấy báo lỗi sẽ bấm lại; khử trùng ở backend cứu được chuyện trùng tin, nhưng không
 *      cứu được cảm giác "ứng dụng này hỏng".
 *   3. **Biết server đã nhận chưa** — chờ `ack`, quá hạn thì gửi lại. Không có bước này thì
 *      "đã gửi" chỉ có nghĩa là "đã ghi vào socket", một câu hoàn toàn khác.
 *
 * Không dùng gì ngoài `WebSocket`, nên chạy được cả trên trình duyệt lẫn React Native.
 */

export type RealtimeState = "idle" | "connecting" | "open" | "closed";

export interface RealtimeMessage {
  type: string;
  [key: string]: unknown;
}

/** Bề mặt tối thiểu của WebSocket mà client này cần — đủ để test cắm bản giả vào. */
export interface SocketLike {
  send(data: string): void;
  close(code?: number, reason?: string): void;
  onopen: ((event: unknown) => void) | null;
  onclose: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
}

export interface RealtimeOptions {
  /** Hàm, không phải chuỗi: nối lại phải dùng token MỚI, không phải token đã chết. */
  url: () => string;
  onEvent?: (message: RealtimeMessage) => void;
  onStateChange?: (state: RealtimeState) => void;
  /** Điểm cắm bản giả trong test, và chỗ React Native đưa WebSocket của nó vào. */
  createSocket?: (url: string) => SocketLike;
  /** Khoảng lùi tối thiểu / tối đa giữa hai lần nối lại, tính bằng mili-giây. */
  minBackoffMs?: number;
  maxBackoffMs?: number;
  /** Chờ ack bao lâu trước khi gửi lại. */
  ackTimeoutMs?: number;
  setTimeoutFn?: (fn: () => void, ms: number) => unknown;
  clearTimeoutFn?: (handle: unknown) => void;
  randomFn?: () => number;
}

interface PendingMessage {
  message: RealtimeMessage;
  ackId?: string;
  attempts: number;
}

const DEFAULT_MIN_BACKOFF = 1_000;
const DEFAULT_MAX_BACKOFF = 30_000;
const DEFAULT_ACK_TIMEOUT = 8_000;
/** Gửi lại quá số lần này thì bỏ: giữ mãi một tin không ai nhận chỉ làm hàng đợi phình ra. */
const MAX_ATTEMPTS = 5;

export class RealtimeClient {
  private socket: SocketLike | null = null;
  private state: RealtimeState = "idle";
  private queue: PendingMessage[] = [];
  private waitingAck = new Map<string, PendingMessage>();
  private retries = 0;
  private reconnectHandle: unknown = null;
  private ackHandles = new Map<string, unknown>();
  private closedByUs = false;

  constructor(private readonly options: RealtimeOptions) {}

  getState(): RealtimeState {
    return this.state;
  }

  /** Số tin đang chờ gửi hoặc chờ ack — dùng để hiện "đang gửi…" trên giao diện. */
  pendingCount(): number {
    return this.queue.length + this.waitingAck.size;
  }

  connect(): void {
    if (this.state === "connecting" || this.state === "open") return;
    this.closedByUs = false;
    this.setState("connecting");

    const create = this.options.createSocket ?? ((url: string) => new WebSocket(url) as SocketLike);
    let socket: SocketLike;
    try {
      socket = create(this.options.url());
    } catch {
      // Không tạo nổi socket (URL sai, hết bộ nhớ) vẫn phải thử lại — coi như một lần đứt.
      // Phải hạ trạng thái về "closed" TRƯỚC khi hẹn nối lại: chốt chặn ở đầu connect() từ
      // chối mọi lần gọi khi đang "connecting", nên bỏ dòng này là client đứng im vĩnh viễn.
      this.setState("closed");
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.onopen = () => {
      this.retries = 0;
      this.setState("open");
      this.flush();
    };
    socket.onmessage = (event) => this.handleMessage(event.data);
    socket.onerror = () => {
      /* onclose luôn theo sau onerror; xử lý ở một chỗ để không nối lại hai lần */
    };
    socket.onclose = () => {
      this.socket = null;
      this.setState("closed");
      if (!this.closedByUs) this.scheduleReconnect();
    };
  }

  /**
   * Gửi một tin. Đang đứt thì xếp hàng và gửi khi nối lại được.
   *
   * `ackId` có thì tin được giữ lại tới khi server báo nhận; quá hạn thì gửi lại. Dùng chung
   * giá trị với `client_msg_id` của backend, nên gửi lại không tạo tin thứ hai.
   */
  send(message: RealtimeMessage, ackId?: string): void {
    const pending: PendingMessage = { message, ackId, attempts: 0 };
    if (this.state !== "open" || this.socket === null) {
      this.queue.push(pending);
      return;
    }
    this.write(pending);
  }

  close(): void {
    this.closedByUs = true;
    this.cancelReconnect();
    for (const handle of this.ackHandles.values()) this.clearTimer(handle);
    this.ackHandles.clear();
    this.socket?.close(1000, "client closed");
    this.socket = null;
    this.setState("closed");
  }

  // --- bên trong ----------------------------------------------------------------------

  private setState(state: RealtimeState): void {
    if (this.state === state) return;
    this.state = state;
    this.options.onStateChange?.(state);
  }

  private write(pending: PendingMessage): void {
    pending.attempts += 1;
    try {
      this.socket?.send(JSON.stringify(pending.message));
    } catch {
      // Socket chết giữa lúc ghi: trả tin về hàng đợi thay vì đánh mất nó.
      this.queue.push(pending);
      return;
    }
    if (pending.ackId) {
      this.waitingAck.set(pending.ackId, pending);
      this.armAckTimer(pending.ackId);
    }
  }

  private armAckTimer(ackId: string): void {
    const handle = this.setTimer(() => {
      const pending = this.waitingAck.get(ackId);
      this.ackHandles.delete(ackId);
      if (!pending) return;
      this.waitingAck.delete(ackId);
      if (pending.attempts >= MAX_ATTEMPTS) return;
      // Xếp lại vào hàng đợi chứ không ghi thẳng: nếu đang đứt thì ghi thẳng lại mất tin.
      this.queue.push(pending);
      if (this.state === "open") this.flush();
    }, this.options.ackTimeoutMs ?? DEFAULT_ACK_TIMEOUT);
    this.ackHandles.set(ackId, handle);
  }

  private flush(): void {
    const cho = this.queue;
    this.queue = [];
    for (const pending of cho) this.write(pending);
  }

  private handleMessage(raw: unknown): void {
    let message: RealtimeMessage;
    try {
      message = JSON.parse(String(raw)) as RealtimeMessage;
    } catch {
      return; // gói hỏng thì bỏ qua, không được làm sập cả kết nối
    }
    const ackId = typeof message.ack_id === "string" ? message.ack_id : undefined;
    if (ackId) {
      this.waitingAck.delete(ackId);
      const handle = this.ackHandles.get(ackId);
      if (handle !== undefined) {
        this.clearTimer(handle);
        this.ackHandles.delete(ackId);
      }
    }
    // `auth.expired`: token chết giữa chừng. Nối lại NGAY với token mới thay vì lùi dần —
    // đây không phải sự cố mạng, và người dùng đang ngồi trước màn hình.
    if (message.type === "auth.expired") {
      this.retries = 0;
    }
    this.options.onEvent?.(message);
  }

  private scheduleReconnect(): void {
    this.cancelReconnect();
    const min = this.options.minBackoffMs ?? DEFAULT_MIN_BACKOFF;
    const max = this.options.maxBackoffMs ?? DEFAULT_MAX_BACKOFF;
    const co_ban = Math.min(max, min * 2 ** this.retries);
    // Nhiễu ngẫu nhiên: không có nó thì mọi client nối lại đúng cùng một mili-giây và hạ
    // server vừa sống lại.
    const rand = this.options.randomFn ?? Math.random;
    const cho = Math.round(co_ban * (0.5 + rand() * 0.5));
    this.retries += 1;
    this.reconnectHandle = this.setTimer(() => {
      this.reconnectHandle = null;
      this.connect();
    }, cho);
  }

  private cancelReconnect(): void {
    if (this.reconnectHandle !== null) {
      this.clearTimer(this.reconnectHandle);
      this.reconnectHandle = null;
    }
  }

  private setTimer(fn: () => void, ms: number): unknown {
    return (this.options.setTimeoutFn ?? setTimeout)(fn, ms);
  }

  private clearTimer(handle: unknown): void {
    (this.options.clearTimeoutFn ?? clearTimeout)(handle as never);
  }
}
