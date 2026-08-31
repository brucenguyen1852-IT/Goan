import { apiClient } from "@/api/client";
import type { Trip } from "@/types";

// NOTE: backend skeleton hiện chưa có endpoint GET /trips (list) — cần bổ sung
// app/api/v1/endpoints/trips.py: GET /trips?customer_id=... trước khi dùng thật.
export async function getTripHistory(): Promise<Trip[]> {
  const { data } = await apiClient.get<Trip[]>("/trips", { params: { mine: true } });
  return data;
}
