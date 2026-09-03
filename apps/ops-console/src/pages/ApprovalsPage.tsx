import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/useAuth";
import { Badge, Button, Card, Empty, ErrorText, Table } from "@/components/ui";

interface Approval {
  id: string;
  kind: string;
  status: string;
  amount: string | null;
  reason: string;
  requested_by: string;
  decided_by: string | null;
  expires_at: string;
  created_at: string;
}

export function ApprovalsPage() {
  const { me } = useAuth();
  const [rows, setRows] = useState<Approval[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setRows(await api.get<Approval[]>("/ops/approvals?status=pending"));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được hàng đợi duyệt");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(id: string, action: "approve" | "reject") {
    const note = window.prompt(action === "approve" ? "Ghi chú khi duyệt:" : "Vì sao từ chối:");
    try {
      await api.post(`/ops/approvals/${id}/${action}`, { note });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Thao tác thất bại");
    }
  }

  return (
    <Card title="Chờ phê duyệt">
      <ErrorText>{error}</ErrorText>
      <p className="muted">
        Người tạo đề nghị không duyệt được đề nghị của chính mình — kể cả quản trị hệ thống.
      </p>
      {rows.length === 0 ? (
        <Empty>Không có đề nghị nào đang chờ.</Empty>
      ) : (
        <Table head={["Loại", "Số tiền", "Lý do", "Hết hạn", ""]}>
          {rows.map((a) => {
            const cuaMinh = a.requested_by === me?.id;
            return (
              <tr key={a.id}>
                <td>
                  <Badge kind="warn">{a.kind}</Badge>
                </td>
                <td>{a.amount ? `${Number(a.amount).toLocaleString("vi-VN")}đ` : "—"}</td>
                <td>{a.reason}</td>
                <td className="muted small">{new Date(a.expires_at).toLocaleString("vi-VN")}</td>
                <td className="actions">
                  {cuaMinh ? (
                    <span className="muted small">Đề nghị của bạn — người khác duyệt</span>
                  ) : (
                    <>
                      <Button kind="primary" onClick={() => void decide(a.id, "approve")}>
                        Duyệt
                      </Button>
                      <Button kind="danger" onClick={() => void decide(a.id, "reject")}>
                        Từ chối
                      </Button>
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </Table>
      )}
    </Card>
  );
}
