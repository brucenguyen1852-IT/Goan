/**
 * Support Desk: hàng đợi, khung chat, thông tin ticket — trong MỘT màn hình (P2-16, P2-17).
 *
 * DoD của P2-16 là "agent xử lý trọn một ticket không rời màn hình", và đó là ràng buộc thiết
 * kế chứ không phải lời khen: mỗi lần agent phải mở tab khác để tra chuyến hay tìm số điện
 * thoại là một lần khách ngồi chờ trong im lặng. Vì thế ba cột nằm cạnh nhau, không phải ba
 * trang nối tiếp.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/useAuth";
import { Badge, Button, Card, Empty, ErrorText, Table } from "@goan/ui";

/** API trả về hình dạng lạ (proxy chèn trang lỗi) không được làm trắng màn hình Console. */
function asList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

interface Ticket {
  id: string;
  code: string;
  subject: string;
  subject_id: string;
  subject_type: string;
  trip_id: string | null;
  conversation_id: string | null;
  category: string;
  priority: string;
  status: string;
  team: string;
  assigned_agent_id: string | null;
  first_response_at: string | null;
  sla_due_at: string;
  reopened_count: number;
  created_at: string;
}

interface Message {
  id: string;
  kind: string;
  body: string;
  sender_user_id: string | null;
  sender_staff_id: string | null;
  created_at: string;
}

interface CannedResponse {
  id: string;
  title: string;
  body: string;
  shortcut: string;
}

const PRIORITY_KIND: Record<string, "ok" | "warn" | "bad" | "muted"> = {
  urgent: "bad",
  high: "warn",
  normal: "muted",
  low: "muted",
};

/** Còn bao lâu tới hạn phản hồi đầu. Quá hạn thì hiện số âm, cố tình: agent phải thấy nó đỏ. */
function slaLabel(ticket: Ticket): { text: string; kind: "ok" | "warn" | "bad" } {
  if (ticket.first_response_at) return { text: "đã phản hồi", kind: "ok" };
  const phut = Math.round((new Date(ticket.sla_due_at).getTime() - Date.now()) / 60000);
  if (phut < 0) return { text: `quá hạn ${-phut} phút`, kind: "bad" };
  if (phut <= 5) return { text: `còn ${phut} phút`, kind: "warn" };
  return { text: `còn ${phut} phút`, kind: "ok" };
}

export function SupportPage() {
  const { me, can } = useAuth();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [chon, setChon] = useState<Ticket | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [canned, setCanned] = useState<CannedResponse[]>([]);
  const [soan, setSoan] = useState("");
  const [error, setError] = useState("");
  const cuoiRef = useRef<HTMLDivElement>(null);

  const loadQueue = useCallback(async () => {
    try {
      setTickets(asList<Ticket>(await api.get("/ops/support/queue")));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được hàng đợi");
    }
  }, []);

  const loadMessages = useCallback(async (ticket: Ticket) => {
    if (!ticket.conversation_id) {
      setMessages([]);
      return;
    }
    try {
      setMessages(
        asList<Message>(
          await api.get(`/ops/chat/conversations/${ticket.conversation_id}/messages`),
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không đọc được hội thoại");
    }
  }, []);

  useEffect(() => {
    void loadQueue();
    void api
      .get("/ops/support/canned-responses")
      .then((rows) => setCanned(asList<CannedResponse>(rows)))
      .catch(() => setCanned([]));
  }, [loadQueue]);

  // Hàng đợi tự làm mới: ticket urgent có 2 phút SLA, nên để agent tự bấm F5 là hỏng cam kết.
  useEffect(() => {
    const id = window.setInterval(() => void loadQueue(), 15_000);
    return () => window.clearInterval(id);
  }, [loadQueue]);

  useEffect(() => {
    // `?.` trên chính hàm: jsdom và một số WebView cũ không cài `scrollIntoView`, và một
    // tiện ích cuộn không được phép làm hỏng cả màn hình đang có người dùng.
    cuoiRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages]);

  async function mo(ticket: Ticket) {
    setChon(ticket);
    setSoan("");
    await loadMessages(ticket);
  }

  async function thaoTac(duong_dan: string, body?: unknown) {
    if (!chon) return;
    try {
      const moi = await api.post<Ticket>(`/ops/support/tickets/${chon.id}${duong_dan}`, body);
      setChon(moi);
      await loadQueue();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Thao tác thất bại");
    }
  }

  /**
   * Gửi trả lời. Một thao tác làm ba việc ở backend: vào hội thoại, gửi tin, đóng đồng hồ
   * SLA. Tách ra ba nút là mời agent quên hai nút cuối — rồi báo cáo SLA hiện "chưa phản
   * hồi" cho những ticket đã được trả lời từ lâu.
   */
  async function guiTraLoi() {
    if (!chon || !soan.trim()) return;
    try {
      await api.post(`/ops/support/tickets/${chon.id}/reply`, {
        body: soan.trim(),
        client_msg_id: crypto.randomUUID(),
      });
      setSoan("");
      const moi = await api.get<Ticket>(`/ops/support/tickets/${chon.id}`);
      setChon(moi);
      await loadMessages(moi);
      await loadQueue();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không gửi được trả lời");
    }
  }

  async function thamGia(vao: boolean) {
    if (!chon?.conversation_id) return;
    try {
      await api.post(
        `/ops/chat/conversations/${chon.conversation_id}/${vao ? "join" : "leave"}`,
      );
      await loadMessages(chon);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thay đổi được trạng thái tham gia");
    }
  }

  /** Gõ tắt `/hoantien` thay bằng nội dung mẫu ngay trong ô soạn (P2-10). */
  function apDungGoTat(value: string) {
    const khop = value.match(/^\/(\S+)\s$/);
    if (!khop) {
      setSoan(value);
      return;
    }
    const mau = canned.find((c) => c.shortcut === khop[1].toLowerCase());
    setSoan(mau ? mau.body : value);
  }

  const quaHan = tickets.filter((t) => !t.first_response_at && new Date(t.sla_due_at) < new Date());

  return (
    <div className="desk">
      <Card
        title={`Hàng đợi (${tickets.length})`}
        action={<Button onClick={() => void loadQueue()}>Làm mới</Button>}
      >
        <ErrorText>{error}</ErrorText>
        {quaHan.length > 0 && (
          <p className="error">
            {quaHan.length} ticket quá hạn phản hồi đầu — đã tự leo thang lên trưởng nhóm.
          </p>
        )}
        {tickets.length === 0 ? (
          <Empty>Hàng đợi trống.</Empty>
        ) : (
          <Table head={["Mã", "Vấn đề", "Ưu tiên", "SLA", ""]}>
            {tickets.map((t) => {
              const sla = slaLabel(t);
              return (
                <tr key={t.id} className={chon?.id === t.id ? "on" : ""}>
                  <td>{t.code}</td>
                  <td>{t.subject}</td>
                  <td>
                    <Badge kind={PRIORITY_KIND[t.priority] ?? "muted"}>{t.priority}</Badge>
                  </td>
                  <td>
                    <Badge kind={sla.kind}>{sla.text}</Badge>
                  </td>
                  <td>
                    <Button onClick={() => void mo(t)}>Mở</Button>
                  </td>
                </tr>
              );
            })}
          </Table>
        )}
      </Card>

      {chon && (
        <Card
          title={`${chon.code} — ${chon.subject}`}
          action={
            <>
              {!chon.assigned_agent_id && (
                <Button kind="primary" onClick={() => void thaoTac("/claim")}>
                  Nhận việc
                </Button>
              )}
              <Button onClick={() => void thamGia(true)}>Tham gia chat</Button>
              <Button onClick={() => void thamGia(false)}>Rời chat</Button>
            </>
          }
        >
          <dl className="meta">
            <div>
              <dt>Trạng thái</dt>
              <dd>{chon.status}</dd>
            </div>
            <div>
              <dt>Đội</dt>
              <dd>{chon.team}</dd>
            </div>
            <div>
              <dt>Loại</dt>
              <dd>{chon.category}</dd>
            </div>
            <div>
              <dt>Người mở</dt>
              <dd>{chon.subject_type}</dd>
            </div>
            <div>
              <dt>Chuyến</dt>
              <dd>{chon.trip_id ? chon.trip_id.slice(0, 8) : "—"}</dd>
            </div>
            <div>
              <dt>Mở lại</dt>
              <dd>{chon.reopened_count} lần</dd>
            </div>
          </dl>

          <div className="chat">
            {messages.length === 0 ? (
              <Empty>Chưa có tin nhắn nào.</Empty>
            ) : (
              messages.map((m) => (
                <div key={m.id} className={m.kind === "system" ? "msg sys" : "msg"}>
                  <span className="who">
                    {m.kind === "system"
                      ? "Hệ thống"
                      : m.sender_staff_id
                        ? "CSKH"
                        : "Khách/Tài xế"}
                  </span>
                  <span className="body">{m.body}</span>
                </div>
              ))
            )}
            <div ref={cuoiRef} />
          </div>

          <div className="soan">
            <textarea
              value={soan}
              placeholder="Gõ /hoantien rồi dấu cách để chèn mẫu trả lời…"
              onChange={(e) => apDungGoTat(e.target.value)}
              aria-label="Nội dung trả lời"
            />
            <div className="hang">
              <Button kind="primary" disabled={!soan.trim()} onClick={() => void guiTraLoi()}>
                Gửi trả lời
              </Button>
              <Button
                onClick={() => {
                  const note = window.prompt("Kết luận ticket — ghi rõ đã xử lý gì:");
                  if (note) void thaoTac("/resolve", { note });
                }}
              >
                Kết luận
              </Button>
              <Button
                onClick={() => {
                  const reason = window.prompt("Chuyển cho đội nào, vì sao? (cs/risk/finance/driver_ops)");
                  if (reason) {
                    const [to_team, ...ly_do] = reason.split(" ");
                    void thaoTac("/transfer", {
                      to_team,
                      reason: ly_do.join(" ") || "chuyển đội",
                    });
                  }
                }}
              >
                Chuyển đội
              </Button>
            </div>
          </div>
        </Card>
      )}

      {!chon && (
        <Card title="Chi tiết">
          <Empty>Chọn một ticket ở hàng đợi để bắt đầu.</Empty>
          {can("support:conversation:read_all") && me && (
            <p className="muted small">
              Bạn có quyền xem mọi hội thoại. Mỗi lần mở lịch sử chat của khách đều được ghi
              vào nhật ký thao tác.
            </p>
          )}
        </Card>
      )}
    </div>
  );
}
