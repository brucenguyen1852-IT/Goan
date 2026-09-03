import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { Badge, Card, Empty, ErrorText, Table } from "@/components/ui";

interface FleetDriver {
  driver_id: string;
  full_name_masked: string | null;
  online_status: string;
  lat: number | null;
  lng: number | null;
  rating_avg: string;
  total_trips: number;
  current_trip_id: string | null;
}

interface Snapshot {
  taken_at: string;
  drivers_online: number;
  drivers_on_trip: number;
  trips_active: number;
  drivers: FleetDriver[];
}

const REFRESH_MS = 5000;

export function FleetPage() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const snapshot = await api.get<Snapshot>("/ops/fleet");
        if (alive) setData(snapshot);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "Không tải được dữ liệu");
      }
    }
    void tick();
    const timer = setInterval(tick, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <>
      <div className="stat-row">
        <Stat label="Tài xế online" value={data?.drivers_online ?? 0} />
        <Stat label="Đang chạy chuyến" value={data?.drivers_on_trip ?? 0} />
        <Stat label="Chuyến đang diễn ra" value={data?.trips_active ?? 0} />
      </div>

      <Card title="Đội xe theo thời gian thực">
        <ErrorText>{error}</ErrorText>
        {/* Bản đồ thật (Goong/Mapbox) là P1-16. Bảng toạ độ dưới đây đã đủ để điều phối
            biết ai đang ở đâu, và không phụ thuộc vào việc chọn nhà cung cấp bản đồ. */}
        <p className="muted">
          Làm mới mỗi {REFRESH_MS / 1000} giây
          {data ? ` · lúc ${new Date(data.taken_at).toLocaleTimeString("vi-VN")}` : ""}
        </p>
        {data && data.drivers.length === 0 ? (
          <Empty>Chưa có tài xế nào online.</Empty>
        ) : (
          <Table head={["Tài xế", "Trạng thái", "Vị trí", "Đánh giá", "Số chuyến", "Chuyến hiện tại"]}>
            {(data?.drivers ?? []).map((d) => (
              <tr key={d.driver_id}>
                <td>{d.full_name_masked ?? "—"}</td>
                <td>
                  <Badge kind={d.online_status === "on_trip" ? "warn" : "ok"}>
                    {d.online_status === "on_trip" ? "Đang chạy" : "Sẵn sàng"}
                  </Badge>
                </td>
                <td className="mono">
                  {d.lat != null && d.lng != null ? `${d.lat.toFixed(4)}, ${d.lng.toFixed(4)}` : "—"}
                </td>
                <td>{d.rating_avg}</td>
                <td>{d.total_trips}</td>
                <td className="mono">{d.current_trip_id?.slice(0, 8) ?? "—"}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}
