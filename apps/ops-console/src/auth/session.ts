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
