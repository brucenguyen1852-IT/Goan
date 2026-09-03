import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import { Badge, Button, Card, Empty, ErrorText, Table } from "@/components/ui";

interface AuditRow {
  id: string;
  actor_role: string | null;
  action: string;
  status_code: number;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  reason: string | null;
  created_at: string;
}

export function AuditPage() {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [resourceType, setResourceType] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const query = new URLSearchParams({ limit: "50" });
      if (resourceType) query.set("resource_type", resourceType);
      const page = await api.get<{ items: AuditRow[]; next_cursor: string | null }>(
        `/ops/audit-logs?${query}`,
      );
      setRows(page.items);
      setCursor(page.next_cursor);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không đọc được nhật ký");
    }
  }, [resourceType]);

  useEffect(() => {
    void load();
  }, [load]);

  async function loadMore() {
    if (!cursor) return;
    const query = new URLSearchParams({ limit: "50", cursor });
    if (resourceType) query.set("resource_type", resourceType);
    const page = await api.get<{ items: AuditRow[]; next_cursor: string | null }>(
      `/ops/audit-logs?${query}`,
    );
    setRows((prev) => [...prev, ...page.items]);
    setCursor(page.next_cursor);
  }

  return (
    <Card
      title="Nhật ký thao tác"
      action={
        <select value={resourceType} onChange={(e) => setResourceType(e.target.value)}>
          <option value="">Mọi đối tượng</option>
          <option value="trip">Chuyến</option>
          <option value="driver">Tài xế</option>
          <option value="user">Người dùng</option>
          <option value="staff">Nhân sự</option>
        </select>
      }
    >
      <ErrorText>{error}</ErrorText>
      {rows.length === 0 ? (
        <Empty>Chưa có bản ghi nào.</Empty>
      ) : (
        <>
          <Table head={["Thời điểm", "Ai", "Thao tác", "Kết quả", "Đối tượng", "Lý do", "IP"]}>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="muted small">{new Date(r.created_at).toLocaleString("vi-VN")}</td>
                <td>{r.actor_role ?? "khách vãng lai"}</td>
                <td className="mono small">{r.action}</td>
                <td>
                  <Badge kind={r.status_code < 400 ? "ok" : "bad"}>{r.status_code}</Badge>
                </td>
                <td className="mono small">
                  {r.resource_type ? `${r.resource_type}/${r.resource_id?.slice(0, 8)}` : "—"}
                </td>
                <td>{r.reason ?? "—"}</td>
                <td className="mono small">{r.ip_address ?? "—"}</td>
              </tr>
            ))}
          </Table>
          {cursor && <Button onClick={() => void loadMore()}>Tải thêm</Button>}
        </>
      )}
    </Card>
  );
}
