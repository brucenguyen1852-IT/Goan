/**
 * Support Desk trên Console: hàng đợi, trả lời, tham gia 3 bên, tra cứu, bảng SLA
 * (P2-16…P2-19).
 *
 * Hai câu hỏi bộ này trả lời, và cả hai đều là chuyện đã làm hỏng báo cáo ở hệ thống thật:
 *
 *   1. Một nút "Gửi trả lời" có gọi đúng endpoint làm cả ba việc (vào hội thoại, gửi tin,
 *      đóng đồng hồ SLA) không? Tách ra ba nút là mời agent quên hai nút cuối.
 *   2. Chỉ số RỖNG có hiện là "—" chứ không phải 0 không? "Chưa có số liệu" và "phản hồi
 *      tức thì" là hai chuyện khác nhau, và biến cái đầu thành 0 là nói dối bằng biểu đồ.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SupportPage } from "@/pages/SupportPage";
import { SupportStatsPage } from "@/pages/SupportStatsPage";
import { ChatHistoryPage } from "@/pages/ChatHistoryPage";
import { AuthProvider } from "@/auth/useAuth";
import { setTokens } from "@/auth/session";

const TICKET = {
  id: "t-1",
  code: "GA-260904-0001",
  subject: "Bị trừ tiền hai lần",
  subject_id: "u-1",
  subject_type: "rider",
  trip_id: null,
  conversation_id: "c-1",
  category: "payment",
  priority: "high",
  status: "new",
  team: "finance",
  assigned_agent_id: null,
  first_response_at: null,
  // Quá hạn 5 phút: hàng đợi phải hiện đỏ chứ không im lặng.
  sla_due_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  reopened_count: 0,
  created_at: new Date().toISOString(),
};

interface Call {
  url: string;
  method: string;
  body: unknown;
}

function mockApi(overrides: Record<string, unknown> = {}) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({
        url,
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : null,
      });
      const json = (data: unknown) =>
        new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });

      for (const [phan, data] of Object.entries(overrides)) {
        if (url.includes(phan)) return json(data);
      }
      if (url.includes("/ops/auth/me")) {
        return json({
          id: "staff-1",
          email: "lead@goan.vn",
          full_name: "Trưởng Nhóm",
          roles: ["cs_lead"],
          permissions: ["support:ticket:write", "support:conversation:read_all"],
        });
      }
      if (url.includes("/ops/support/canned-responses")) {
        return json([
          { id: "cr-1", title: "Hoàn tiền", body: "Anh/chị chờ 3-5 ngày ạ", shortcut: "hoantien" },
        ]);
      }
      if (url.includes("/ops/support/queue")) return json([TICKET]);
      if (url.includes("/ops/support/tickets/t-1/reply")) {
        return json({ id: "m-9", kind: "text", body: "Em đang kiểm tra ạ", created_at: "" });
      }
      if (url.includes("/ops/support/tickets/t-1")) {
        return json({ ...TICKET, status: "assigned", first_response_at: new Date().toISOString() });
      }
      if (url.includes("/ops/chat/conversations/c-1/join")) return json({ id: "c-1" });
      if (url.includes("/ops/chat/conversations/c-1/messages")) {
        return json([
          { id: "m-1", kind: "text", body: "Em bị trừ 2 lần", sender_staff_id: null, created_at: "" },
        ]);
      }
      if (url.includes("/ops/chat/search")) return json([]);
      return json({});
    }),
  );
  return calls;
}

function renderPage(node: React.ReactElement) {
  return render(<AuthProvider>{node}</AuthProvider>);
}

beforeEach(() => {
  setTokens("token-test", "refresh-test");
  vi.restoreAllMocks();
  vi.stubGlobal("crypto", { ...globalThis.crypto, randomUUID: () => "uuid-test" });
});

describe("Hàng đợi CSKH (P2-16)", () => {
  it("ticket quá hạn phản hồi đầu hiện rõ là quá hạn", async () => {
    // Hàng đợi im lặng cho một ticket quá hạn là đúng thứ khiến cam kết SLA thành giấy tờ.
    mockApi();
    renderPage(<SupportPage />);

    expect(await screen.findByText("GA-260904-0001")).toBeInTheDocument();
    expect(screen.getByText(/quá hạn 5 phút/)).toBeInTheDocument();
    expect(screen.getByText(/đã tự leo thang lên trưởng nhóm/)).toBeInTheDocument();
  });

  it("mở một ticket thì thấy luôn nội dung hội thoại, không phải sang màn hình khác", async () => {
    mockApi();
    renderPage(<SupportPage />);
    await screen.findByText("GA-260904-0001");

    await userEvent.click(screen.getByRole("button", { name: "Mở" }));

    expect(await screen.findByText("Em bị trừ 2 lần")).toBeInTheDocument();
    expect(screen.getByText("finance")).toBeInTheDocument();
  });
});

describe("Trả lời (P2-16, P2-10)", () => {
  it("một nút gửi gọi đúng endpoint đóng đồng hồ SLA", async () => {
    const calls = mockApi();
    renderPage(<SupportPage />);
    await screen.findByText("GA-260904-0001");
    await userEvent.click(screen.getByRole("button", { name: "Mở" }));

    await userEvent.type(
      await screen.findByLabelText("Nội dung trả lời"),
      "Em đang kiểm tra ạ",
    );
    await userEvent.click(screen.getByRole("button", { name: "Gửi trả lời" }));

    await waitFor(() => {
      const gui = calls.find((c) => c.url.includes("/reply"));
      expect(gui).toBeTruthy();
      expect(gui?.method).toBe("POST");
      expect((gui?.body as { body: string }).body).toBe("Em đang kiểm tra ạ");
      // client_msg_id: Console cũng mất mạng giữa lúc gửi.
      expect((gui?.body as { client_msg_id: string }).client_msg_id).toBe("uuid-test");
    });
  });

  it("ô soạn rỗng thì nút gửi bị khoá", async () => {
    mockApi();
    renderPage(<SupportPage />);
    await screen.findByText("GA-260904-0001");
    await userEvent.click(screen.getByRole("button", { name: "Mở" }));

    expect(await screen.findByRole("button", { name: "Gửi trả lời" })).toBeDisabled();
  });

  it("gõ tắt /hoantien rồi dấu cách thì chèn mẫu trả lời", async () => {
    mockApi();
    renderPage(<SupportPage />);
    await screen.findByText("GA-260904-0001");
    await userEvent.click(screen.getByRole("button", { name: "Mở" }));
    const o = await screen.findByLabelText("Nội dung trả lời");

    await userEvent.type(o, "/hoantien ");

    await waitFor(() => expect(o).toHaveValue("Anh/chị chờ 3-5 ngày ạ"));
  });
});

describe("Tham gia hội thoại 3 bên (P2-17)", () => {
  it("bấm tham gia gọi endpoint join của đúng hội thoại", async () => {
    const calls = mockApi();
    renderPage(<SupportPage />);
    await screen.findByText("GA-260904-0001");
    await userEvent.click(screen.getByRole("button", { name: "Mở" }));

    await userEvent.click(await screen.findByRole("button", { name: "Tham gia chat" }));

    await waitFor(() =>
      expect(calls.some((c) => c.url.endsWith("/ops/chat/conversations/c-1/join"))).toBe(true),
    );
  });
});

describe("Tra cứu lịch sử chat (P2-18)", () => {
  it("nói rõ mỗi lần xem đều được ghi nhật ký", async () => {
    // Tra cứu được mà không để lại dấu vết thì không còn là tra cứu, nó là đọc trộm.
    mockApi();
    renderPage(<ChatHistoryPage />);

    expect(
      await screen.findByText(/đều được ghi vào nhật ký thao tác kèm tên người xem/),
    ).toBeInTheDocument();
  });

  it("không có kết quả thì nói rõ là không có, không để trang trắng", async () => {
    mockApi();
    renderPage(<ChatHistoryPage />);

    await userEvent.type(screen.getByLabelText("Mã chuyến"), "trip-1");
    await userEvent.click(screen.getByRole("button", { name: "Tra cứu" }));

    expect(await screen.findByText("Không có hội thoại nào khớp.")).toBeInTheDocument();
  });
});

describe("Bảng SLA (P2-19)", () => {
  const STATS = {
    tu_ngay: new Date().toISOString(),
    tong_ticket: 3,
    dang_mo: 2,
    qua_han_chua_phan_hoi: 1,
    phan_hoi_dau_phut: 4.5,
    xu_ly_phut: null,
    ty_le_reopen: 0.333,
    ty_le_dat_sla: 0.5,
    agents: [
      {
        agent_id: "chua_phan_cong",
        tickets: 1,
        dang_mo: 1,
        da_ket_luan: 0,
        phan_hoi_dau_phut: null,
        xu_ly_phut: null,
        ty_le_reopen: 0,
        ty_le_dat_sla: null,
      },
    ],
  };

  it("chỉ số chưa có số liệu hiện là — chứ không phải 0", async () => {
    // Đây là toàn bộ lý do bảng này có test: 0 phút cho một agent chưa trả lời ticket nào
    // là con số đẹp nhất và sai nhất mà báo cáo có thể hiện.
    mockApi({ "/ops/support/stats": STATS });
    renderPage(<SupportStatsPage />);

    expect(await screen.findByText("Thời gian xử lý trung bình")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("4.5 phút")).toBeInTheDocument();
  });

  it("quá hạn chưa phản hồi hiện nổi bật", async () => {
    mockApi({ "/ops/support/stats": STATS });
    renderPage(<SupportStatsPage />);

    expect(await screen.findByText("Quá hạn chưa phản hồi")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });
});
