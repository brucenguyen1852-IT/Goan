import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/authStore";
import type { AuthTokens, OtpRequestResponse } from "@/types";

export async function requestOtp(phone: string): Promise<OtpRequestResponse> {
  const { data } = await apiClient.post<OtpRequestResponse>("/auth/request-otp", { phone });
  return data;
}

/**
 * Backend gộp đăng ký và đăng nhập vào một bước: chưa có tài khoản thì `full_name` là bắt buộc,
 * đã có thì bị bỏ qua. Vì vậy màn hình OTP luôn hỏi tên và gửi kèm.
 */
export async function verifyOtp(
  phone: string,
  otp: string,
  fullName?: string
): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>("/auth/verify-otp", {
    phone,
    otp,
    role: "rider",
    full_name: fullName || undefined,
  });
  return data;
}

/** Thu hồi cả phiên của thiết bị này ở phía backend, không chỉ xoá token trong máy. */
export async function logout(): Promise<void> {
  const { refreshToken, logout: clearLocal } = useAuthStore.getState();
  try {
    if (refreshToken) await apiClient.post("/auth/logout", { refresh_token: refreshToken });
  } finally {
    clearLocal();
  }
}
