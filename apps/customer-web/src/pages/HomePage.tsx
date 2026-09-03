import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { MapPlaceholder } from "@/components/map/MapPlaceholder";
import { apiMessage } from "@/api/client";
import { createTrip, getFareEstimate } from "@/api/trips";
import { useTripStore } from "@/store/tripStore";
import { formatVnd, type FareEstimate, type GeoPoint } from "@/types";

// TODO: thay bằng ô tìm kiếm địa chỉ có autocomplete (Goong Places / Mapbox Search).
// Toạ độ mẫu đặt ở TP.HCM cho khớp với dữ liệu seed của backend — đội tài xế mẫu đứng
// quanh Quận 1, nếu để toạ độ Hà Nội thì matching sẽ luôn trả "không tìm thấy tài xế".
const DEMO_PICKUP: GeoPoint = { lat: 10.7769, lng: 106.7009 }; // Quận 1, TP.HCM
const DEMO_DROPOFF: GeoPoint = { lat: 10.81, lng: 106.66 }; // Thảo Điền, TP. Thủ Đức

const TIME_BAND_LABEL: Record<string, string> = {
  normal: "Giờ thường",
  night: "Giờ đêm",
  peak: "Cao điểm",
};

export function HomePage() {
  const navigate = useNavigate();
  const setActiveTrip = useTripStore((s) => s.setActiveTrip);

  const [pickupAddress, setPickupAddress] = useState("Quán nhậu Nguyễn Huệ, Quận 1");
  const [dropoffAddress, setDropoffAddress] = useState("Chung cư Thảo Điền, Thủ Đức");
  const [fare, setFare] = useState<FareEstimate | null>(null);
  const [loadingEstimate, setLoadingEstimate] = useState(false);
  const [booking, setBooking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleEstimate() {
    setError(null);
    setLoadingEstimate(true);
    try {
      setFare(await getFareEstimate(DEMO_PICKUP, DEMO_DROPOFF));
    } catch (err) {
      setError(apiMessage(err, "Không tính được giá cước. Vui lòng thử lại."));
    } finally {
      setLoadingEstimate(false);
    }
  }

  async function handleBook() {
    setError(null);
    setBooking(true);
    try {
      const { trip } = await createTrip({
        pickup: DEMO_PICKUP,
        dropoff: DEMO_DROPOFF,
        pickup_address: pickupAddress,
        dropoff_address: dropoffAddress,
      });
      setActiveTrip(trip);
      navigate(`/trip/${trip.id}`);
    } catch (err) {
      setError(apiMessage(err, "Không đặt được chuyến. Vui lòng thử lại."));
    } finally {
      setBooking(false);
    }
  }

  const b = fare?.breakdown;

  return (
    <div className="flex min-h-screen flex-col">
      <MapPlaceholder className="h-64 w-full rounded-none" />

      <div className="-mt-6 flex-1 space-y-5 rounded-t-3xl bg-night-950 px-5 py-6">
        <h1 className="text-xl font-bold">Đặt tài xế lái hộ</h1>

        <div className="space-y-3">
          <Input
            label="Điểm đón"
            value={pickupAddress}
            onChange={(e) => setPickupAddress(e.target.value)}
          />
          <Input
            label="Điểm đến"
            value={dropoffAddress}
            onChange={(e) => setDropoffAddress(e.target.value)}
          />
        </div>

        <Button variant="secondary" fullWidth onClick={handleEstimate} disabled={loadingEstimate}>
          {loadingEstimate ? "Đang tính giá..." : "Xem giá cước ước tính"}
        </Button>

        {fare && b && (
          <div className="space-y-2 rounded-2xl border border-night-700 bg-night-900 p-4">
            <div className="flex justify-between text-sm text-white/60">
              <span>Quãng đường</span>
              <span>
                {fare.distance_km} km · ~{fare.duration_minutes} phút
              </span>
            </div>
            <div className="flex justify-between text-sm text-white/60">
              <span>Khung giờ</span>
              <span>{TIME_BAND_LABEL[fare.time_band] ?? fare.time_band}</span>
            </div>
            <div className="flex justify-between text-sm text-white/60">
              <span>Phí nền</span>
              <span>{formatVnd(b.base_fee)}</span>
            </div>
            <div className="flex justify-between text-sm text-white/60">
              <span>Theo quãng đường</span>
              <span>{formatVnd(b.distance_fee)}</span>
            </div>
            <div className="flex justify-between text-sm text-white/60">
              <span>Theo thời gian</span>
              <span>{formatVnd(b.time_fee)}</span>
            </div>
            {Number(b.pickup_surcharge) > 0 && (
              <div className="flex justify-between text-sm text-white/60">
                <span>Phụ thu đón xa</span>
                <span>+{formatVnd(b.pickup_surcharge)}</span>
              </div>
            )}
            <div className="flex justify-between border-t border-night-700 pt-2 text-lg font-bold text-brand">
              <span>Tổng cước ước tính</span>
              <span>{formatVnd(b.final_fare)}</span>
            </div>
            <p className="text-xs text-white/40">
              Giá cuối tính theo lộ trình GPS thực tế khi kết thúc chuyến.
            </p>
          </div>
        )}

        {error && <p className="text-sm text-red-400">{error}</p>}

        {fare && (
          <Button fullWidth onClick={handleBook} disabled={booking}>
            {booking ? "Đang tìm tài xế..." : "Đặt tài xế ngay"}
          </Button>
        )}
      </div>
    </div>
  );
}
