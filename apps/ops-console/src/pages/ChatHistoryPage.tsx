/**
 * Tra cứu lịch sử chat phục vụ khiếu nại (P2-18).
 *
 * Đây là màn hình đọc hội thoại của NGƯỜI KHÁC, nên nó khác mọi màn hình khác ở hai điểm và
 * cả hai đều cố ý: chỉ mở cho quyền `support:conversation:read_all`, và mỗi lần mở đều nằm
 * trong nhật ký thao tác. Tra cứu được mà không để lại dấu vết thì không còn là tra cứu, nó
 * là đọc trộm.
 */
import { useState } from "react";
import { api } from "@/api/client";
import { Badge, Button, Card, Empty, ErrorText, Table } from "@goan/ui";

function asList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

interface Conversation {
  id: string;
  kind: string;
  status: string;
  trip_id: string | null;
  subject: string | null;
  last_message_at: string | null;
}

interface Message {
  id: string;
  kind: string;
  body: string;
  sender_staff_id: string | null;
  created_at: string;
}

export function ChatHistoryPage() {
  const [userId, setUserId] = useState("");
  const [tripId, setTripId] = useState("");
  const [rows, setRows] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [dangXem, setDangXem] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [daTim, setDaTim] = useState(false);

  async function tim() {
    const params = new URLSearchParams();
    if (userId.trim()) params.set("user_id", userId.trim());
    if (tripId.trim()) params.set("trip_id", tripId.trim());
    try {
      setRows(asList<Conversation>(await api.get(`/ops/chat/search?${params.toString()}`)));
      setDaTim(true);
      setMessages([]);
      setDangXem(null);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tra cứu được");
    }
  }

  async function xem(id: string) {
    try {
      setMessages(asList<Message>(await api.get(`/ops/chat/conversations/${id}/messages`)));
      setDangXem(id);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không đọc được hội thoại");
    }
  }

  return (
    <>
      <Card title="Tra cứu lịch sử chat">
        <ErrorText>{error}</ErrorText>
        <p className="muted">
          Mỗi lần mở một hội thoại ở đây đều được ghi vào nhật ký thao tác kèm tên người xem.
        </p>
        <div className="hang">
          <input
            aria-label="Mã khách hoặc tài xế"
            placeholder="Mã khách / tài xế"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
          />
          <input
            aria-label="Mã chuyến"
            placeholder="Mã chuyến"
            value={tripId}
            onChange={(e) => setTripId(e.target.value)}
          />
          <Button kind="primary" onClick={() => void tim()}>
            Tra cứu
          </Button>
        </div>

        {daTim && rows.length === 0 ? (
          <Empty>Không có hội thoại nào khớp.</Empty>
        ) : rows.length > 0 ? (
          <Table head={["Loại", "Chủ đề", "Trạng thái", "Tin gần nhất", ""]}>
            {rows.map((c) => (
              <tr key={c.id} className={dangXem === c.id ? "on" : ""}>
                <td>
                  <Badge kind="muted">{c.kind}</Badge>
                </td>
                <td>{c.subject ?? (c.trip_id ? `Chuyến ${c.trip_id.slice(0, 8)}` : "—")}</td>
                <td>
                  <Badge kind={c.status === "open" ? "ok" : "muted"}>{c.status}</Badge>
                </td>
                <td>
                  {c.last_message_at ? new Date(c.last_message_at).toLocaleString("vi-VN") : "—"}
                </td>
                <td>
                  <Button onClick={() => void xem(c.id)}>Xem</Button>
                </td>
              </tr>
            ))}
          </Table>
        ) : null}
      </Card>

      {dangXem && (
        <Card title="Nội dung hội thoại">
          {messages.length === 0 ? (
            <Empty>Hội thoại này chưa có tin nhắn.</Empty>
          ) : (
            <div className="chat">
              {messages.map((m) => (
                <div key={m.id} className={m.kind === "system" ? "msg sys" : "msg"}>
                  <span className="who">
                    {m.kind === "system" ? "Hệ thống" : m.sender_staff_id ? "CSKH" : "Người dùng"}
                  </span>
                  <span className="body">{m.body}</span>
                  <span className="muted small">
                    {new Date(m.created_at).toLocaleString("vi-VN")}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </>
  );
}
