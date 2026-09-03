import type { TripStatus } from "@/types";

// Nhãn bám đúng enum TripStatus của backend (app/core/constants.py).
// Thêm trạng thái mới ở backend mà quên ở đây thì TypeScript sẽ báo lỗi biên dịch,
// nhờ Record<TripStatus, …> yêu cầu đủ mọi khoá.
const STATUS_LABELS: Record<TripStatus, { label: string; color: string }> = {
  requested: { label: "Đang gửi yêu cầu", color: "bg-white/10 text-white/70" },
  matching: { label: "Đang tìm tài xế", color: "bg-accent/20 text-accent" },
  matched: { label: "Đã ghép tài xế", color: "bg-brand/20 text-brand" },
  driver_arriving: { label: "Tài xế đang đến", color: "bg-brand/20 text-brand" },
  qr_verified: { label: "Đã quét QR, chuẩn bị khởi hành", color: "bg-brand/20 text-brand" },
  in_progress: { label: "Đang trong chuyến", color: "bg-brand text-white" },
  completed: { label: "Đã hoàn thành", color: "bg-white/10 text-white/70" },
  cancelled_by_rider: { label: "Bạn đã huỷ chuyến", color: "bg-red-500/20 text-red-400" },
  cancelled_by_driver: { label: "Tài xế đã huỷ chuyến", color: "bg-red-500/20 text-red-400" },
  no_driver_found: { label: "Không tìm được tài xế", color: "bg-red-500/20 text-red-400" },
};

export function TripStatusBadge({ status }: { status: TripStatus }) {
  const entry = STATUS_LABELS[status];
  if (!entry) return <span className="text-sm text-white/50">{status}</span>;
  return (
    <span className={`inline-block rounded-full px-3 py-1 text-sm font-medium ${entry.color}`}>
      {entry.label}
    </span>
  );
}
