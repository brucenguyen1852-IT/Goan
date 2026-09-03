import { apiClient } from "@/api/client";
import type { AuthTokens } from "@/types";

export async function requestOtp(phone: string): Promise<void> {
  await apiClient.post("/auth/otp/request", { phone });
}

export async function verifyOtp(phone: string, otp: string): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>("/auth/otp/verify", { phone, otp });
  return data;
}
