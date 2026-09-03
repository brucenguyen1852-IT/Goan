import { useEffect, useRef } from "react";
import { useAuthStore } from "@/store/authStore";
import { useTripStore } from "@/store/tripStore";
import type { TripStatus } from "@/types";

/**
 * Một kết nối WebSocket duy nhất cho cả app (backend: `GET /ws?token=<access_token>`).
 *
 * Backend gửi sự kiện cho MỌI chuyến của người dùng qua cùng một kênh, nên hook lọc theo
 * `trip_id`. WebSocket chỉ là kênh vận chuyển — trang theo dõi vẫn poll REST 5 giây một lần,
 * nên mất kết nối không làm mất dữ liệu, chỉ chậm hơn.
 */
export function useTripTrackingSocket(tripId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const setDriverLocation = useTripStore((s) => s.setDriverLocation);
  const updateTripStatus = useTripStore((s) => s.updateTripStatus);
  const accessToken = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    if (!tripId || !accessToken) return;

    let closed = false;
    let retry = 0;
    let timer: number | undefined;

    const connect = () => {
      if (closed) return;
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(
        `${protocol}//${window.location.host}/ws?token=${encodeURIComponent(accessToken)}`
      );
      wsRef.current = ws;

      ws.onopen = () => {
        retry = 0;
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data) as Record<string, unknown>;
        if (data.trip_id && data.trip_id !== tripId) return;

        switch (data.type) {
          case "driver_location":
            if (typeof data.lat === "number" && typeof data.lng === "number") {
              setDriverLocation({ lat: data.lat, lng: data.lng });
            }
            break;
          case "trip_status_changed":
            if (typeof data.status === "string") updateTripStatus(data.status as TripStatus);
            break;
          case "trip_matched":
            updateTripStatus("driver_arriving");
            break;
          case "trip_completed":
            updateTripStatus("completed");
            break;
        }
      };

      // Nối lại với backoff luỹ tiến + jitter, tối đa 30 giây. Không dùng khoảng cố định:
      // khi backend restart, hàng nghìn client nối lại cùng lúc sẽ dập chết nó lần nữa.
      ws.onclose = () => {
        if (closed) return;
        const delay = Math.min(1000 * 2 ** retry, 30_000) + Math.random() * 500;
        retry += 1;
        timer = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      wsRef.current?.close();
    };
  }, [tripId, accessToken, setDriverLocation, updateTripStatus]);

  return wsRef;
}
