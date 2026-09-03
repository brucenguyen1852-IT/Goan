import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/useAuth";
import { Badge, Button, Card, Empty, ErrorText, Table } from "@/components/ui";

interface OpsDriver {
  driver_id: string;
  full_name: string;
  phone_masked: string | null;
  national_id_masked: string | null;
  license_number: string;
  approval_status: "pending" | "approved" | "rejected";
  approval_note: string | null;
  account_status: string;
  online_status: string;
  rating_avg: string;
  total_trips: number;
  fraud_strikes: number;
  escrow_balance: string;
}

const NHAN_TRANG_THAI: Record<string, string> = {
  pending: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Từ chối",
};

export function DriversPage() {
  const { can } = useAuth();
  const [filter, setFilter] = useState<string>("pending");
  const [rows, setRows] = useState<OpsDriver[]>([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    try {
      const query = filter ? `?approval_status=${filter}` : "";
      setRows(await api.get<OpsDriver[]>(`/ops/drivers${query}`));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được danh sách");
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(driverId: string, action: "approve" | "reject" | "lock" | "unlock") {
    // Từ chối, khoá, mở khoá đều bắt buộc có lý do — backend từ chối request thiếu lý do,
    // và lý do được ghi vĩnh viễn vào nhật ký thao tác.
    let body: Record<string, string> = {};
    if (action !== "approve") {
      const reason = window.prompt("Lý do (ít nhất 10 ký tự, sẽ được ghi vào nhật ký):");
      if (!reason) return;
      body = { reason };
    }
    setBusyId(driverId);
    try {
      await api.post(`/ops/drivers/${driverId}/${action}`, body);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Thao tác thất bại");
    } finally {
      setBusyId("");
    }
  }

  async function revealPii(driverId: string) {
    const reason = window.prompt("Vì sao cần xem số điện thoại đầy đủ? (ghi vào nhật ký)");
    if (!reason) return;
    try {
      const data = await api.post<{ phone: string; national_id_number: string | null }>(
        `/ops/users/${driverId}/reveal-pii`,
        { reason },
      );
      window.alert(`Số điện thoại: ${data.phone}\nCCCD: ${data.national_id_number ?? "chưa có"}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không xem được");
    }
  }

  return (
    <Card
      title="Hồ sơ tài xế"
      action={
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="pending">Chờ duyệt</option>
          <option value="approved">Đã duyệt</option>
          <option value="rejected">Đã từ chối</option>
          <option value="">Tất cả</option>
        </select>
      }
    >
      <ErrorText>{error}</ErrorText>
      {rows.length === 0 ? (
        <Empty>Không có hồ sơ nào ở trạng thái này.</Empty>
      ) : (
        <Table head={["Tài xế", "SĐT", "CCCD", "GPLX", "Duyệt", "Tài khoản", "Cảnh báo", "Thao tác"]}>
          {rows.map((d) => (
            <tr key={d.driver_id}>
              <td>
                {d.full_name}
                {d.approval_note && <div className="muted small">{d.approval_note}</div>}
              </td>
              <td className="mono">{d.phone_masked ?? "—"}</td>
              <td className="mono">{d.national_id_masked ?? "—"}</td>
              <td className="mono">{d.license_number}</td>
              <td>
                <Badge
                  kind={
                    d.approval_status === "approved"
                      ? "ok"
                      : d.approval_status === "rejected"
                        ? "bad"
                        : "warn"
                  }
                >
                  {NHAN_TRANG_THAI[d.approval_status]}
                </Badge>
              </td>
              <td>
                <Badge kind={d.account_status === "active" ? "ok" : "bad"}>{d.account_status}</Badge>
              </td>
              <td>{d.fraud_strikes > 0 ? <Badge kind="bad">{d.fraud_strikes}</Badge> : "—"}</td>
              <td className="actions">
                {can("pii:full:read") && (
                  <Button onClick={() => void revealPii(d.driver_id)}>Xem PII</Button>
                )}
                {can("driver:profile:approve") && d.approval_status !== "approved" && (
                  <Button
                    kind="primary"
                    disabled={busyId === d.driver_id}
                    onClick={() => void act(d.driver_id, "approve")}
                  >
                    Duyệt
                  </Button>
                )}
                {can("driver:profile:approve") && d.approval_status !== "rejected" && (
                  <Button disabled={busyId === d.driver_id} onClick={() => void act(d.driver_id, "reject")}>
                    Từ chối
                  </Button>
                )}
                {can("driver:account:lock") &&
                  (d.account_status === "active" ? (
                    <Button kind="danger" onClick={() => void act(d.driver_id, "lock")}>
                      Khoá
                    </Button>
                  ) : (
                    <Button onClick={() => void act(d.driver_id, "unlock")}>Mở khoá</Button>
                  ))}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
