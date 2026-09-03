import type { ReactElement } from "react";
import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

export function RequireAuth({ children }: { children: ReactElement }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}
