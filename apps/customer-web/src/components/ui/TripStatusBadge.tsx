import type { TripStatus } from "@/types";

const STATUS_LABELS: Record<TripStatus, { label: string; color: string }> = {
  requested: { label: "Đang gửi yêu cầu", color: "bg-white/10 text-white/70" },
  matching: { label: "Đang tìm tài xế", color: "bg-accent/20 text-accent" },
  driver_assigned: { label: "Đã ghép tài xế", color: "bg-brand/20 text-brand" },
  driver_arriving: { label: "Tài xế đang đến", color: "bg-brand/20 text-brand" },
  qr_verified: { label: "Đã xác thực, chuẩn bị khởi hành", color: "bg-brand/20 text-brand" },
  in_progress: { label: "Đang trong chuyến", color: "bg-brand text-white" },
  completed: { label: "Đã hoàn thành", color: "bg-white/10 text-white/70" },
  rated: { label: "Đã đánh giá", color: "bg-white/10 text-white/70" },
  cancelled_by_customer: { label: "Bạn đã hủy chuyến", color: "bg-red-500/20 text-red-400" },
  cancelled_by_driver: { label: "Tài xế đã hủy chuyến", color: "bg-red-500/20 text-red-400" },
  no_driver_found: { label: "Không tìm được tài xế", color: "bg-red-500/20 text-red-400" },
};

export function TripStatusBadge({ status }: { status: TripStatus }) {
  const { label, color } = STATUS_LABELS[status];
  return (
    <span className={`inline-block rounded-full px-3 py-1 text-sm font-medium ${color}`}>
      {label}
    </span>
  );
}
