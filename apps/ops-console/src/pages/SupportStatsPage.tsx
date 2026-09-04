/**
 * Bảng SLA và hiệu suất agent (P2-19).
 *
 * Bốn chỉ số ở tài liệu phân định §7.5. Quy ước hiển thị quan trọng nhất ở đây: chỉ số rỗng
 * hiện là "—", KHÔNG phải 0. "Chưa có số liệu" và "phản hồi tức thì" là hai chuyện khác nhau,
 * và biến cái đầu thành số 0 là nói dối bằng biểu đồ — đúng loại nói dối mà người đọc báo cáo
 * không có cách nào phát hiện.
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import { Badge, Card, Empty, ErrorText, Table } from "@goan/ui";

interface AgentRow {
  agent_id: string;
  tickets: number;
  dang_mo: number;
  da_ket_luan: number;
  phan_hoi_dau_phut: number | null;
  xu_ly_phut: number | null;
  ty_le_reopen: number;
  ty_le_dat_sla: number | null;
}

interface Stats {
  tu_ngay: string;
  tong_ticket: number;
  dang_mo: number;
  qua_han_chua_phan_hoi: number;
  phan_hoi_dau_phut: number | null;
  xu_ly_phut: number | null;
  ty_le_reopen: number;
  ty_le_dat_sla: number | null;
  agents: AgentRow[];
}

function phut(value: number | null): string {
  return value === null ? "—" : `${value} phút`;
}

function phanTram(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function SupportStatsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setStats(await api.get<Stats>(`/ops/support/stats?days=${days}`));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được bảng hiệu suất");
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card
      title="SLA và hiệu suất CSKH"
      action={
        <select
          aria-label="Khoảng thời gian"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          <option value={7}>7 ngày</option>
          <option value={30}>30 ngày</option>
          <option value={90}>90 ngày</option>
        </select>
      }
    >
      <ErrorText>{error}</ErrorText>
      {!stats ? (
        <Empty>Đang tải…</Empty>
      ) : (
        <>
          <dl className="meta">
            <div>
              <dt>Tổng ticket</dt>
              <dd>{stats.tong_ticket}</dd>
            </div>
            <div>
              <dt>Đang mở</dt>
              <dd>{stats.dang_mo}</dd>
            </div>
            <div>
              <dt>Quá hạn chưa phản hồi</dt>
              <dd>
                <Badge kind={stats.qua_han_chua_phan_hoi > 0 ? "bad" : "ok"}>
                  {stats.qua_han_chua_phan_hoi}
                </Badge>
              </dd>
            </div>
            <div>
              <dt>Phản hồi đầu trung bình</dt>
              <dd>{phut(stats.phan_hoi_dau_phut)}</dd>
            </div>
            <div>
              <dt>Thời gian xử lý trung bình</dt>
              <dd>{phut(stats.xu_ly_phut)}</dd>
            </div>
            <div>
              <dt>Đạt SLA</dt>
              <dd>{phanTram(stats.ty_le_dat_sla)}</dd>
            </div>
            <div>
              <dt>Tỷ lệ mở lại</dt>
              <dd>{phanTram(stats.ty_le_reopen)}</dd>
            </div>
          </dl>

          {stats.agents.length === 0 ? (
            <Empty>Chưa có ticket nào trong khoảng này.</Empty>
          ) : (
            <Table
              head={[
                "Agent",
                "Ticket",
                "Đang mở",
                "Đã kết luận",
                "Phản hồi đầu",
                "Xử lý",
                "Đạt SLA",
                "Mở lại",
              ]}
            >
              {stats.agents.map((a) => (
                <tr key={a.agent_id}>
                  <td>{a.agent_id === "chua_phan_cong" ? "— chưa phân công —" : a.agent_id.slice(0, 8)}</td>
                  <td>{a.tickets}</td>
                  <td>{a.dang_mo}</td>
                  <td>{a.da_ket_luan}</td>
                  <td>{phut(a.phan_hoi_dau_phut)}</td>
                  <td>{phut(a.xu_ly_phut)}</td>
                  <td>{phanTram(a.ty_le_dat_sla)}</td>
                  <td>{phanTram(a.ty_le_reopen)}</td>
                </tr>
              ))}
            </Table>
          )}
        </>
      )}
    </Card>
  );
}
