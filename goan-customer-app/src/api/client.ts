import axios from "axios";
import { useAuthStore } from "@/store/authStore";

export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 15_000,
});

// Gắn access token vào mọi request nếu đã đăng nhập
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Nếu token hết hạn (401), đăng xuất và điều hướng về màn hình đăng nhập.
// TODO: có thể nâng cấp thành tự động refresh token bằng refresh_token trước khi logout.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
    }
    return Promise.reject(error);
  }
);
