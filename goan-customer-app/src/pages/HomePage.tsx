import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { MapPlaceholder } from "@/components/map/MapPlaceholder";
import { createTrip, getFareEstimate } from "@/api/trips";
import { useTripStore } from "@/store/tripStore";
import type { FareEstimate, GeoPoint, PaymentMethod } from "@/types";

// TODO: thay bằng ô tìm kiếm địa chỉ có autocomplete (gọi Maps Places API).
// Tạm thời demo với 2 điểm cố định để luồng đặt xe chạy được end-to-end.
const DEMO_PICKUP: GeoPoint = { lat: 21.0285, lng: 105.8542 }; // Hồ Gươm, Hà Nội
const DEMO_DROPOFF: GeoPoint = { lat: 21.0122, lng: 105.8252 }; // Cầu Giấy, Hà Nội

export function HomePage() {
  const navigate = useNavigate();
  const setActiveTrip = useTripStore((s) => s.setActiveTrip);

  const [pickupAddress, setPickupAddress] = useState("Hồ Gươm, Hà Nội");
  const [dropoffAddress, setDropoffAddress] = useState("Cầu Giấy, Hà Nội");
  const [fare, setFare] = useState<FareEstimate | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("online");
  const [loadingEstimate, setLoadingEstimate] = useState(false);
  const [booking, setBooking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleEstimate() {
    setError(null);
    setLoadingEstimate(true);
    try {
      const result = await getFareEstimate(DEMO_PICKUP, DEMO_DROPOFF, pickupAddress, dropoffAddress);
      setFare(result);
    } catch {
      setError("Không tính được giá cước. Vui lòng thử lại.");
    } finally {
      setLoadingEstimate(false);
    }
  }

  async function handleBook() {
    setError(null);
    setBooking(true);
    try {
      const trip = await createTrip({
        pickup: DEMO_PICKUP,
        dropoff: DEMO_DROPOFF,
        pickup_address: pickupAddress,
        dropoff_address: dropoffAddress,
        payment_method: paymentMethod,
      });
      setActiveTrip(trip);
      navigate(`/trip/${trip.id}`);
    } catch {
      setError("Không đặt được chuyến. Vui lòng thử lại.");
    } finally {
      setBooking(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <MapPlaceholder className="h-64 w-full rounded-none" />

      <div className="flex-1 space-y-5 rounded-t-3xl bg-night-950 px-5 py-6 -mt-6">
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

        {fare && (
          <div className="rounded-2xl border border-night-700 bg-night-900 p-4 space-y-2">
            <div className="flex justify-between text-sm text-white/60">
              <span>Quãng đường</span>
              <span>{fare.distance_km} km · ~{fare.duration_min} phút</span>
            </div>
            <div className="flex justify-between text-sm text-white/60">
              <span>Khung giờ</span>
              <span>
                {fare.time_band === "night" ? "Giờ đêm" : fare.time_band === "peak" ? "Cao điểm" : "Giờ thường"}
              </span>
            </div>
            {fare.surcharge_far_pickup > 0 && (
              <div className="flex justify-between text-sm text-white/60">
                <span>Phụ thu đón xa</span>
                <span>+{fare.surcharge_far_pickup.toLocaleString("vi-VN")}đ</span>
              </div>
            )}
            <div className="flex justify-between border-t border-night-700 pt-2 text-lg font-bold text-brand">
              <span>Tổng cước ước tính</span>
              <span>{fare.total_fare_estimate.toLocaleString("vi-VN")}đ</span>
            </div>
          </div>
        )}

        {fare && (
          <div className="space-y-2">
            <span className="block text-sm text-white/60">Phương thức thanh toán</span>
            <div className="flex gap-3">
              <button
                onClick={() => setPaymentMethod("online")}
                className={`flex-1 rounded-xl border px-4 py-3 text-sm font-medium ${
                  paymentMethod === "online" ? "border-brand bg-brand/10 text-brand" : "border-night-700 text-white/60"
                }`}
              >
                Thanh toán online
              </button>
              <button
                onClick={() => setPaymentMethod("cash")}
                className={`flex-1 rounded-xl border px-4 py-3 text-sm font-medium ${
                  paymentMethod === "cash" ? "border-brand bg-brand/10 text-brand" : "border-night-700 text-white/60"
                }`}
              >
                Tiền mặt
              </button>
            </div>
          </div>
        )}

        {error && <p className="text-sm text-red-400">{error}</p>}

        {fare && (
          <Button fullWidth onClick={handleBook} disabled={booking}>
            {booking ? "Đang đặt xe..." : "Đặt tài xế ngay"}
          </Button>
        )}
      </div>
    </div>
  );
}
