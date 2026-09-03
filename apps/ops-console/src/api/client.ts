/**
 * Tầng gọi API của Console.
 *
 * Không viết tay đường dẫn: kiểu dữ liệu đến từ `@goan/api-client`, sinh ra từ OpenAPI của
 * backend. Sai tên endpoint là lỗi biên dịch, không phải lỗi lúc chạy.
 *
 * Access token sống 15 phút, phiên làm việc 8 giờ. Gặp 401 thì tự làm mới một lần rồi phát
 * lại request. Backend xoay vòng refresh token nên chỉ được có ĐÚNG MỘT lần refresh chạy tại
 * một thời điểm — hai request cùng gọi refresh thì request thứ hai dùng token đã tiêu và
 * backend thu hồi cả phiên. Biến `refreshing` giữ ràng buộc đó, đừng bỏ.
 */
import { getSession, clearSession, setTokens } from "@/auth/session";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
  }
}

let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const session = getSession();
  if (!session) return null;
  const response = await fetch(`${BASE}/ops/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: session.refreshToken }),
  });
  if (!response.ok) {
    clearSession();
    return null;
  }
  const data = (await response.json()) as { access_token: string; refresh_token: string };
  setTokens(data.access_token, data.refresh_token);
  return data.access_token;
}

async function parseError(response: Response): Promise<ApiError> {
  let message = `Lỗi ${response.status}`;
  let details: Record<string, unknown> | undefined;
  try {
    const body = await response.json();
    message = body?.error?.message ?? body?.detail?.[0]?.msg ?? message;
    details = body?.error?.details;
  } catch {
    /* thân phản hồi không phải JSON — giữ thông điệp mặc định */
  }
  return new ApiError(response.status, message, details);
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const session = getSession();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (session) headers.set("Authorization", `Bearer ${session.accessToken}`);

  const response = await fetch(`${BASE}${path}`, { ...init, headers });

  if (response.status === 401 && retry && session && !path.startsWith("/ops/auth/")) {
    refreshing = refreshing ?? refreshAccessToken().finally(() => (refreshing = null));
    const token = await refreshing;
    if (token) return request<T>(path, init, false);
    throw new ApiError(401, "Phiên làm việc đã hết hạn, đăng nhập lại");
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body ?? {}) }),
};
