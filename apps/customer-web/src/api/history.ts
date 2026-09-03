import { apiClient } from "@/api/client";
import type { Trip } from "@/types";

/** Lịch sử chuyến của chính người đang đăng nhập. Phân trang bằng con trỏ thời gian. */
export async function getTripHistory(before?: string, limit = 20): Promise<Trip[]> {
  const { data } = await apiClient.get<Trip[]>("/trips", { params: { before, limit } });
  return data;
}
