import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  phone: string | null;
  isAuthenticated: boolean;
  setTokens: (accessToken: string, refreshToken: string, phone: string) => void;
  logout: () => void;
}

// Lưu ý: dùng localStorage cho token là chấp nhận được cho web MVP, nhưng khi
// port sang React Native (bản mobile chính thức) cần đổi sang SecureStore/Keychain.
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      phone: null,
      isAuthenticated: false,
      setTokens: (accessToken, refreshToken, phone) =>
        set({ accessToken, refreshToken, phone, isAuthenticated: true }),
      logout: () => set({ accessToken: null, refreshToken: null, phone: null, isAuthenticated: false }),
    }),
    { name: "goan-auth" }
  )
);
