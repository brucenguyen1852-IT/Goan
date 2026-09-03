import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { TripStatusBadge } from "@/components/ui/TripStatusBadge";
import { MapPlaceholder } from "@/components/map/MapPlaceholder";
import { apiMessage } from "@/api/client";
import { cancelTrip, getTrip, verifyQr } from "@/api/trips";
import { useTripTrackingSocket } from "@/hooks/useTripTrackingSocket";
import { useTripStore } from "@/store/tripStore";
import { formatVnd, type TripStatus } from "@/types";

// Backend chỉ cho huỷ ở các trạng thái này (app/domains/trips/state_machine.py).
// Sau khi quét QR thì chuyến đã chạy, huỷ phải qua CSKH.
const CANCELLABLE_STATUSES = new Set<TripStatus>([
  "requested",
  "matching",
  "matched",
  "driver_arriving",
]);

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

  const [qrToken, setQrToken] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleCancel() {
    if (!tripId) return;
    setActionError(null);
    setBusy(true);
    try {
      await cancelTrip(tripId);
      navigate("/", { replace: true });
    } catch (err) {
      setActionError(apiMessage(err, "Không huỷ được chuyến."));
    } finally {
      setBusy(false);
    }
  }

  // Bản web MVP chưa có camera quét QR nên nhập tay mã trên máy tài xế.
  // App React Native sẽ thay bằng quét camera thật.
  async function handleVerifyQr() {
    if (!tripId) return;
    setActionError(null);
    setBusy(true);
    try {
      const updated = await verifyQr(tripId, qrToken.trim());
      setActiveTrip(updated);
      setQrToken("");
    } catch (err) {
      setActionError(apiMessage(err, "Mã QR không hợp lệ."));
    } finally {
      setBusy(false);
    }
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

        <div className="flex justify-between border-t border-night-700 pt-4 text-lg font-bold text-brand">
          <span>{displayedTrip.final_fare ? "Cước phí" : "Ước tính"}</span>
          <span>{formatVnd(displayedTrip.final_fare ?? displayedTrip.estimated_fare)}</span>
        </div>

        {displayedTrip.status === "driver_arriving" && (
          <div className="space-y-3 rounded-xl bg-brand/10 p-4">
            <p className="text-sm text-brand">
              Tài xế đã đến điểm đón. Quét mã QR trên máy tài xế để bắt đầu chuyến — đây là bước
              bắt buộc để chống đơn ma.
            </p>
            <Input
              label="Mã QR của tài xế"
              placeholder="Dán mã hiển thị trên máy tài xế"
              value={qrToken}
              onChange={(e) => setQrToken(e.target.value)}
            />
            <Button fullWidth onClick={handleVerifyQr} disabled={busy || !qrToken.trim()}>
              {busy ? "Đang xác thực..." : "Xác nhận bắt đầu chuyến"}
            </Button>
          </div>
        )}

        {displayedTrip.status === "no_driver_found" && (
          <div className="rounded-xl bg-red-500/10 p-4 text-sm text-red-300">
            Chưa tìm được tài xế quanh điểm đón. Bạn có thể đặt lại hoặc thử vào giờ khác.
          </div>
        )}

        {actionError && <p className="text-sm text-red-400">{actionError}</p>}

        {CANCELLABLE_STATUSES.has(displayedTrip.status) && (
          <Button variant="ghost" fullWidth onClick={handleCancel} disabled={busy}>
            Huỷ chuyến
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
