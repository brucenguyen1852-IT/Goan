/**
 * Người đang đăng nhập + danh sách quyền của họ.
 *
 * Menu và nút bấm ẩn/hiện theo `permissions` lấy từ `/ops/auth/me`. Đây chỉ là trải nghiệm
 * người dùng — backend vẫn kiểm quyền cho từng request. Ẩn nút không phải là phân quyền.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/api/client";
import { clearSession, getSession, setTokens, subscribe } from "@/auth/session";

export interface Me {
  id: string;
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
}

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string, totpCode: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    if (!getSession()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      setMe(await api.get<Me>("/ops/auth/me"));
    } catch {
      clearSession();
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMe();
    return subscribe(() => {
      if (!getSession()) setMe(null);
    });
  }, [loadMe]);

  const login = useCallback(
    async (email: string, password: string, totpCode: string) => {
      const tokens = await api.post<{ access_token: string; refresh_token: string }>(
        "/ops/auth/login",
        { email, password, totp_code: totpCode },
      );
      setTokens(tokens.access_token, tokens.refresh_token);
      await loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(async () => {
    const session = getSession();
    if (session) {
      // Chỉ xoá token ở máy thì phiên vẫn sống tới hết 8 giờ ở phía backend.
      try {
        await api.post("/ops/auth/logout", { refresh_token: session.refreshToken });
      } catch {
        /* backend không với tới được thì vẫn phải đăng xuất ở máy này */
      }
    }
    clearSession();
    setMe(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      me,
      loading,
      login,
      logout,
      can: (permission) =>
        !!me && (me.permissions.includes("*") || me.permissions.includes(permission)),
    }),
    [me, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth phải nằm trong AuthProvider");
  return context;
}
