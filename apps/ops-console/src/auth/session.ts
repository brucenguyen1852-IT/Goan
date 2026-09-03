/**
 * Phiên đăng nhập của nhân sự nội bộ.
 *
 * Token nằm ở localStorage: Console chạy trên máy công ty, và mất tab không nên bắt người
 * vận hành gõ lại mã 2FA. Phiên chỉ sống 8 giờ ở phía backend nên rủi ro có giới hạn thời gian.
 */
export interface Session {
  accessToken: string;
  refreshToken: string;
}

const KEY = "goan.ops.session";

type Listener = () => void;
const listeners = new Set<Listener>();
let cached: Session | null | undefined;

export function getSession(): Session | null {
  if (cached === undefined) {
    try {
      const raw = localStorage.getItem(KEY);
      cached = raw ? (JSON.parse(raw) as Session) : null;
    } catch {
      cached = null;
    }
  }
  return cached;
}

function emit(next: Session | null): void {
  cached = next;
  listeners.forEach((l) => l());
}

export function setTokens(accessToken: string, refreshToken: string): void {
  const session = { accessToken, refreshToken };
  localStorage.setItem(KEY, JSON.stringify(session));
  emit(session);
}

export function clearSession(): void {
  localStorage.removeItem(KEY);
  emit(null);
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// --- Nhớ thiết bị (P1-13) ---------------------------------------------------------------
// Cố tình lưu tách khỏi phiên đăng nhập và KHÔNG xoá khi đăng xuất: đăng xuất là kết thúc ca
// làm việc, không phải tuyên bố "máy này không còn tin được". Muốn quên máy thì gỡ ở màn hình
// thiết bị, thao tác đó gọi lên server để token chết thật chứ không chỉ biến mất khỏi trình duyệt.
const DEVICE_KEY = "goan.ops.device";

export function getDeviceToken(): string | null {
  try {
    return localStorage.getItem(DEVICE_KEY);
  } catch {
    return null;
  }
}

export function setDeviceToken(token: string): void {
  try {
    localStorage.setItem(DEVICE_KEY, token);
  } catch {
    /* trình duyệt chặn lưu trữ: lần sau nhập lại mã, không sao */
  }
}

export function forgetDeviceToken(): void {
  try {
    localStorage.removeItem(DEVICE_KEY);
  } catch {
    /* không sao */
  }
}
