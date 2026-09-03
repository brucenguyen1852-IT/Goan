import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import { Badge, Button, Card, Empty, ErrorText, Table } from "@goan/ui";

/** API trả về hình dạng lạ (proxy chèn trang lỗi, gateway trả HTML) không được làm trắng
 * màn hình Console. Thà hiện danh sách rỗng còn hơn để người vận hành nhìn tab trắng. */
function asList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}


interface OpsTrip {
  id: string;
  status: string;
  rider_id: string;
  driver_id: string | null;
  distance_km: string | null;
  final_fare: string | null;
  estimated_fare: string | null;
  driver_payout: string | null;
  requested_at: string | null;
  completed_at: string | null;
}

interface GpsPoint {
  lat: number;
  lng: number;
  recorded_at: string;
}

const TRANG_THAI_XAU = ["cancelled_by_rider", "cancelled_by_driver", "no_driver_found"];

/** Tiền từ backend là chuỗi (Decimal), không ép sang number rồi tính. */
function vnd(value: string | null): string {
  if (!value) return "—";
  return `${Number(value).toLocaleString("vi-VN")}đ`;
}

export function TripsPage() {
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState<OpsTrip[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [gps, setGps] = useState<{ tripId: string; points: GpsPoint[] } | null>(null);

  const load = useCallback(async () => {
    try {
      const query = new URLSearchParams({ limit: "25" });
      if (status) query.set("status", status);
      const page = await api.get<{ items: OpsTrip[]; next_cursor: string | null }>(
        `/ops/trips?${query}`,
      );
      setRows(asList<OpsTrip>(page.items));
      setCursor(page.next_cursor);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được danh sách chuyến");
    }
  }, [status]);

  useEffect(() => {
    void load();
  }, [load]);

  async function loadMore() {
    if (!cursor) return;
    const query = new URLSearchParams({ limit: "25", cursor });
    if (status) query.set("status", status);
    const page = await api.get<{ items: OpsTrip[]; next_cursor: string | null }>(
      `/ops/trips?${query}`,
    );
    setRows((prev) => [...prev, ...asList<OpsTrip>(page.items)]);
    setCursor(page.next_cursor);
  }

  async function showGps(tripId: string) {
    try {
      setGps({ tripId, points: await api.get<GpsPoint[]>(`/ops/trips/${tripId}/gps`) });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được lộ trình");
    }
  }

  return (
    <>
      <Card
        title="Chuyến đi"
        action={
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Tất cả trạng thái</option>
            <option value="matching">Đang ghép</option>
            <option value="in_progress">Đang chạy</option>
            <option value="completed">Hoàn thành</option>
            <option value="rated">Đã đánh giá</option>
            <option value="cancelled_by_rider">Khách huỷ</option>
            <option value="no_driver_found">Không tìm được tài xế</option>
          </select>
        }
      >
        <ErrorText>{error}</ErrorText>
        {rows.length === 0 ? (
          <Empty>Chưa có chuyến nào.</Empty>
        ) : (
          <>
            <Table head={["Mã", "Trạng thái", "Quãng đường", "Cước", "Tài xế nhận", "Thời điểm", ""]}>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td className="mono">{t.id.slice(0, 8)}</td>
                  <td>
                    <Badge kind={TRANG_THAI_XAU.includes(t.status) ? "bad" : "ok"}>{t.status}</Badge>
                  </td>
                  <td>{t.distance_km ? `${t.distance_km} km` : "—"}</td>
                  <td>{vnd(t.final_fare ?? t.estimated_fare)}</td>
                  <td>{vnd(t.driver_payout)}</td>
                  <td className="muted small">
                    {t.requested_at ? new Date(t.requested_at).toLocaleString("vi-VN") : "—"}
                  </td>
                  <td>
                    <Button onClick={() => void showGps(t.id)}>Lộ trình</Button>
                  </td>
                </tr>
              ))}
            </Table>
            {cursor && <Button onClick={() => void loadMore()}>Tải thêm</Button>}
          </>
        )}
      </Card>

      {gps && (
        <Card title={`Lộ trình chuyến ${gps.tripId.slice(0, 8)}`} action={<Button onClick={() => setGps(null)}>Đóng</Button>}>
          {gps.points.length === 0 ? (
            <Empty>Chuyến này không có điểm GPS nào được ghi.</Empty>
          ) : (
            <Table head={["#", "Toạ độ", "Thời điểm"]}>
              {gps.points.map((p, i) => (
                <tr key={`${p.recorded_at}-${i}`}>
                  <td>{i + 1}</td>
                  <td className="mono">
                    {p.lat.toFixed(5)}, {p.lng.toFixed(5)}
                  </td>
                  <td className="muted small">{new Date(p.recorded_at).toLocaleString("vi-VN")}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      )}
    </>
  );
}
