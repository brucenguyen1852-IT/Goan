interface MapPlaceholderProps {
  className?: string;
  label?: string;
}

/**
 * Placeholder cho bản đồ — trong triển khai thật, thay thế bằng SDK bản đồ
 * (Goong Maps / Mapbox GL cho VN, hoặc Google Maps) hiển thị vị trí hiện tại,
 * điểm đón/trả, và vị trí tài xế real-time (qua useTripTrackingSocket).
 */
export function MapPlaceholder({ className = "", label = "Bản đồ" }: MapPlaceholderProps) {
  return (
    <div
      className={`flex items-center justify-center rounded-2xl border border-dashed border-night-700 bg-night-900 text-white/30 ${className}`}
    >
      <span className="text-sm">{label} — tích hợp Goong Maps / Mapbox tại đây</span>
    </div>
  );
}
