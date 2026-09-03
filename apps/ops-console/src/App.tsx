import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/auth/useAuth";
import { Button } from "@goan/ui";
import { ApprovalsPage } from "@/pages/ApprovalsPage";
import { AuditPage } from "@/pages/AuditPage";
import { DriversPage } from "@/pages/DriversPage";
import { FleetPage } from "@/pages/FleetPage";
import { LoginPage } from "@/pages/LoginPage";
import { RolesPage } from "@/pages/RolesPage";
import { StaffPage } from "@/pages/StaffPage";
import { TripsPage } from "@/pages/TripsPage";

/** Menu dựng theo quyền: mỗi mục chỉ hiện khi người đăng nhập có quyền tương ứng. */
const MENU = [
  { to: "/fleet", label: "Live Ops", permission: "ops:fleet:read", element: <FleetPage /> },
  { to: "/drivers", label: "Tài xế", permission: "driver:profile:read", element: <DriversPage /> },
  { to: "/trips", label: "Chuyến đi", permission: "trip:trip:read_all", element: <TripsPage /> },
  { to: "/approvals", label: "Chờ duyệt", permission: null, element: <ApprovalsPage /> },
  { to: "/staff", label: "Nhân sự", permission: "iam:staff:read", element: <StaffPage /> },
  { to: "/roles", label: "Vai trò", permission: "iam:role:read", element: <RolesPage /> },
  { to: "/audit", label: "Nhật ký", permission: "audit:log:read", element: <AuditPage /> },
] as const;

export function App() {
  const { me, loading, logout, can } = useAuth();

  if (loading) return <div className="loading">Đang tải…</div>;
  if (!me) return <LoginPage />;

  const visible = MENU.filter((item) => item.permission === null || can(item.permission));
  const home = visible[0]?.to ?? "/approvals";

  return (
    <div className="shell">
      <aside>
        <div className="brand">GoAn Console</div>
        <nav>
          {visible.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? "on" : "")}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="who">
          <div>{me.full_name}</div>
          <div className="muted small">{me.roles.join(", ") || "chưa gán vai trò"}</div>
          <Button onClick={() => void logout()}>Đăng xuất</Button>
        </div>
      </aside>

      <main>
        <Routes>
          {visible.map((item) => (
            <Route key={item.to} path={item.to} element={item.element} />
          ))}
          {/* Vào thẳng đường dẫn không có quyền thì đưa về trang đầu tiên được phép, thay vì
              hiện trang trắng. Backend vẫn là nơi chặn thật. */}
          <Route path="*" element={<Navigate to={home} replace />} />
        </Routes>
      </main>
    </div>
  );
}
