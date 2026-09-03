import "@testing-library/jest-dom/vitest";

// Leaflet cần đo kích thước phần tử; jsdom trả về 0 và không dựng được bản đồ. Bản đồ không
// phải thứ bộ test này kiểm — phân quyền mới là — nên thay bằng một hộp trống.
vi.mock("@/components/FleetMap", () => ({
  FleetMap: () => null,
}));

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.closed = true;
  }
}

vi.stubGlobal("WebSocket", FakeWebSocket);
