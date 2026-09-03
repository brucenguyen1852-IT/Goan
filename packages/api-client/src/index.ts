/**
 * Điểm vào của API client dùng chung.
 *
 * `schema.d.ts` được sinh từ openapi.json (chạy `pnpm api:client` ở thư mục gốc) và không
 * được commit — vì vậy import bên dưới sẽ báo lỗi cho tới khi bạn chạy lệnh sinh.
 */
import createClient from "openapi-fetch";
import type { paths } from "./generated/schema";

export type ApiPaths = paths;

export interface CreateApiOptions {
  baseUrl: string;
  /** Trả về access token hiện tại, hoặc null nếu chưa đăng nhập. */
  getAccessToken?: () => string | null;
  /** Gọi khi backend trả 401 sau khi đã thử refresh — nơi để đăng xuất người dùng. */
  onUnauthorized?: () => void;
}

export function createApi({ baseUrl, getAccessToken, onUnauthorized }: CreateApiOptions) {
  const client = createClient<paths>({ baseUrl });

  client.use({
    onRequest({ request }) {
      const token = getAccessToken?.();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
    onResponse({ response }) {
      if (response.status === 401) onUnauthorized?.();
      return response;
    },
  });

  return client;
}
