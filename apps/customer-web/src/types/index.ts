// Các kiểu này phản chiếu schema thật của backend (services/api).
// Nguồn sự thật là packages/api-client/openapi.json — khi backend đổi, chạy `pnpm api:client`
// rồi đối chiếu lại file này. Không tự đặt tên trường theo trí nhớ.

export interface GeoPoint {
  lat: number;
  lng: number;
}

export type TimeBand = "normal" | "night" | "peak";

/** Backend trả tiền dưới dạng chuỗi (Decimal) để không mất chính xác khi qua JSON. */
export type Money = string;

export interface FareBreakdown {
  base_fee: Money;
  distance_fee: Money;
  time_fee: Money;
  pickup_surcharge: Money;
  subtotal: Money;
  final_fare: Money;
  driver_payout: Money;
  platform_commission: Money;
  insurance_fee: Money;
  payment_gateway_fee: Money;
}

export interface FareEstimate {
  time_band: TimeBand;
  distance_km: Money;
  duration_minutes: number;
  breakdown: FareBreakdown;
}

export type TripStatus =
  | "requested"
  | "matching"
  | "matched"
  | "driver_arriving"
  | "qr_verified"
  | "in_progress"
  | "completed"
  | "cancelled_by_rider"
  | "cancelled_by_driver"
  | "no_driver_found";

export interface Trip {
  id: string;
  rider_id: string;
  driver_id: string | null;
  status: TripStatus;
  time_band: TimeBand;
  pickup_lat: number;
  pickup_lng: number;
  pickup_address: string | null;
  dropoff_lat: number | null;
  dropoff_lng: number | null;
  dropoff_address: string | null;
  estimated_fare: Money | null;
  final_fare: Money | null;
  distance_km: Money | null;
  duration_minutes: number | null;
  pickup_surcharge: Money;
  driver_payout: Money | null;
  cancellation_fee: Money;
  qr_verified_at: string | null;
  requested_at: string | null;
  matched_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
}

export interface CreateTripResponse {
  trip: Trip;
  estimate: FareBreakdown;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface OtpRequestResponse {
  phone: string;
  expires_in_sec: number;
  /** Chỉ có ở môi trường dev (DEBUG=true) — production luôn null. */
  debug_otp: string | null;
}

/** Định dạng lỗi chuẩn của backend: {"error": {"code", "message", "details"}} */
export interface ApiError {
  error: { code: string; message: string; details?: unknown };
}

export function formatVnd(value: Money | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  return Number.isFinite(n) ? `${n.toLocaleString("vi-VN")}đ` : "—";
}
