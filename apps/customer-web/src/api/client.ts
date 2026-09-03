import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/store/authStore";
import type { ApiError, AuthTokens } from "@/types";

export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 15_000,
});

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Backend rút access token xuống 15 phút, nên đăng xuất khi gặp 401 là không dùng được:
// người dùng sẽ bị văng ra giữa chuyến. Ở đây tự làm mới token rồi phát lại request.
//
// Backend xoay vòng refresh token: mỗi lần refresh trả về refresh token MỚI và vô hiệu
// token cũ. Vì vậy chỉ được có ĐÚNG MỘT lần refresh chạy tại một thời điểm — nếu hai
// request cùng gặp 401 và cùng gọi refresh, request thứ hai sẽ dùng token đã tiêu và bị
// backend coi là tái sử dụng → thu hồi toàn bộ phiên. Biến `refreshing` bên dưới đảm bảo
// mọi request cùng chờ chung một lần refresh.
let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setTokens, phone, logout } = useAuthStore.getState();
  if (!refreshToken) return null;
  try {
    const { data } = await axios.post<AuthTokens>("/api/v1/auth/refresh", {
      refresh_token: refreshToken,
    });
    setTokens(data.access_token, data.refresh_token, phone ?? "");
    return data.access_token;
  } catch {
    logout();
    return null;
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const original = error.config as InternalAxiosRequestConfig & { _retried?: boolean };
    const isAuthCall = original?.url?.includes("/auth/");

    if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true;
      refreshing = refreshing ?? refreshAccessToken().finally(() => (refreshing = null));
      const token = await refreshing;
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return apiClient(original);
      }
    }
    return Promise.reject(error);
  }
);

/** Lấy thông điệp tiếng Việt do backend trả về, thay vì hiện lỗi kỹ thuật cho người dùng. */
export function apiMessage(err: unknown, fallback: string): string {
  const axiosErr = err as AxiosError<ApiError>;
  return axiosErr?.response?.data?.error?.message ?? fallback;
}
