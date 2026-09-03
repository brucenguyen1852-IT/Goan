import { useEffect, useRef, useState } from "react";
import { Badge, Card, Empty, ErrorText, Table } from "@goan/ui";
import { FleetMap } from "@/components/FleetMap";
import { getSession } from "@/auth/session";
import { api } from "@/api/client";

export interface FleetDriver {
  driver_id: string;
  full_name_masked: string | null;
  online_status: string;
  lat: number | null;
  lng: number | null;
  current_trip_id: string | null;
}

interface Snapshot {
  taken_at: string;
  drivers_online: number;
  drivers_on_trip: number;
  trips_active: number;
  drivers: FleetDriver[];
}

/** Hỏi lại mỗi 5 giây, chỉ dùng khi WebSocket không mở được (mạng chặn, proxy cũ). */
const POLL_MS = 5000;

export function FleetPage() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let alive = true;
    let poller: ReturnType<typeof setInterval> | null = null;

    async function poll() {
      try {
        const snapshot = await api.get<Snapshot>("/ops/fleet");
        if (alive) setData(snapshot);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "Không tải được dữ liệu");
      }
    }

    // Backend đẩy ảnh chụp mỗi 3 giây qua WS. Hỏi lại theo chu kỳ chỉ là đường lui khi WS
    // không mở được — giữ cả hai để Console không bao giờ đứng hình.
    const token = getSession()?.accessToken;
    if (token) {
      const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/ops/fleet?token=${token}`;
      try {
        const socket = new WebSocket(url);
        socketRef.current = socket;
        socket.onmessage = (event) => {
          const message = JSON.parse(event.data);
          if (message.type === "ops.fleet_update" && alive) {
            setData(message.data);
            setLive(true);
          }
        };
        socket.onclose = () => alive && setLive(false);
        socket.onerror = () => alive && setLive(false);
      } catch {
        setLive(false);
      }
    }

    void poll();
    poller = setInterval(poll, POLL_MS);
    return () => {
      alive = false;
      if (poller) clearInterval(poller);
      socketRef.current?.close();
    };
  }, []);

  return (
    <>
      <div className="stat-row">
        <Stat label="Tài xế online" value={data?.drivers_online ?? 0} />
        <Stat label="Đang chạy chuyến" value={data?.drivers_on_trip ?? 0} />
        <Stat label="Chuyến đang diễn ra" value={data?.trips_active ?? 0} />
        <div className="stat">
          <span className="stat-value">{live ? "●" : "○"}</span>
          <span className="stat-label">{live ? "Đang nhận real-time" : "Đang hỏi lại 5 giây/lần"}</span>
        </div>
      </div>

      <Card title="Bản đồ đội xe">
        <ErrorText>{error}</ErrorText>
        <FleetMap drivers={data?.drivers ?? []} />
      </Card>

      <Card title="Danh sách tài xế đang trực">
        {data && data.drivers.length === 0 ? (
          <Empty>Chưa có tài xế nào online.</Empty>
        ) : (
          <Table head={["Tài xế", "Trạng thái", "Vị trí", "Chuyến hiện tại"]}>
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
