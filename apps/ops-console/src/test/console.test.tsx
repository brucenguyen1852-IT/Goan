/**
 * Kiểm thử giao diện Console theo vai trò (PRD-OPS-16) — P1-19.
 *
 * Câu hỏi bộ test này trả lời: "mỗi vai trò có thấy đúng phần được phép không?".
 *
 * Cần nói rõ giới hạn: ẩn menu KHÔNG phải là phân quyền — backend mới là nơi chặn thật, và
 * điều đó đã có 92 test bảo vệ. Bộ này chỉ bảo đảm người vận hành không nhìn thấy những nút
 * mà bấm vào chỉ nhận 403, vì một Console đầy nút vô dụng là một Console không ai tin.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "@/App";
import { AuthProvider } from "@/auth/useAuth";
import { clearSession, setTokens } from "@/auth/session";

const PERMISSIONS: Record<string, string[]> = {
  dispatcher: ["ops:fleet:read", "user:profile:read", "trip:trip:read_all", "trip:trip:assign"],
  driver_ops: ["driver:profile:read", "driver:profile:approve", "trip:trip:read_all"],
  finance_manager: ["finance:payout:approve", "finance:reconciliation:read"],
  auditor: ["audit:log:read", "trip:trip:read_all", "iam:role:read"],
  super_admin: ["*"],
};

function mockApi(role: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const json = (data: unknown) =>
        new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      if (url.includes("/ops/auth/me")) {
        return json({
          id: "staff-1",
          email: `${role}@goan.vn`,
          full_name: "Nhân Sự Test",
          roles: [role],
          permissions: PERMISSIONS[role],
        });
      }
      if (url.includes("/ops/fleet")) {
        return json({
          taken_at: new Date().toISOString(),
          drivers_online: 2,
          drivers_on_trip: 1,
          trips_active: 1,
          drivers: [],
        });
      }
      if (url.includes("/ops/approvals")) return json([]);
      if (url.includes("/ops/drivers")) return json([]);
      if (url.includes("/ops/trips")) return json({ items: [], next_cursor: null });
      if (url.includes("/ops/audit-logs")) return json({ items: [], next_cursor: null });
      if (url.includes("/ops/roles")) return json([]);
      if (url.includes("/ops/staff")) return json([]);
      return json({});
    }),
  );
}

function renderConsole() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>,
  );
}

describe("Menu Console dựng theo quyền", () => {
  beforeEach(() => {
    // Dùng setTokens chứ không ghi thẳng localStorage: session.ts giữ một bản nhớ trong bộ
    // nhớ, ghi thẳng vào localStorage sẽ không đánh thức nó.
    setTokens("token-test", "refresh-test");
    vi.restoreAllMocks();
  });

  it("điều phối viên thấy Live Ops và chuyến, không thấy nhân sự", async () => {
    mockApi("dispatcher");
    renderConsole();

    expect(await screen.findByRole("link", { name: "Live Ops" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chuyến đi" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Nhân sự" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Nhật ký" })).not.toBeInTheDocument();
  });

  it("vận hành tài xế thấy mục Tài xế, không thấy Live Ops", async () => {
    mockApi("driver_ops");
    renderConsole();

    expect(await screen.findByRole("link", { name: "Tài xế" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Live Ops" })).not.toBeInTheDocument();
  });

  it("trưởng phòng tài chính chỉ thấy hàng đợi phê duyệt", async () => {
    mockApi("finance_manager");
    renderConsole();

    expect(await screen.findByRole("link", { name: "Chờ duyệt" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Tài xế" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Live Ops" })).not.toBeInTheDocument();
  });

  it("kiểm toán viên thấy nhật ký và vai trò, không thấy nút thao tác", async () => {
    mockApi("auditor");
    renderConsole();

    expect(await screen.findByRole("link", { name: "Nhật ký" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Vai trò" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Nhân sự" })).not.toBeInTheDocument();
  });

  it("quản trị hệ thống thấy toàn bộ menu nhờ quyền vạn năng", async () => {
    mockApi("super_admin");
    renderConsole();

    for (const label of ["Live Ops", "Tài xế", "Chuyến đi", "Chờ duyệt", "Nhân sự", "Vai trò", "Nhật ký"]) {
      expect(await screen.findByRole("link", { name: label })).toBeInTheDocument();
    }
  });
});

describe("Đăng nhập", () => {
  beforeEach(() => {
    clearSession();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("chưa đăng nhập thì hiện màn hình đăng nhập kèm ô mã 2FA", async () => {
    mockApi("dispatcher");
    renderConsole();

    expect(await screen.findByLabelText(/Mã xác thực hai lớp/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Nhớ máy này 30 ngày/)).toBeInTheDocument();
  });

  it("gửi kèm cờ nhớ máy khi người dùng tích chọn", async () => {
    const calls: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
        if (url.includes("/ops/auth/login")) {
          return new Response(
            JSON.stringify({
              access_token: "a",
              refresh_token: "r",
              device_token: "thiet-bi-1",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(
          JSON.stringify({
            id: "staff-1",
            email: "a@goan.vn",
            full_name: "A",
            roles: ["dispatcher"],
            permissions: PERMISSIONS.dispatcher,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    renderConsole();

    await userEvent.type(await screen.findByLabelText(/Email công ty/), "a@goan.vn");
    await userEvent.type(screen.getByLabelText(/^Mật khẩu/), "mat-khau-du-dai-12");
    await userEvent.type(screen.getByLabelText(/Mã xác thực hai lớp/), "123456");
    await userEvent.click(screen.getByLabelText(/Nhớ máy này 30 ngày/));
    await userEvent.click(screen.getByRole("button", { name: /Đăng nhập/ }));

    await waitFor(() => {
      const login = calls.find((c) => c.url.includes("/ops/auth/login"));
      expect(login?.body).toMatchObject({ remember_device: true, totp_code: "123456" });
    });
    // Token nhớ máy phải được giữ lại, nếu không lần sau vẫn phải nhập mã.
    await waitFor(() => expect(localStorage.getItem("goan.ops.device")).toBe("thiet-bi-1"));
  });
});
