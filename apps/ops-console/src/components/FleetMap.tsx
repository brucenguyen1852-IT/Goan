/**
 * Bản đồ đội xe (P1-16).
 *
 * Dùng Leaflet + nền OpenStreetMap: chạy được ngay, không cần khoá API và không cần hợp đồng
 * với ai. Đổi sang Goong (bản đồ Việt Nam, tên đường sát thực tế hơn) chỉ là đổi URL tile và
 * thêm khoá — không phải viết lại màn hình.
 */
import { useEffect, useRef } from "react";
import L from "leaflet";
import type { FleetDriver } from "@/pages/FleetPage";

// TP.HCM — nơi chạy thị trường đầu tiên.
const CENTER: [number, number] = [10.7769, 106.7009];

const ICONS: Record<string, L.DivIcon> = {
  online: L.divIcon({ className: "pin pin-online", iconSize: [14, 14] }),
  on_trip: L.divIcon({ className: "pin pin-ontrip", iconSize: [14, 14] }),
};

export function FleetMap({ drivers }: { drivers: FleetDriver[] }) {
  const holder = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const markers = useRef<Map<string, L.Marker>>(new Map());

  useEffect(() => {
    if (!holder.current || map.current) return;
    map.current = L.map(holder.current).setView(CENTER, 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
    }).addTo(map.current);
    return () => {
      map.current?.remove();
      map.current = null;
      markers.current.clear();
    };
  }, []);

  useEffect(() => {
    if (!map.current) return;
    const seen = new Set<string>();

    for (const driver of drivers) {
      if (driver.lat == null || driver.lng == null) continue;
      seen.add(driver.driver_id);
      const position: [number, number] = [driver.lat, driver.lng];
      const existing = markers.current.get(driver.driver_id);
      // Di chuyển marker đã có thay vì xoá rồi vẽ lại: vẽ lại làm bản đồ nhấp nháy mỗi 3 giây
      // và làm mất popup mà điều phối viên đang mở.
      if (existing) {
        existing.setLatLng(position);
        existing.setIcon(ICONS[driver.online_status] ?? ICONS.online);
      } else {
        const marker = L.marker(position, {
          icon: ICONS[driver.online_status] ?? ICONS.online,
        })
          .addTo(map.current)
          .bindPopup(
            `${driver.full_name_masked ?? "Tài xế"}<br/>${
              driver.online_status === "on_trip" ? "Đang chạy chuyến" : "Sẵn sàng nhận chuyến"
            }`,
          );
        markers.current.set(driver.driver_id, marker);
      }
    }

    for (const [id, marker] of markers.current) {
      if (!seen.has(id)) {
        marker.remove();
        markers.current.delete(id);
      }
    }
  }, [drivers]);

  return <div ref={holder} className="map" />;
}
