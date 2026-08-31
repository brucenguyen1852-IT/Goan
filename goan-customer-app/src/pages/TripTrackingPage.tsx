import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { TripStatusBadge } from "@/components/ui/TripStatusBadge";
import { MapPlaceholder } from "@/components/map/MapPlaceholder";
import { cancelTrip, getTrip } from "@/api/trips";
import { useTripTrackingSocket } from "@/hooks/useTripTrackingSocket";
import { useTripStore } from "@/store/tripStore";

const CANCELLABLE_STATUSES = new Set(["requested", "matching", "driver_assigned", "driver_arriving"]);

export function TripTrackingPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const navigate = useNavigate();
  const setActiveTrip = useTripStore((s) => s.setActiveTrip);
  const activeTrip = useTripStore((s) => s.activeTrip);
  const driverLocation = useTripStore((s) => s.driverLocation);

  // Kết nối WebSocket để nhận cập nhật vị trí tài xế + trạng thái chuyến real-time
  useTripTrackingSocket(tripId ?? null);

  // Polling dự phòng (mỗi 5s) — đảm bảo trạng thái đúng ngay cả khi WebSocket rớt kết nối tạm thời
  const { data: trip } = useQuery({
    queryKey: ["trip", tripId],
    queryFn: () => getTrip(tripId as string),
    enabled: !!tripId,
    refetchInterval: 5000,
  });

  useEffect(() => {
    if (trip) setActiveTrip(trip);
  }, [trip, setActiveTrip]);

  const displayedTrip = trip ?? activeTrip;

  async function handleCancel() {
    if (!tripId) return;
    await cancelTrip(tripId);
    navigate("/", { replace: true });
  }

  if (!displayedTrip) {
    return <div className="p-6 text-white/60">Đang tải thông tin chuyến đi...</div>;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <MapPlaceholder
        className="h-72 w-full rounded-none"
        label={driverLocation ? `Tài xế: ${driverLocation.lat.toFixed(4)}, ${driverLocation.lng.toFixed(4)}` : "Bản đồ"}
      />

      <div className="flex-1 space-y-5 rounded-t-3xl bg-night-950 px-5 py-6 -mt-6">
        <TripStatusBadge status={displayedTrip.status} />

        <div className="space-y-1">
          <p className="text-sm text-white/60">Điểm đón</p>
          <p className="font-medium">{displayedTrip.pickup_address}</p>
        </div>
        <div className="space-y-1">
          <p className="text-sm text-white/60">Điểm đến</p>
          <p className="font-medium">{displayedTrip.dropoff_address}</p>
        </div>

        {displayedTrip.total_fare && (
          <div className="flex justify-between border-t border-night-700 pt-4 text-lg font-bold text-brand">
            <span>Cước phí</span>
            <span>{displayedTrip.total_fare.toLocaleString("vi-VN")}đ</span>
          </div>
        )}

        {displayedTrip.status === "driver_arriving" && (
          <div className="rounded-xl bg-brand/10 p-4 text-sm text-brand">
            Tài xế đã đến điểm đón. Vui lòng quét mã QR của tài xế để bắt đầu chuyến đi.
          </div>
        )}

        {CANCELLABLE_STATUSES.has(displayedTrip.status) && (
          <Button variant="ghost" fullWidth onClick={handleCancel}>
            Hủy chuyến
          </Button>
        )}

        {displayedTrip.status === "completed" && (
          <Button fullWidth onClick={() => navigate("/")}>
            Về trang chủ
          </Button>
        )}
      </div>
    </div>
  );
}
