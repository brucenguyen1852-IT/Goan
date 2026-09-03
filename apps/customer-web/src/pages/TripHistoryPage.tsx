import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { TripStatusBadge } from "@/components/ui/TripStatusBadge";
import { getTripHistory } from "@/api/history";
import { formatVnd } from "@/types";

export function TripHistoryPage() {
  const navigate = useNavigate();
  const { data: trips, isLoading, isError } = useQuery({
    queryKey: ["trip-history"],
    queryFn: () => getTripHistory(),
  });

  return (
    <div className="min-h-screen px-5 py-6">
      <h1 className="mb-5 text-xl font-bold">Lịch sử chuyến đi</h1>

      {isLoading && <p className="text-white/60">Đang tải...</p>}
      {isError && <p className="text-red-400">Không tải được lịch sử chuyến đi.</p>}

      <div className="space-y-3">
        {trips?.map((trip) => (
          <button
            key={trip.id}
            onClick={() => navigate(`/trip/${trip.id}`)}
            className="w-full rounded-2xl border border-night-700 bg-night-900 p-4 text-left"
          >
            <div className="mb-2 flex items-center justify-between">
              <TripStatusBadge status={trip.status} />
              <span className="font-semibold text-brand">
                {formatVnd(trip.final_fare ?? trip.estimated_fare)}
              </span>
            </div>
            <p className="text-sm text-white/80">{trip.pickup_address}</p>
            <p className="text-sm text-white/50">→ {trip.dropoff_address}</p>
            <p className="mt-1 text-xs text-white/30">
              {trip.requested_at ? new Date(trip.requested_at).toLocaleString("vi-VN") : "—"}
            </p>
          </button>
        ))}

        {trips?.length === 0 && <p className="text-white/40">Bạn chưa có chuyến đi nào.</p>}
      </div>
    </div>
  );
}
