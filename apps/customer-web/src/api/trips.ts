import { apiClient } from "@/api/client";
import type { CreateTripResponse, FareEstimate, GeoPoint, Trip } from "@/types";

export async function getFareEstimate(
  pickup: GeoPoint,
  dropoff: GeoPoint
): Promise<FareEstimate> {
  const { data } = await apiClient.post<FareEstimate>("/pricing/estimate", { pickup, dropoff });
  return data;
}

export async function createTrip(params: {
  pickup: GeoPoint;
  dropoff: GeoPoint;
  pickup_address: string;
  dropoff_address: string;
}): Promise<CreateTripResponse> {
  // Idempotency-Key: mất sóng giữa chừng, người dùng bấm lại thì backend phát lại kết quả cũ
  // thay vì tạo chuyến thứ hai.
  const { data } = await apiClient.post<CreateTripResponse>("/trips", params, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data;
}

export async function getTrip(tripId: string): Promise<Trip> {
  const { data } = await apiClient.get<Trip>(`/trips/${tripId}`);
  return data;
}

export async function cancelTrip(tripId: string, reason?: string): Promise<Trip> {
  const { data } = await apiClient.post<Trip>(
    `/trips/${tripId}/cancel`,
    { reason },
    { headers: { "Idempotency-Key": crypto.randomUUID() } }
  );
  return data;
}

/** Khách quét mã QR trên máy tài xế — không qua bước này thì chuyến không thể bắt đầu. */
export async function verifyQr(tripId: string, qrToken: string): Promise<Trip> {
  const { data } = await apiClient.post<Trip>(`/trips/${tripId}/verify-qr`, { qr_token: qrToken });
  return data;
}
