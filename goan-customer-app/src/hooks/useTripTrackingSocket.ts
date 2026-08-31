import { useEffect, useRef } from "react";
import { useTripStore } from "@/store/tripStore";

/** Kết nối WebSocket theo dõi 1 chuyến đi — nhận vị trí tài xế + cập nhật trạng thái. */
export function useTripTrackingSocket(tripId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const setDriverLocation = useTripStore((s) => s.setDriverLocation);
  const updateTripStatus = useTripStore((s) => s.updateTripStatus);

  useEffect(() => {
    if (!tripId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/trips/${tripId}/track`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "driver_location" && data.lat && data.lng) {
        setDriverLocation({ lat: data.lat, lng: data.lng });
      }
      if (data.type === "status_update" && data.status) {
        updateTripStatus(data.status);
      }
    };

    ws.onerror = () => {
      // TODO: hiển thị banner "mất kết nối real-time, đang thử lại" cho người dùng
      console.error("Mất kết nối WebSocket theo dõi chuyến đi");
    };

    return () => ws.close();
  }, [tripId, setDriverLocation, updateTripStatus]);

  return wsRef;
}
